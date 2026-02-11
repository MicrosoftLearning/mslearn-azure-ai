#!/usr/bin/env bash

# Change the values of these variables as needed

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
namespace_name="sbns-exercise-${user_hash}"

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

# Function to create Service Bus namespace
create_servicebus_namespace() {
    echo "Creating Service Bus namespace '$namespace_name'..."

    local ns_exists=$(az servicebus namespace show --resource-group $rg --name $namespace_name 2>/dev/null)
    if [ -z "$ns_exists" ]; then
        az servicebus namespace create \
            --name $namespace_name \
            --resource-group $rg \
            --location $location \
            --sku Standard > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Service Bus namespace created: $namespace_name"
        else
            echo "Error: Failed to create Service Bus namespace"
            return 1
        fi
    else
        echo "✓ Service Bus namespace already exists: $namespace_name"
    fi

    echo ""
    echo "Use option 2 to assign the data plane role."
}

# Function to assign Azure Service Bus Data Owner role
assign_role() {
    echo "Assigning Azure Service Bus Data Owner role..."

    # Prereq check: namespace must exist
    local status=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ -z "$status" ]; then
        echo "Error: Service Bus namespace '$namespace_name' not found."
        echo "Please run option 1 to create the namespace, then try again."
        return 1
    fi

    if [ "$status" != "Succeeded" ]; then
        echo "Error: Service Bus namespace is not ready (current state: $status)."
        echo "Please wait for deployment to complete. Use option 3 to check status."
        return 1
    fi

    # Get the signed-in user's UPN
    local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)

    if [ -z "$user_object_id" ] || [ -z "$user_upn" ]; then
        echo "Error: Unable to retrieve signed-in user information."
        echo "Please ensure you are logged in with 'az login'."
        return 1
    fi

    local ns_id=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "id" -o tsv)

    # Check if role is already assigned
    local role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $ns_id \
        --role "Azure Service Bus Data Owner" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -n "$role_exists" ]; then
        echo "✓ Azure Service Bus Data Owner role already assigned"
    else
        az role assignment create \
            --role "Azure Service Bus Data Owner" \
            --assignee "$user_object_id" \
            --scope "$ns_id" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Azure Service Bus Data Owner role assigned"
        else
            echo "Error: Failed to assign Azure Service Bus Data Owner role"
            return 1
        fi
    fi

    echo ""
    echo "Role configured for: $user_upn"
    echo "  - Azure Service Bus Data Owner: send, receive, and manage entities"
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    echo "Service Bus Namespace ($namespace_name):"
    local ns_status=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "provisioningState" -o tsv 2>/dev/null)

    if [ -z "$ns_status" ]; then
        echo "  Status: Not created"
    else
        echo "  Status: $ns_status"
        if [ "$ns_status" = "Succeeded" ]; then
            echo "  ✓ Namespace is ready"
            local ns_sku=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "sku.name" -o tsv 2>/dev/null)
            echo "  SKU: $ns_sku"
            local ns_endpoint=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "serviceBusEndpoint" -o tsv 2>/dev/null)
            echo "  Endpoint: $ns_endpoint"

            # Check role assignment
            local user_upn=$(az ad signed-in-user show --query userPrincipalName -o tsv 2>/dev/null)
            local ns_id=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "id" -o tsv)

            local role_exists=$(az role assignment list \
                --assignee $user_object_id \
                --scope $ns_id \
                --role "Azure Service Bus Data Owner" \
                --query "[0].id" -o tsv 2>/dev/null)

            if [ -n "$role_exists" ]; then
                echo "  ✓ Role assigned: $user_upn (Azure Service Bus Data Owner)"
            else
                echo "  ⚠ Role not assigned"
            fi
        else
            echo "  ⚠ Namespace is still provisioning. Please wait and try again."
        fi
    fi
}

# Function to retrieve connection info and create .env file
retrieve_connection_info() {
    echo "Retrieving connection information..."

    # Prereq check: namespace must exist
    local ns_exists=$(az servicebus namespace show --resource-group $rg --name $namespace_name 2>/dev/null)
    if [ -z "$ns_exists" ]; then
        echo "Error: Service Bus namespace '$namespace_name' not found."
        echo "Please run option 1 to create the namespace, then try again."
        return 1
    fi

    # Prereq check: role must be assigned
    local ns_id=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "id" -o tsv)
    local role_exists=$(az role assignment list \
        --assignee $user_object_id \
        --scope $ns_id \
        --role "Azure Service Bus Data Owner" \
        --query "[0].id" -o tsv 2>/dev/null)

    if [ -z "$role_exists" ]; then
        echo "Error: Azure Service Bus Data Owner role not assigned."
        echo "Please run option 2 to assign the role, then try again."
        return 1
    fi

    # Get the FQDN
    local fqdn="${namespace_name}.servicebus.windows.net"

    local env_file="$(dirname "$0")/.env"

    cat > "$env_file" << EOF
export RESOURCE_GROUP="$rg"
export NAMESPACE_NAME="$namespace_name"
export SERVICE_BUS_FQDN="$fqdn"
EOF

    echo ""
    echo "Service Bus Connection Information"
    echo "==========================================================="
    echo "FQDN: $fqdn"
    echo "Authentication: Microsoft Entra ID (DefaultAzureCredential)"
    echo ""
    echo "Environment variables saved to: $env_file"
}

# Display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    Service Bus Messaging Exercise - Deployment Script"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Location: $location"
    echo "Namespace: $namespace_name"
    echo "====================================================================="
    echo "1. Create Service Bus namespace"
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
            create_servicebus_namespace
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
