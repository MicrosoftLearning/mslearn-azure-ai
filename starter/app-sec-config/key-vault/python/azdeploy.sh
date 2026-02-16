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

# Resource names with hash for uniqueness
kv_name="kv-exercise-${user_hash}"

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

# Function to create Key Vault with RBAC authorization
create_key_vault() {
    echo "Creating Key Vault '$kv_name'..."

    local kv_exists=$(az keyvault show --resource-group $rg --name $kv_name 2>/dev/null)
    if [ -z "$kv_exists" ]; then
        az keyvault create \
            --name $kv_name \
            --resource-group $rg \
            --location $location \
            --enable-rbac-authorization true > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Key Vault created: $kv_name"
        else
            echo "Error: Failed to create Key Vault"
            return 1
        fi
    else
        echo "✓ Key Vault already exists: $kv_name"
    fi

    echo ""
    echo "Use option 2 to assign the role."
}

# Function to store sample secrets in the vault
store_secrets() {
    echo "Storing sample secrets..."

    # Prereq check: vault must exist and be ready
    local status=$(az keyvault show --resource-group $rg --name $kv_name --query "properties.provisioningState" -o tsv 2>/dev/null)
    if [ -z "$status" ]; then
        echo "Error: Key Vault '$kv_name' not found."
        echo "Please run option 1 to create the vault, then try again."
        return 1
    fi

    if [ "$status" != "Succeeded" ]; then
        echo "Error: Key Vault is not ready (current state: $status)."
        echo "Please wait for deployment to complete. Use option 4 to check status."
        return 1
    fi

    # Store openai-api-key secret
    az keyvault secret set \
        --vault-name $kv_name \
        --name "openai-api-key" \
        --value "sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx" \
        --content-type "application/x-api-key" \
        --tags environment=development service=openai > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        echo "✓ Secret stored: openai-api-key"
    else
        echo "Error: Failed to store openai-api-key secret"
        return 1
    fi

    # Store cosmosdb-connection-string secret
    az keyvault secret set \
        --vault-name $kv_name \
        --name "cosmosdb-connection-string" \
        --value "AccountEndpoint=https://mycosmosdb.documents.azure.com:443/;AccountKey=abc123def456ghi789==" \
        --content-type "application/x-connection-string" \
        --tags environment=development service=cosmosdb > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        echo "✓ Secret stored: cosmosdb-connection-string"
    else
        echo "Error: Failed to store cosmosdb-connection-string secret"
        return 1
    fi

    echo ""
    echo "Use option 4 to check deployment status."
}

# Function to assign Key Vault Secrets Officer role
assign_role() {
    echo "Assigning Key Vault Secrets Officer role..."

    # Prereq check: vault must exist
    local status=$(az keyvault show --resource-group $rg --name $kv_name --query "properties.provisioningState" -o tsv 2>/dev/null)
    if [ -z "$status" ]; then
        echo "Error: Key Vault '$kv_name' not found."
        echo "Please run option 1 to create the vault, then try again."
        return 1
    fi

    if [ "$status" != "Succeeded" ]; then
        echo "Error: Key Vault is not ready (current state: $status)."
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

    local kv_id=$(az keyvault show --resource-group $rg --name $kv_name --query "id" -o tsv)

    # Check if role is already assigned
    local role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $kv_id \
        --role "Key Vault Secrets Officer" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -n "$role_exists" ]; then
        echo "✓ Key Vault Secrets Officer role already assigned"
    else
        az role assignment create \
            --role "Key Vault Secrets Officer" \
            --assignee "$user_object_id" \
            --scope "$kv_id" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Key Vault Secrets Officer role assigned"
        else
            echo "Error: Failed to assign Key Vault Secrets Officer role"
            return 1
        fi
    fi

    echo ""
    echo "Role configured for: $user_upn"
    echo "  - Key Vault Secrets Officer: read, create, update, and delete secrets"
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    echo "Key Vault ($kv_name):"
    local kv_status=$(az keyvault show --resource-group $rg --name $kv_name --query "properties.provisioningState" -o tsv 2>/dev/null)

    if [ -z "$kv_status" ]; then
        echo "  Status: Not created"
    else
        echo "  Status: $kv_status"
        if [ "$kv_status" = "Succeeded" ]; then
            echo "  ✓ Key Vault is ready"
            local kv_uri=$(az keyvault show --resource-group $rg --name $kv_name --query "properties.vaultUri" -o tsv 2>/dev/null)
            echo "  Vault URI: $kv_uri"

            # Check secrets
            echo ""
            echo "Secrets:"

            local api_key_exists=$(az keyvault secret show --vault-name $kv_name --name "openai-api-key" --query "name" -o tsv 2>/dev/null)
            if [ -n "$api_key_exists" ]; then
                echo "  ✓ Secret stored: openai-api-key"
            else
                echo "  ⚠ Secret not stored: openai-api-key"
            fi

            local conn_str_exists=$(az keyvault secret show --vault-name $kv_name --name "cosmosdb-connection-string" --query "name" -o tsv 2>/dev/null)
            if [ -n "$conn_str_exists" ]; then
                echo "  ✓ Secret stored: cosmosdb-connection-string"
            else
                echo "  ⚠ Secret not stored: cosmosdb-connection-string"
            fi

            # Check role assignment
            echo ""
            echo "Role Assignment:"
            local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)
            local kv_id=$(az keyvault show --resource-group $rg --name $kv_name --query "id" -o tsv)

            local role_exists=$(az role assignment list \
                --assignee $user_object_id \
                --scope $kv_id \
                --role "Key Vault Secrets Officer" \
                --query "[0].id" -o tsv 2>/dev/null)

            if [ -n "$role_exists" ]; then
                echo "  ✓ Role assigned: $user_upn (Key Vault Secrets Officer)"
            else
                echo "  ⚠ Role not assigned"
            fi
        else
            echo "  ⚠ Key Vault is still provisioning. Please wait and try again."
        fi
    fi
}

# Function to retrieve connection info and create .env file
retrieve_connection_info() {
    echo "Retrieving connection information..."

    # Prereq check: vault must exist
    local kv_exists=$(az keyvault show --resource-group $rg --name $kv_name 2>/dev/null)
    if [ -z "$kv_exists" ]; then
        echo "Error: Key Vault '$kv_name' not found."
        echo "Please run option 1 to create the vault, then try again."
        return 1
    fi

    # Prereq check: role must be assigned
    local kv_id=$(az keyvault show --resource-group $rg --name $kv_name --query "id" -o tsv)
    local role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $kv_id \
        --role "Key Vault Secrets Officer" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -z "$role_exists" ]; then
        echo "Error: Key Vault Secrets Officer role not assigned."
        echo "Please run option 3 to assign the role, then try again."
        return 1
    fi

    # Get the vault URI
    local kv_uri=$(az keyvault show --resource-group $rg --name $kv_name --query "properties.vaultUri" -o tsv 2>/dev/null)

    local env_file="$(dirname "$0")/.env"

    cat > "$env_file" << EOF
export KEY_VAULT_URL="$kv_uri"
EOF

    echo ""
    echo "Key Vault Connection Information"
    echo "==========================================================="
    echo "Vault URL: $kv_uri"
    echo "Authentication: Microsoft Entra ID (DefaultAzureCredential)"
    echo ""
    echo "Environment variables saved to: $env_file"
}

# Display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    Key Vault Secrets Exercise - Deployment Script"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Location: $location"
    echo "Key Vault: $kv_name"
    echo "====================================================================="
    echo "1. Create Key Vault"
    echo "2. Assign role"
    echo "3. Store secrets"
    echo "4. Check deployment status"
    echo "5. Retrieve connection info"
    echo "6. Exit"
    echo "====================================================================="
}

# Main menu loop
while true; do
    show_menu
    read -p "Please select an option (1-6): " choice

    case $choice in
        1)
            echo ""
            create_resource_group
            echo ""
            create_key_vault
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            assign_role
            echo ""
            read -p "Press Enter to continue..."
            ;;
        3)
            echo ""
            store_secrets
            echo ""
            read -p "Press Enter to continue..."
            ;;
        4)
            echo ""
            check_deployment_status
            echo ""
            read -p "Press Enter to continue..."
            ;;
        5)
            echo ""
            retrieve_connection_info
            echo ""
            read -p "Press Enter to continue..."
            ;;
        6)
            echo "Exiting..."
            clear
            exit 0
            ;;
        *)
            echo ""
            echo "Invalid option. Please select 1-6."
            echo ""
            read -p "Press Enter to continue..."
            ;;
    esac

    echo ""
done
