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

# Function to create resource group if it doesn't exist
create_resource_group() {
    echo "Checking resource group '$rg'..."
    local exists=$(az group exists --name $rg)
    if [ "$exists" = "false" ]; then
        az group create --name $rg --location $location > /dev/null 2>&1
        echo "Resource group created: $rg"
    else
        echo "Resource group already exists: $rg"
    fi
}

# Function to create Azure Managed Redis resource
create_redis_resource() {
    create_resource_group
    echo ""

    # Check if the cluster already exists
    local cluster_state=$(az redisenterprise show --resource-group $rg --name $cache_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -n "$cluster_state" ]; then
        echo "Azure Managed Redis resource already exists: $cache_name (State: $cluster_state)"
        return 0
    fi

    echo "Creating Azure Managed Redis cluster '$cache_name'..."

    # Create the Azure Managed Redis cluster (Balanced_B0 is the cheapest SKU)
    az redisenterprise create \
        --resource-group $rg \
        --name $cache_name \
        --location $location \
        --sku Balanced_B0 \
        --public-network-access "Enabled" \
        --no-database \
        --no-wait

    echo "The Azure Managed Redis cluster is being created and takes 5-10 minutes to complete."
    echo "You can check the deployment status from the menu later in the exercise."
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

# Function to create database and retrieve endpoint and access key
create_database_and_get_key() {

    # Check if cluster is provisioned
    local cluster_state=$(az redisenterprise show --resource-group $rg --name $cache_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ "$cluster_state" != "Succeeded" ]; then
        echo "Error: Cluster is not ready (State: ${cluster_state:-Not created})."
        echo "Please check the deployment status (option 2) and wait until provisioning succeeds."
        return 1
    fi

    # Check if database already exists
    local db_state=$(az redisenterprise database show --resource-group $rg --cluster-name $cache_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -n "$db_state" ]; then
        echo "Database already exists (State: $db_state). Enabling access key auth..."
        az redisenterprise database update \
            --resource-group $rg \
            --cluster-name $cache_name \
            --access-keys-auth "Enabled" \
            > /dev/null 2>&1
    else
        echo "Creating database with RediSearch module and access key authentication..."
        az redisenterprise database create \
            --resource-group $rg \
            --cluster-name $cache_name \
            --clustering-policy "EnterpriseCluster" \
            --eviction-policy "NoEviction" \
            --modules name="RediSearch" \
            --access-keys-auth "Enabled" \
            > /dev/null 2>&1

        if [ $? -ne 0 ]; then
            echo "Error: Failed to create database."
            return 1
        fi
    fi

    echo "Retrieving endpoint and access key..."

    # Get the endpoint (hostname)
    local hostname=$(az redisenterprise show --resource-group $rg --name $cache_name --query "hostName" -o tsv 2>/dev/null)

    # Get the primary access key
    local primaryKey=$(az redisenterprise database list-keys --cluster-name $cache_name -g $rg --query "primaryKey" -o tsv 2>/dev/null)

    # Check if values are empty
    if [ -z "$hostname" ] || [ -z "$primaryKey" ]; then
        echo ""
        echo "Error: Unable to retrieve endpoint or access key."
        echo "Please check the deployment status to ensure the resource is fully provisioned."
        return 1
    fi

    # Write .env file
    cat > .env << EOF
REDIS_HOST=$hostname
REDIS_KEY=$primaryKey
EOF

    clear
    echo ""
    echo "Redis Connection Information"
    echo "==========================================================="
    echo "Endpoint: $hostname"
    echo "Primary Key: $primaryKey"
    echo ""
    echo "Values have been saved to .env file"
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
    echo "2. Check deployment status"
    echo "3. Create database and retrieve endpoint and access key"
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
            check_deployment_status
            echo ""
            read -p "Press Enter to continue..."
            ;;
        3)
            echo ""
            create_database_and_get_key
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
