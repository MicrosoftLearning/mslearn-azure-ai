#!/usr/bin/env bash

# Change the values of these variables as needed

# rg="<your-resource-group-name>"  # Resource Group name
# location="<your-azure-region>"   # Azure region for the resources

rg="rg-exercises" # Resource Group name
location="westus2" # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Disable Git Bash forward-slash path conversion (Windows only; no-op elsewhere).
export MSYS_NO_PATHCONV=1

# Generate consistent hash from Azure user object ID (based on az login account)
user_object_id=$(az ad signed-in-user show --query "id" -o tsv 2>/dev/null)
if [ -z "$user_object_id" ]; then
    echo "Error: Not authenticated with Azure. Please run: az login"
    exit 1
fi
user_hash=$(echo -n "$user_object_id" | sha1sum | cut -c1-8)
cache_name="amr-exercise-${user_hash}"

# Run a command quietly, but surface its exit code and output if it fails. This
# keeps the console clean on success while still reporting the error details
# when a command fails, instead of silently discarding them. Use for action
# commands (create/update/delete), not for commands whose output you need to
# capture.
# Usage: run_quiet "Description of the step" <command> [args...]
run_quiet() {
    local description="$1"
    shift
    local output rc
    output=$("$@" 2>&1)
    rc=$?
    if [ $rc -ne 0 ]; then
        echo "Error: ${description} failed (exit code ${rc})."
        if [ -n "$output" ]; then
            echo "$output"
        fi
        return $rc
    fi
    return 0
}

# Function to create resource group if it doesn't exist
create_resource_group() {
    echo "Checking resource group '$rg'..."
    local exists=$(az group exists --name $rg)
    if [ "$exists" = "false" ]; then
        run_quiet "Create resource group" az group create --name $rg --location $location || return 1
        echo "Resource group created: $rg"
    else
        echo "Resource group already exists: $rg"
    fi
}

# Function to create Azure Managed Redis resource
create_redis_resource() {
    create_resource_group
    echo ""

    # Check the current state of the cluster before deciding what to do.
    local cluster_state=$(az redisenterprise show --resource-group $rg --name $cache_name --query "provisioningState" -o tsv 2>/dev/null)
    case "$cluster_state" in
        "Succeeded")
            echo "Azure Managed Redis resource already exists: $cache_name (State: $cluster_state)"
            return 0
            ;;
        "Failed"|"Canceled")
            echo "A previous deployment of '$cache_name' is in a $cluster_state state."
            echo "Deleting the failed resource before trying again..."
            run_quiet "Delete failed Azure Managed Redis resource" az redisenterprise delete \
                --resource-group $rg \
                --name $cache_name \
                --yes || return 1
            echo "Failed resource deleted."
            echo ""
            ;;
        "")
            # No existing cluster; continue to create it below.
            ;;
        *)
            echo "Azure Managed Redis resource '$cache_name' is still provisioning (State: $cluster_state)."
            echo "Please wait for it to finish, then check the deployment status from the menu."
            return 0
            ;;
    esac

    echo "Creating Azure Managed Redis resource '$cache_name' in '$location'..."
    echo "This takes 5-10 minutes to complete. Please wait..."

    if ! run_quiet "Create Azure Managed Redis resource" az redisenterprise create \
        --resource-group $rg \
        --name $cache_name \
        --location $location \
        --sku "Balanced_B0" \
        --public-network-access "Enabled" \
        --no-database; then
        echo ""
        echo "⚠ The deployment failed. This is most often caused by a temporary"
        echo "  lack of capacity for this SKU in the '$location' region."
        echo ""
        echo "To resolve this:"
        echo "  1. Choose option 4 to exit the script."
        echo "  2. Near the top of this script, change the 'location' variable to a"
        echo "     different region, such as eastus2, australiaeast, or canadacentral."
        echo "  3. Run the script again and choose option 1. The failed resource is"
        echo "     deleted automatically before the next attempt."
        return 1
    fi

    echo ""
    echo "✓ Azure Managed Redis resource created successfully: $cache_name"
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    echo "Cluster ($cache_name):"
    local cluster_state=$(az redisenterprise show --resource-group $rg --name $cache_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -n "$cluster_state" ]; then
        echo "  Provisioning state: $cluster_state"
    else
        echo "  Status: Not created"
    fi

    echo ""
    echo "Database:"
    local db_state=$(az redisenterprise database show --resource-group $rg --cluster-name $cache_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -n "$db_state" ]; then
        echo "  Provisioning state: $db_state"
    else
        echo "  Status: Not created"
    fi
}

# Function to create the database, grant the current user Microsoft Entra ID
# access, and write the .env file with the Redis endpoint
create_database_and_configure_access() {

    # Check if cluster is provisioned
    local cluster_state=$(az redisenterprise show --resource-group $rg --name $cache_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ "$cluster_state" != "Succeeded" ]; then
        echo "Error: Cluster is not ready (State: ${cluster_state:-Not created})."
        echo "Please check the deployment status (option 3) and wait until provisioning succeeds."
        return 1
    fi

    # Check if database already exists
    local db_state=$(az redisenterprise database show --resource-group $rg --cluster-name $cache_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -n "$db_state" ]; then
        echo "Database already exists (State: $db_state)."
    else
        echo "Creating database..."
        run_quiet "Create database" az redisenterprise database create \
            --resource-group $rg \
            --cluster-name $cache_name \
            --client-protocol "Encrypted" \
            --clustering-policy "NoCluster" \
            --eviction-policy "AllKeysLRU" \
            --port 10000 || return 1
    fi

    # Grant the signed-in user access to the database using Microsoft Entra ID.
    # This assigns the built-in "default" access policy to the user's object ID
    # so the app can authenticate with DefaultAzureCredential instead of a key.
    local assignment_name="useraccess"
    local assignment_state=$(az redisenterprise database access-policy-assignment show \
        --resource-group $rg \
        --cluster-name $cache_name \
        --database-name default \
        --access-policy-assignment-name $assignment_name \
        --query "provisioningState" -o tsv 2>/dev/null)

    if [ -n "$assignment_state" ]; then
        echo "Microsoft Entra access is already assigned for the current user."
    else
        echo "Assigning Microsoft Entra access for the current user..."
        run_quiet "Assign access policy" az redisenterprise database access-policy-assignment create \
            --resource-group $rg \
            --cluster-name $cache_name \
            --database-name default \
            --access-policy-assignment-name $assignment_name \
            --access-policy-name default \
            --object-id $user_object_id || return 1
    fi

    echo "Retrieving endpoint..."

    # Get the endpoint (hostname)
    local hostname=$(az redisenterprise show --resource-group $rg --name $cache_name --query "hostName" -o tsv 2>/dev/null)

    # Check if the value is empty
    if [ -z "$hostname" ]; then
        echo ""
        echo "Error: Unable to retrieve the endpoint."
        echo "Please check the deployment status to ensure the resource is fully provisioned."
        return 1
    fi

    # Write .env file
    cat > .env << EOF
export REDIS_HOST="$hostname"
EOF

    clear
    echo ""
    echo "Redis Connection Information"
    echo "==========================================================="
    echo "Endpoint: $hostname"
    echo "Authentication: Microsoft Entra ID (current user)"
    echo ""
    echo "The endpoint has been saved to the .env file"
}

# Display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    Azure Managed Redis Deployment Menu"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Cache Name: $cache_name"
    echo "Location: $location"
    echo "====================================================================="
    echo "1. Create Azure Managed Redis resource"
    echo "2. Create database and configure access"
    echo "3. Check deployment status"
    echo "4. Exit"
    echo "====================================================================="
}

# Main menu loop
while true; do
    show_menu
    read -p "Please select an option (1-4): " choice

    case $choice in
        1)
            echo ""
            create_redis_resource
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            create_database_and_configure_access
            echo ""
            read -p "Press Enter to continue..."
            ;;
        3)
            echo ""
            check_deployment_status
            echo ""
            read -p "Press Enter to continue..."
            ;;
        4)
            echo "Exiting..."
            clear
            exit 0
            ;;
        *)
            echo ""
            echo "Invalid option. Please select 1-4."
            echo ""
            read -p "Press Enter to continue..."
            ;;
    esac

    echo ""
done

