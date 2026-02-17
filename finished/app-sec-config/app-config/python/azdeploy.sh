#!/usr/bin/env bash

# Change the values of these variables as needed

# rg="<your-resource-group-name>"  # Resource Group name
# location="<your-azure-region>"   # Azure region for the resources

rg="rg-exercises"           # Resource Group name
location="eastus2"          # Azure region for the resources

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
appconfig_name="appconfig-exercise-${user_hash}"
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

# Function to create App Configuration store
create_app_configuration() {
    echo "Creating App Configuration store '$appconfig_name'..."

    local ac_exists=$(az appconfig show --resource-group $rg --name $appconfig_name 2>/dev/null)
    if [ -z "$ac_exists" ]; then
        az appconfig create \
            --name $appconfig_name \
            --resource-group $rg \
            --location $location \
            --sku Standard > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ App Configuration store created: $appconfig_name"
        else
            echo "Error: Failed to create App Configuration store"
            return 1
        fi
    else
        echo "✓ App Configuration store already exists: $appconfig_name"
    fi

    echo ""
    echo "Use option 2 to create Key Vault."
}

# Function to create Key Vault with RBAC authorization
create_key_vault() {
    echo "Creating Key Vault '$kv_name'..."

    local kv_exists=$(az keyvault show --resource-group $rg --name $kv_name 2>/dev/null)
    if [ -z "$kv_exists" ]; then
        # Check for a soft-deleted vault with the same name and recover it
        local soft_deleted=$(az keyvault show-deleted --name $kv_name --query "name" -o tsv 2>/dev/null)
        if [ -n "$soft_deleted" ]; then
            echo "  Recovering soft-deleted Key Vault '$kv_name'..."
            az keyvault recover --name $kv_name > /dev/null 2>&1
            if [ $? -eq 0 ]; then
                echo "✓ Key Vault recovered: $kv_name"
            else
                echo "Error: Failed to recover soft-deleted Key Vault."
                echo "You may need to purge it first: az keyvault purge --name $kv_name"
                return 1
            fi
        else
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
        fi
    else
        echo "✓ Key Vault already exists: $kv_name"
    fi

    echo ""
    echo "Use option 3 to assign roles."
}

# Function to assign App Configuration Data Owner and Key Vault Secrets Officer roles
assign_roles() {
    echo "Assigning roles..."

    # Get the signed-in user's UPN
    local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

    if [ -z "$user_object_id" ] || [ -z "$user_upn" ]; then
        echo "Error: Unable to retrieve signed-in user information."
        echo "Please ensure you are logged in with 'az login'."
        return 1
    fi

    # Assign App Configuration Data Owner role
    local ac_status=$(az appconfig show --resource-group $rg --name $appconfig_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$ac_status" ]; then
        echo "Error: App Configuration store '$appconfig_name' not found."
        echo "Please run option 1 to create the store, then try again."
        return 1
    fi

    local ac_id=$(az appconfig show --resource-group $rg --name $appconfig_name --query "id" -o tsv)

    local ac_role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $ac_id \
        --role "App Configuration Data Owner" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -n "$ac_role_exists" ]; then
        echo "✓ App Configuration Data Owner role already assigned"
    else
        az role assignment create \
            --role "App Configuration Data Owner" \
            --assignee "$user_object_id" \
            --scope "$ac_id" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ App Configuration Data Owner role assigned"
        else
            echo "Error: Failed to assign App Configuration Data Owner role"
            return 1
        fi
    fi

    # Assign Key Vault Secrets Officer role
    local kv_status=$(az keyvault show --resource-group $rg --name $kv_name --query "properties.provisioningState" -o tsv 2>/dev/null)
    if [ -z "$kv_status" ]; then
        echo "Error: Key Vault '$kv_name' not found."
        echo "Please run option 2 to create the vault, then try again."
        return 1
    fi

    local kv_id=$(az keyvault show --resource-group $rg --name $kv_name --query "id" -o tsv)

    local kv_role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $kv_id \
        --role "Key Vault Secrets Officer" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -n "$kv_role_exists" ]; then
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
    echo "Roles configured for: $user_upn"
    echo "  - App Configuration Data Owner: read, create, and update settings"
    echo "  - Key Vault Secrets Officer: read, create, update, and delete secrets"
}

# Function to store settings, secrets, and Key Vault references
store_settings() {
    echo "Storing configuration settings..."

    # Prereq check: App Configuration store must exist
    local ac_status=$(az appconfig show --resource-group $rg --name $appconfig_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$ac_status" ]; then
        echo "Error: App Configuration store '$appconfig_name' not found."
        echo "Please run option 1 to create the store, then try again."
        return 1
    fi

    if [ "$ac_status" != "Succeeded" ]; then
        echo "Error: App Configuration store is not ready (current state: $ac_status)."
        echo "Please wait for deployment to complete. Use option 5 to check status."
        return 1
    fi

    # Prereq check: Key Vault must exist and be ready
    local kv_status=$(az keyvault show --resource-group $rg --name $kv_name --query "properties.provisioningState" -o tsv 2>/dev/null)
    if [ -z "$kv_status" ]; then
        echo "Error: Key Vault '$kv_name' not found."
        echo "Please run option 2 to create the vault, then try again."
        return 1
    fi

    if [ "$kv_status" != "Succeeded" ]; then
        echo "Error: Key Vault is not ready (current state: $kv_status)."
        echo "Please wait for deployment to complete. Use option 5 to check status."
        return 1
    fi

    # Store default (unlabeled) configuration settings
    az appconfig kv set --name $appconfig_name --key "OpenAI:Endpoint" \
        --value "https://my-openai.openai.azure.com/" --yes > /dev/null 2>&1
    echo "✓ Setting stored: OpenAI:Endpoint (no label)"

    az appconfig kv set --name $appconfig_name --key "OpenAI:DeploymentName" \
        --value "gpt-4o" --yes > /dev/null 2>&1
    echo "✓ Setting stored: OpenAI:DeploymentName (no label)"

    az appconfig kv set --name $appconfig_name --key "Pipeline:BatchSize" \
        --value "10" --yes > /dev/null 2>&1
    echo "✓ Setting stored: Pipeline:BatchSize = 10 (no label)"

    az appconfig kv set --name $appconfig_name --key "Pipeline:RetryCount" \
        --value "3" --yes > /dev/null 2>&1
    echo "✓ Setting stored: Pipeline:RetryCount = 3 (no label)"

    # Store Production-labeled overrides
    az appconfig kv set --name $appconfig_name --key "Pipeline:BatchSize" \
        --value "200" --label "Production" --yes > /dev/null 2>&1
    echo "✓ Setting stored: Pipeline:BatchSize = 200 (Production)"

    az appconfig kv set --name $appconfig_name --key "Pipeline:RetryCount" \
        --value "5" --label "Production" --yes > /dev/null 2>&1
    echo "✓ Setting stored: Pipeline:RetryCount = 5 (Production)"

    # Store sentinel key for dynamic refresh
    az appconfig kv set --name $appconfig_name --key "Sentinel" \
        --value "1" --yes > /dev/null 2>&1
    echo "✓ Setting stored: Sentinel = 1"

    # Store secret in Key Vault
    az keyvault secret set \
        --vault-name $kv_name \
        --name "openai-api-key" \
        --value "sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx" \
        --content-type "application/x-api-key" > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        echo "✓ Secret stored in Key Vault: openai-api-key"
    else
        echo "Error: Failed to store openai-api-key secret in Key Vault"
        return 1
    fi

    # Create Key Vault reference in App Configuration
    local secret_uri=$(az keyvault secret show --vault-name $kv_name --name "openai-api-key" --query "id" -o tsv 2>/dev/null)

    az appconfig kv set-keyvault \
        --name $appconfig_name \
        --key "OpenAI:ApiKey" \
        --secret-identifier "$secret_uri" \
        --yes > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        echo "✓ Key Vault reference created: OpenAI:ApiKey → openai-api-key"
    else
        echo "Error: Failed to create Key Vault reference"
        return 1
    fi

    echo ""
    echo "Use option 5 to check deployment status."
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    # Check App Configuration store
    echo "App Configuration ($appconfig_name):"
    local ac_status=$(az appconfig show --resource-group $rg --name $appconfig_name --query "provisioningState" -o tsv 2>/dev/null)

    if [ -z "$ac_status" ]; then
        echo "  Status: Not created"
    else
        echo "  Status: $ac_status"
        if [ "$ac_status" = "Succeeded" ]; then
            echo "  ✓ App Configuration store is ready"
            local ac_endpoint=$(az appconfig show --resource-group $rg --name $appconfig_name --query "endpoint" -o tsv 2>/dev/null)
            echo "  Endpoint: $ac_endpoint"

            # Check settings
            echo ""
            echo "  Settings:"

            local setting_count=$(az appconfig kv list --name $appconfig_name --query "length(@)" -o tsv 2>/dev/null)
            if [ -n "$setting_count" ] && [ "$setting_count" -gt 0 ]; then
                echo "  ✓ $setting_count setting(s) stored"
            else
                echo "  ⚠ No settings stored"
            fi

            # Check Key Vault reference
            local kv_ref=$(az appconfig kv list --name $appconfig_name --key "OpenAI:ApiKey" --query "[0].contentType" -o tsv 2>/dev/null)
            if [ -n "$kv_ref" ]; then
                echo "  ✓ Key Vault reference: OpenAI:ApiKey"
            else
                echo "  ⚠ Key Vault reference not found: OpenAI:ApiKey"
            fi
        else
            echo "  ⚠ App Configuration store is still provisioning. Please wait and try again."
        fi
    fi

    echo ""

    # Check Key Vault
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

            # Check secret
            echo ""
            echo "  Secrets:"
            local api_key_exists=$(az keyvault secret show --vault-name $kv_name --name "openai-api-key" --query "name" -o tsv 2>/dev/null)
            if [ -n "$api_key_exists" ]; then
                echo "  ✓ Secret stored: openai-api-key"
            else
                echo "  ⚠ Secret not stored: openai-api-key"
            fi
        else
            echo "  ⚠ Key Vault is still provisioning. Please wait and try again."
        fi
    fi

    # Check role assignments
    echo ""
    echo "Role Assignments:"
    local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

    local ac_id=$(az appconfig show --resource-group $rg --name $appconfig_name --query "id" -o tsv 2>/dev/null)
    if [ -n "$ac_id" ]; then
        local ac_role_exists=$(az role assignment list \
            --assignee $user_object_id \
            --scope $ac_id \
            --role "App Configuration Data Owner" \
            --query "[0].id" -o tsv 2>/dev/null)

        if [ -n "$ac_role_exists" ]; then
            echo "  ✓ Role assigned: $user_upn (App Configuration Data Owner)"
        else
            echo "  ⚠ App Configuration Data Owner role not assigned"
        fi
    fi

    local kv_id=$(az keyvault show --resource-group $rg --name $kv_name --query "id" -o tsv 2>/dev/null)
    if [ -n "$kv_id" ]; then
        local kv_role_exists=$(az role assignment list \
            --assignee $user_object_id \
            --scope $kv_id \
            --role "Key Vault Secrets Officer" \
            --query "[0].id" -o tsv 2>/dev/null)

        if [ -n "$kv_role_exists" ]; then
            echo "  ✓ Role assigned: $user_upn (Key Vault Secrets Officer)"
        else
            echo "  ⚠ Key Vault Secrets Officer role not assigned"
        fi
    fi
}

# Function to retrieve connection info and create .env file
retrieve_connection_info() {
    echo "Retrieving connection information..."

    # Prereq check: App Configuration store must exist
    local ac_exists=$(az appconfig show --resource-group $rg --name $appconfig_name 2>/dev/null)
    if [ -z "$ac_exists" ]; then
        echo "Error: App Configuration store '$appconfig_name' not found."
        echo "Please run option 1 to create the store, then try again."
        return 1
    fi

    # Prereq check: roles must be assigned
    local ac_id=$(az appconfig show --resource-group $rg --name $appconfig_name --query "id" -o tsv)
    local ac_role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $ac_id \
        --role "App Configuration Data Owner" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -z "$ac_role_exists" ]; then
        echo "Error: App Configuration Data Owner role not assigned."
        echo "Please run option 3 to assign roles, then try again."
        return 1
    fi

    # Get the App Configuration endpoint
    local ac_endpoint=$(az appconfig show --resource-group $rg --name $appconfig_name --query "endpoint" -o tsv 2>/dev/null)

    local env_file="$(dirname "$0")/.env"

    cat > "$env_file" << EOF
export AZURE_APPCONFIG_ENDPOINT="$ac_endpoint"
EOF

    echo ""
    echo "App Configuration Connection Information"
    echo "==========================================================="
    echo "Endpoint: $ac_endpoint"
    echo "Authentication: Microsoft Entra ID (DefaultAzureCredential)"
    echo ""
    echo "Environment variables saved to: $env_file"
}

# Display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    App Configuration Exercise - Deployment Script"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Location: $location"
    echo "App Configuration: $appconfig_name"
    echo "Key Vault: $kv_name"
    echo "====================================================================="
    echo "1. Create App Configuration"
    echo "2. Create Key Vault"
    echo "3. Assign roles"
    echo "4. Store sample settings"
    echo "5. Check deployment status"
    echo "6. Retrieve connection info"
    echo "7. Exit"
    echo "====================================================================="
}

# Main menu loop
while true; do
    show_menu
    read -p "Please select an option (1-7): " choice

    case $choice in
        1)
            echo ""
            create_resource_group
            echo ""
            create_app_configuration
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            create_resource_group
            echo ""
            create_key_vault
            echo ""
            read -p "Press Enter to continue..."
            ;;
        3)
            echo ""
            assign_roles
            echo ""
            read -p "Press Enter to continue..."
            ;;
        4)
            echo ""
            store_settings
            echo ""
            read -p "Press Enter to continue..."
            ;;
        5)
            echo ""
            check_deployment_status
            echo ""
            read -p "Press Enter to continue..."
            ;;
        6)
            echo ""
            retrieve_connection_info
            echo ""
            read -p "Press Enter to continue..."
            ;;
        7)
            echo "Exiting..."
            clear
            exit 0
            ;;
        *)
            echo ""
            echo "Invalid option. Please select 1-7."
            echo ""
            read -p "Press Enter to continue..."
            ;;
    esac

    echo ""
done
