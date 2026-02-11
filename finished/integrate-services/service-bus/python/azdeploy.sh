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

# Function to display menu
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
    echo "2. Check deployment status"
    echo "3. Assign role and create .env file"
    echo "4. Exit"
    echo "====================================================================="
}

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
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    echo "Service Bus Namespace ($namespace_name):"
    local ns_status=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ ! -z "$ns_status" ]; then
        echo "  Provisioning State: $ns_status"
        if [ "$ns_status" = "Succeeded" ]; then
            echo "  ✓ Namespace is ready"
            local ns_sku=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "sku.name" -o tsv 2>/dev/null)
            echo "  SKU: $ns_sku"
            local ns_endpoint=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "serviceBusEndpoint" -o tsv 2>/dev/null)
            echo "  Endpoint: $ns_endpoint"
        else
            echo "  ⚠ Namespace is still provisioning. Please wait and try again."
        fi
    else
        echo "  Status: Not created"
    fi
}

# Function to assign role and create .env file
assign_role_and_create_env() {
    echo "Assigning Azure Service Bus Data Owner role..."

    # Get the namespace resource ID
    local ns_id=$(az servicebus namespace show --resource-group $rg --name $namespace_name --query "id" -o tsv 2>/dev/null)
    if [ -z "$ns_id" ]; then
        echo ""
        echo "Error: Unable to find the Service Bus namespace."
        echo "Please check the deployment status to ensure the resource is fully provisioned."
        return 1
    fi

    # Assign the Azure Service Bus Data Owner role
    az role assignment create \
        --role "Azure Service Bus Data Owner" \
        --assignee "$user_object_id" \
        --scope "$ns_id" > /dev/null 2>&1

    echo "✓ Role assigned: Azure Service Bus Data Owner"

    # Get the FQDN
    local fqdn="${namespace_name}.servicebus.windows.net"

    # Create .env file
    local env_file="$(dirname "$0")/.env"

    cat > "$env_file" << EOF
export RESOURCE_GROUP="$rg"
export NAMESPACE_NAME="$namespace_name"
export SERVICE_BUS_FQDN="$fqdn"
EOF

    clear
    echo ""
    echo "Service Bus Connection Information"
    echo "==========================================================="
    echo "FQDN: $fqdn"
    echo ""
    echo "Environment variables saved to: $env_file"
    echo "Run 'source .env' to load them into your shell."
}

# Main menu loop
while true; do
    show_menu
    read -p "Please select an option (1-4): " choice

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
            check_deployment_status
            echo ""
            read -p "Press Enter to continue..."
            ;;
        3)
            echo ""
            assign_role_and_create_env
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
