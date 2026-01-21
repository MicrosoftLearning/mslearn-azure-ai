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
resource_group="${rg}"
aca_env="aca-env-exercise-${user_hash}"
acr_name="acr${user_hash}"
container_image="ai-api:v1"

# Function to display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    Azure Container Apps Exercise - Deployment Script"
    echo "====================================================================="
    echo "Resource Group: $resource_group"
    echo "Location: $location"
    echo "Container Apps Environment: $aca_env"
    echo "ACR Name: $acr_name"
    echo "====================================================================="
    echo "1. Create resource group + Container Apps environment"
    echo "2. Create Azure Container Registry and build container image"
    echo "3. Check setup status"
    echo "4. Exit"
    echo "====================================================================="
}

# Function to create resource group if it doesn't exist
create_resource_group() {
    echo "Checking/creating resource group '$resource_group'..."

    local exists=$(az group exists --name $resource_group)
    if [ "$exists" = "false" ]; then
        az group create --name $resource_group --location $location > /dev/null 2>&1
        echo "✓ Resource group created: $resource_group"
    else
        echo "✓ Resource group already exists: $resource_group"
    fi
}

install_containerapp_extension_and_register_providers() {
    echo "Ensuring Azure CLI and Container Apps extension are available..."
    az upgrade > /dev/null 2>&1 || true
    az extension add --name containerapp --upgrade > /dev/null 2>&1

    echo "Registering required resource providers (idempotent)..."
    az provider register --namespace Microsoft.App > /dev/null 2>&1
    az provider register --namespace Microsoft.OperationalInsights > /dev/null 2>&1
}

create_containerapps_environment() {
    echo "Creating Container Apps environment '$aca_env' (if needed)..."
    az containerapp env show --name "$aca_env" --resource-group "$resource_group" > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        az containerapp env create \
            --name "$aca_env" \
            --resource-group "$resource_group" \
            --location "$location" > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "✓ Container Apps environment created: $aca_env"
        else
            echo "Error: Failed to create Container Apps environment"
            return 1
        fi
    else
        echo "✓ Container Apps environment already exists: $aca_env"
    fi
}

# Function to create Azure Container Registry and build image
create_acr_and_build_image() {
    echo "Creating Azure Container Registry '$acr_name'..."

    local acr_exists=$(az acr show --resource-group $resource_group --name $acr_name 2>/dev/null)
    if [ -z "$acr_exists" ]; then
        az acr create \
            --resource-group $resource_group \
            --name $acr_name \
            --sku Basic \
            --admin-enabled false > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ ACR created: $acr_name"
            echo "  Login server: $acr_name.azurecr.io"
        else
            echo "Error: Failed to create ACR"
            return 1
        fi
    else
        echo "✓ ACR already exists: $acr_name"
        echo "  Login server: $acr_name.azurecr.io"
    fi

    echo ""
    echo "Building and pushing container image to ACR..."
    echo "This may take a few minutes..."

    # Build image using ACR Tasks
    az acr build \
        --resource-group $resource_group \
        --registry $acr_name \
        --image $container_image \
        --file api/Dockerfile \
        api/ > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        echo "✓ Image built and pushed: $acr_name.azurecr.io/$container_image"
    else
        echo "Error: Failed to build/push image"
        return 1
    fi
}

# Function to write environment variables to file
write_env_file() {
    local env_file="$(dirname "$0")/.env"

    local acr_server
    acr_server=$(az acr show -n "$acr_name" --query loginServer -o tsv 2>/dev/null)

    cat > "$env_file" << EOF
export RESOURCE_GROUP="$resource_group"
export LOCATION="$location"
export ACA_ENVIRONMENT="$aca_env"
export ACR_NAME="$acr_name"
export ACR_SERVER="$acr_server"
export CONTAINER_IMAGE="$container_image"
EOF
    echo ""
    echo "Environment variables saved to: $env_file"
    echo "Run 'source .env' to load them into your shell."

    echo ""
    echo "Next (student steps in the exercise):"
    echo "  - Deploy the Container App using: az containerapp create ..."
    echo "  - Configure secrets using: az containerapp secret set / az containerapp update"
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking setup status..."
    echo ""

    # Container Apps env
    echo "Container Apps Environment ($aca_env):"
    local env_status=$(az containerapp env show --resource-group $resource_group --name $aca_env --query "provisioningState" -o tsv 2>/dev/null)
    if [ ! -z "$env_status" ]; then
        echo "  Status: $env_status"
        if [ "$env_status" = "Succeeded" ]; then
            echo "  ✓ Environment is ready"
        fi
    else
        echo "  Status: Not created"
    fi

    # Check ACR
    echo "Azure Container Registry ($acr_name):"
    local acr_status=$(az acr show --resource-group $resource_group --name $acr_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ ! -z "$acr_status" ]; then
        echo "  Status: $acr_status"
        if [ "$acr_status" = "Succeeded" ]; then
            echo "  ✓ ACR is ready"
            # Check if image exists
            local image_exists=$(az acr repository show --name $acr_name --image $container_image 2>/dev/null)
            if [ ! -z "$image_exists" ]; then
                echo "  ✓ Container image: $container_image"
            else
                echo "  Container image not found"
            fi
        fi
    else
        echo "  Status: Not created"
    fi

    # Check App Service Plan
    echo ""
    echo "Tip: run 'source .env' after option 2 to load variables."
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
            create_acr_and_build_image
                    install_containerapp_extension_and_register_providers
                    create_containerapps_environment
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            create_resource_group
                    install_containerapp_extension_and_register_providers
                    create_containerapps_environment
            echo ""
            create_app_service_plan
                    write_env_file
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
            echo "Invalid option. Please select 1-4."
            read -p "Press Enter to continue..."
            ;;
    esac
done
