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
law_name="law-exercise-${user_hash}"
appinsights_name="appi-exercise-${user_hash}"

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

# Function to create Application Insights with a Log Analytics workspace
create_application_insights() {
    echo "Creating Log Analytics workspace '$law_name'..."

    local law_exists=$(az monitor log-analytics workspace show --resource-group $rg --workspace-name $law_name --query "name" -o tsv 2>/dev/null)
    if [ -z "$law_exists" ]; then
        az monitor log-analytics workspace create \
            --resource-group $rg \
            --workspace-name $law_name \
            --location $location > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Log Analytics workspace created: $law_name"
        else
            echo "Error: Failed to create Log Analytics workspace"
            return 1
        fi
    else
        echo "✓ Log Analytics workspace already exists: $law_name"
    fi

    echo ""
    echo "Creating Application Insights '$appinsights_name'..."

    local appi_exists=$(az monitor app-insights component show --resource-group $rg --app $appinsights_name --query "name" -o tsv 2>/dev/null)
    if [ -z "$appi_exists" ]; then
        local law_id=$(az monitor log-analytics workspace show --resource-group $rg --workspace-name $law_name --query "id" -o tsv)

        az monitor app-insights component create \
            --resource-group $rg \
            --app $appinsights_name \
            --location $location \
            --workspace "$law_id" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Application Insights created: $appinsights_name"
        else
            echo "Error: Failed to create Application Insights"
            return 1
        fi
    else
        echo "✓ Application Insights already exists: $appinsights_name"
    fi

    echo ""
    echo "Use option 2 to assign the role."
}

# Function to assign Monitoring Metrics Publisher role
assign_role() {
    echo "Assigning Monitoring Metrics Publisher role..."

    # Prereq check: Application Insights must exist
    local appi_exists=$(az monitor app-insights component show --resource-group $rg --app $appinsights_name --query "name" -o tsv 2>/dev/null)
    if [ -z "$appi_exists" ]; then
        echo "Error: Application Insights '$appinsights_name' not found."
        echo "Please run option 1 to create the resource, then try again."
        return 1
    fi

    # Get the signed-in user's UPN
    local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

    if [ -z "$user_object_id" ] || [ -z "$user_upn" ]; then
        echo "Error: Unable to retrieve signed-in user information."
        echo "Please ensure you are logged in with 'az login'."
        return 1
    fi

    local appi_id=$(az monitor app-insights component show --resource-group $rg --app $appinsights_name --query "id" -o tsv)

    # Check if role is already assigned
    local role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $appi_id \
        --role "Monitoring Metrics Publisher" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -n "$role_exists" ]; then
        echo "✓ Monitoring Metrics Publisher role already assigned"
    else
        az role assignment create \
            --role "Monitoring Metrics Publisher" \
            --assignee "$user_object_id" \
            --scope "$appi_id" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Monitoring Metrics Publisher role assigned"
        else
            echo "Error: Failed to assign Monitoring Metrics Publisher role"
            return 1
        fi
    fi

    echo ""
    echo "Role configured for: $user_upn"
    echo "  - Monitoring Metrics Publisher: publish telemetry using Entra authentication"
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    echo "Log Analytics Workspace ($law_name):"
    local law_status=$(az monitor log-analytics workspace show --resource-group $rg --workspace-name $law_name --query "provisioningState" -o tsv 2>/dev/null)

    if [ -z "$law_status" ]; then
        echo "  Status: Not created"
    else
        echo "  Status: $law_status"
        if [ "$law_status" = "Succeeded" ]; then
            echo "  ✓ Log Analytics workspace is ready"
        else
            echo "  ⚠ Log Analytics workspace is still provisioning. Please wait and try again."
        fi
    fi

    echo ""
    echo "Application Insights ($appinsights_name):"
    local appi_status=$(az monitor app-insights component show --resource-group $rg --app $appinsights_name --query "provisioningState" -o tsv 2>/dev/null)

    if [ -z "$appi_status" ]; then
        echo "  Status: Not created"
    else
        echo "  Status: $appi_status"
        if [ "$appi_status" = "Succeeded" ]; then
            echo "  ✓ Application Insights is ready"
            local conn_string=$(az monitor app-insights component show --resource-group $rg --app $appinsights_name --query "connectionString" -o tsv 2>/dev/null)
            echo "  Connection string: ${conn_string:0:60}..."
        else
            echo "  ⚠ Application Insights is still provisioning. Please wait and try again."
        fi
    fi

    # Check role assignment
    echo ""
    echo "Role Assignment:"
    local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)
    local appi_id=$(az monitor app-insights component show --resource-group $rg --app $appinsights_name --query "id" -o tsv 2>/dev/null)

    if [ -n "$appi_id" ]; then
        local role_exists=$(az role assignment list \
            --assignee $user_object_id \
            --scope $appi_id \
            --role "Monitoring Metrics Publisher" \
            --query "[0].id" -o tsv 2>/dev/null)

        if [ -n "$role_exists" ]; then
            echo "  ✓ Role assigned: $user_upn (Monitoring Metrics Publisher)"
        else
            echo "  ⚠ Role not assigned"
        fi
    else
        echo "  ⚠ Application Insights not created yet"
    fi
}

# Function to retrieve connection info and create .env file
retrieve_connection_info() {
    echo "Retrieving connection information..."

    # Prereq check: Application Insights must exist
    local appi_exists=$(az monitor app-insights component show --resource-group $rg --app $appinsights_name --query "name" -o tsv 2>/dev/null)
    if [ -z "$appi_exists" ]; then
        echo "Error: Application Insights '$appinsights_name' not found."
        echo "Please run option 1 to create the resource, then try again."
        return 1
    fi

    # Prereq check: role must be assigned
    local appi_id=$(az monitor app-insights component show --resource-group $rg --app $appinsights_name --query "id" -o tsv)
    local role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $appi_id \
        --role "Monitoring Metrics Publisher" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -z "$role_exists" ]; then
        echo "Error: Monitoring Metrics Publisher role not assigned."
        echo "Please run option 2 to assign the role, then try again."
        return 1
    fi

    # Get the connection string
    local conn_string=$(az monitor app-insights component show --resource-group $rg --app $appinsights_name --query "connectionString" -o tsv 2>/dev/null)

    local env_file="$(dirname "$0")/.env"

    cat > "$env_file" << EOF
export APPLICATIONINSIGHTS_CONNECTION_STRING="$conn_string"
EOF

    echo ""
    echo "Application Insights Connection Information"
    echo "==========================================================="
    echo "Connection string: ${conn_string:0:60}..."
    echo "Authentication: Microsoft Entra ID (DefaultAzureCredential)"
    echo ""
    echo "Environment variables saved to: $env_file"
}

# Display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    OpenTelemetry Exercise - Deployment Script"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Location: $location"
    echo "Log Analytics: $law_name"
    echo "App Insights: $appinsights_name"
    echo "====================================================================="
    echo "1. Create Application Insights"
    echo "2. Assign role"
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
            create_application_insights
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
