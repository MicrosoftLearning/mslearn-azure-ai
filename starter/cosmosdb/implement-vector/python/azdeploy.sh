#!/usr/bin/env bash

# Change the values of these variables as needed

rg="<your-resource-group-name>"  # Resource Group name
location="<your-azure-region>"   # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from Azure user object ID (based on az login account)
user_object_id=$(az ad signed-in-user show --query "id" -o tsv 2>/dev/null)
if [ -z "$user_object_id" ]; then
    echo "Error: Not authenticated with Azure. Please run: az login"
    exit 1
fi
user_hash=$(echo -n "$user_object_id" | sha1sum | cut -c1-8)
account_name="cosmos-vector-${user_hash}"
database_name="vectorstore"
container_name="vectors"

# Function to create resource group if it doesn't exist
create_resource_group() {
    echo "Checking/creating resource group '$rg'..."

    local exists=$(az group exists --name $rg)
    if [ "$exists" = "false" ]; then
        az group create --name $rg --location $location > /dev/null 2>&1
        echo "✓ Resource group created: $rg"
    else
        echo "✓ Resource group already exists: $rg"
    fi
}

# Function to create Azure Cosmos DB for NoSQL account with vector search capability
create_cosmosdb_account() {
    echo "Creating Azure Cosmos DB for NoSQL account '$account_name'..."
    echo "This may take several minutes..."

    # Check if Cosmos DB account already exists
    local account_exists=$(az cosmosdb show --resource-group $rg --name $account_name 2>/dev/null)
    if [ -z "$account_exists" ]; then
        # Create Cosmos DB account with serverless capacity mode and vector search capability
        # EnableNoSQLVectorSearch enables the VectorDistance function for similarity queries
        az cosmosdb create \
            --resource-group $rg \
            --name $account_name \
            --locations regionName=$location \
            --capabilities EnableServerless EnableNoSQLVectorSearch \
            --default-consistency-level Session > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Cosmos DB account created with vector search capability"
        else
            echo "Error: Failed to create Cosmos DB account"
            return 1
        fi
    else
        echo "✓ Cosmos DB account already exists: $account_name"
    fi

    # Create database
    echo "Creating database '$database_name'..."
    local db_exists=$(az cosmosdb sql database show --resource-group $rg --account-name $account_name --name $database_name 2>/dev/null)
    if [ -z "$db_exists" ]; then
        az cosmosdb sql database create \
            --resource-group $rg \
            --account-name $account_name \
            --name $database_name > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Database created: $database_name"
        else
            echo "Error: Failed to create database"
            return 1
        fi
    else
        echo "✓ Database already exists: $database_name"
    fi

    echo ""
    echo "Use option 2 to configure Entra ID access."
}

# Function to configure Entra ID RBAC for the signed-in user
configure_entra_access() {
    echo "Configuring Microsoft Entra ID access..."

    # Prereq check: Cosmos DB account must exist
    local status=$(az cosmosdb show --resource-group $rg --name $account_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$status" ]; then
        echo "Error: Cosmos DB account '$account_name' not found."
        echo "Please run option 1 to create the Cosmos DB account, then try again."
        return 1
    fi

    if [ "$status" != "Succeeded" ]; then
        echo "Error: Cosmos DB account is not ready (current state: $status)."
        echo "Please wait for deployment to complete. Use option 4 to check status."
        return 1
    fi

    # Get the signed-in user's UPN
    local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

    if [ -z "$user_object_id" ] || [ -z "$user_upn" ]; then
        echo "Error: Unable to retrieve signed-in user information."
        echo "Please ensure you are logged in with 'az login'."
        return 1
    fi

    local account_id=$(az cosmosdb show --resource-group $rg --name $account_name --query "id" -o tsv)

    # Assign Azure RBAC Contributor role (for control plane: create/delete databases, containers)
    echo "Assigning Azure RBAC 'Contributor' role to '$user_upn'..."
    local azure_role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $account_id \
        --role "Contributor" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -n "$azure_role_exists" ]; then
        echo "✓ Azure RBAC Contributor role already assigned"
    else
        az role assignment create \
            --assignee $user_object_id \
            --scope $account_id \
            --role "Contributor" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Azure RBAC Contributor role assigned"
        else
            echo "Error: Failed to assign Azure RBAC Contributor role"
            return 1
        fi
    fi

    # Assign Cosmos DB Built-in Data Contributor role (for data plane: read/write items)
    echo "Assigning 'Cosmos DB Built-in Data Contributor' role to '$user_upn'..."

    # Use the built-in role name for better maintainability
    local cosmos_role_name="Cosmos DB Built-in Data Contributor"

    # Check if role assignment already exists
    local cosmos_role_exists=$(az cosmosdb sql role assignment list \
        --resource-group $rg \
        --account-name $account_name \
        --query "[?principalId=='$user_object_id']" \
        -o tsv 2>/dev/null)

    if [ -n "$cosmos_role_exists" ]; then
        echo "✓ Cosmos DB Data Contributor role already assigned"
    else
        az cosmosdb sql role assignment create \
            --resource-group $rg \
            --account-name $account_name \
            --role-definition-name "$cosmos_role_name" \
            --principal-id $user_object_id \
            --scope $account_id > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Cosmos DB Data Contributor role assigned"
        else
            echo "Error: Failed to assign Cosmos DB Data Contributor role"
            return 1
        fi
    fi

    echo ""
    echo "Entra ID access configured for: $user_upn"
    echo "  - Azure RBAC Contributor: manage databases and containers"
    echo "  - Cosmos DB Data Contributor: read/write data"
}

# Function to retrieve connection info and set environment variables
retrieve_connection_info() {
    echo "Retrieving connection information..."

    # Prereq check: Cosmos DB account must exist
    local account_exists=$(az cosmosdb show --resource-group $rg --name $account_name 2>/dev/null)
    if [ -z "$account_exists" ]; then
        echo "Error: Cosmos DB account '$account_name' not found."
        echo "Please run option 1 to create the Cosmos DB account, then try again."
        return 1
    fi

    # Prereq check: Both RBAC roles must be configured
    local account_id=$(az cosmosdb show --resource-group $rg --name $account_name --query "id" -o tsv)
    local cosmos_role=$(az cosmosdb sql role assignment list \
        --resource-group $rg \
        --account-name $account_name \
        --query "[?principalId=='$user_object_id']" \
        -o tsv 2>/dev/null)

    if [ -z "$cosmos_role" ]; then
        echo "Error: Entra ID access not configured for this account."
        echo "Please run option 2 to configure Entra ID access, then try again."
        return 1
    fi

    # Get endpoint
    local endpoint=$(az cosmosdb show --resource-group $rg --name $account_name --query "documentEndpoint" -o tsv 2>/dev/null)

    if [ -z "$endpoint" ]; then
        echo "Error: Unable to retrieve connection information."
        return 1
    fi

    local env_file="$(dirname "$0")/.env"

    # Create or update .env file with export statements (no key needed for Entra auth)
    cat > "$env_file" << EOF
export COSMOS_ENDPOINT="$endpoint"
export COSMOS_DATABASE="$database_name"
export COSMOS_CONTAINER="$container_name"
EOF

    echo ""
    echo "Cosmos DB Connection Information"
    echo "==========================================================="
    echo "Endpoint: $endpoint"
    echo "Database: $database_name"
    echo "Container: $container_name"
    echo "Authentication: Microsoft Entra ID (DefaultAzureCredential)"
    echo ""
    echo "Environment variables saved to: $env_file"
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    # Check Cosmos DB account
    echo "Cosmos DB Account ($account_name):"
    local status=$(az cosmosdb show --resource-group $rg --name $account_name --query "provisioningState" -o tsv 2>/dev/null)

    if [ -z "$status" ]; then
        echo "  Status: Not created"
    else
        echo "  Status: $status"
        if [ "$status" = "Succeeded" ]; then
            echo "  ✓ Cosmos DB account is ready"

            # Check for vector search capability
            local capabilities=$(az cosmosdb show --resource-group $rg --name $account_name --query "capabilities[].name" -o tsv 2>/dev/null)
            if echo "$capabilities" | grep -q "EnableNoSQLVectorSearch"; then
                echo "  ✓ Vector search capability enabled"
            else
                echo "  ⚠ Vector search capability not enabled"
            fi

            # Check database
            local db_status=$(az cosmosdb sql database show --resource-group $rg --account-name $account_name --name $database_name 2>/dev/null)
            if [ -n "$db_status" ]; then
                echo "  ✓ Database: $database_name"
            else
                echo "  ⚠ Database not created"
            fi

            # Check Entra ID RBAC
            local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)
            local account_id=$(az cosmosdb show --resource-group $rg --name $account_name --query "id" -o tsv)

            # Check Azure RBAC
            local azure_role=$(az role assignment list \
                --assignee $user_object_id \
                --scope $account_id \
                --role "Contributor" \
                --query "[0].id" -o tsv 2>/dev/null)

            # Check Cosmos DB data plane RBAC
            local cosmos_role=$(az cosmosdb sql role assignment list \
                --resource-group $rg \
                --account-name $account_name \
                --query "[?principalId=='$user_object_id']" \
                -o tsv 2>/dev/null)

            if [ -n "$azure_role" ] && [ -n "$cosmos_role" ]; then
                echo "  ✓ Entra ID access: $user_upn (full control)"
            elif [ -n "$cosmos_role" ]; then
                echo "  ⚠ Entra ID access: $user_upn (data only, missing Azure RBAC)"
            elif [ -n "$azure_role" ]; then
                echo "  ⚠ Entra ID access: $user_upn (control plane only, missing data role)"
            else
                echo "  ⚠ Entra ID access not configured"
            fi
        fi
    fi
}

# Display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    Azure Cosmos DB Vector Search Deployment Menu"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Account Name: $account_name"
    echo "Location: $location"
    echo "====================================================================="
    echo "1. Create Cosmos DB account (with vector search capability)"
    echo "2. Configure Entra ID access"
    echo "3. Check deployment status"
    echo "4. Retrieve connection info"
    echo "5. Exit"
    echo "====================================================================="
}

# Main menu loop
while true; do
    show_menu
    read -p "Please select an option (1-5): " choice

    case $choice in
        1)
            echo ""
            create_resource_group
            echo ""
            create_cosmosdb_account
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            configure_entra_access
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
            echo ""
            retrieve_connection_info
            echo ""
            read -p "Press Enter to continue..."
            ;;
        5)
            echo "Exiting..."
            clear
            exit 0
            ;;
        *)
            echo ""
            echo "Invalid option. Please select 1-5."
            echo ""
            read -p "Press Enter to continue..."
            ;;
    esac

    echo ""
done

