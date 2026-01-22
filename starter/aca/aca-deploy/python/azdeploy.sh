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
acr_name="acr${user_hash}"
aca_env="aca-env-${user_hash}"
container_app_name="ai-api"
container_image="ai-api:v1"

# Function to display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    Azure Container Apps Exercise - Deployment Script"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Location: $location"
    echo "Container Apps Environment: $aca_env"
    echo "ACR Name: $acr_name"
    echo "====================================================================="
    echo "1. Create Azure Container Registry and build container image"
    echo "2. Create Container Apps environment"
    echo "3. Check deployment status"
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

# Function to create Azure Container Registry and build image
create_acr_and_build_image() {
    echo "Creating Azure Container Registry '$acr_name'..."

    local acr_exists=$(az acr show --resource-group $rg --name $acr_name 2>/dev/null)
    if [ -z "$acr_exists" ]; then
        az acr create \
            --resource-group $rg \
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
        --resource-group $rg \
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

# Function to create Container Apps environment
create_containerapps_environment() {
    echo "Creating Container Apps environment '$aca_env' (if needed)..."
    echo "This may take a few minutes..."
    az containerapp env show --name "$aca_env" --resource-group "$rg" > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        az containerapp env create \
            --name "$aca_env" \
            --resource-group "$rg" \
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

    # Write environment variables to file
    write_env_file
}

# Function to write environment variables to file
write_env_file() {
    local env_file="$(dirname "$0")/.env"

    cat > "$env_file" << EOF
export RESOURCE_GROUP="$rg"
export ACR_NAME="$acr_name"
export ACR_SERVER="$acr_name.azurecr.io"
export ACA_ENVIRONMENT="$aca_env"
export CONTAINER_APP_NAME="$container_app_name"
export CONTAINER_IMAGE="$container_image"
export TARGET_PORT="8000"
export MODEL_NAME="gpt-4o-mini"
export EMBEDDINGS_API_KEY="demo-key-12345"
export LOCATION="$location"
EOF
    echo ""
    echo "Environment variables saved to: $env_file"
    echo "Run 'source .env' to load them into your shell."
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    # Check Container Apps environment
    echo "Container Apps Environment ($aca_env):"
    local env_status=$(az containerapp env show --resource-group "$rg" --name "$aca_env" --query "properties.provisioningState" -o tsv 2>/dev/null | tail -1)
    if [ -n "$env_status" ]; then
        echo "  Status: $env_status"
        if [ "$env_status" = "Succeeded" ]; then
            echo "  ✓ Container Apps environment is ready"
        fi
    else
        echo "  Status: Not created"
    fi

    # Check ACR
    echo "Azure Container Registry ($acr_name):"
    local acr_status=$(az acr show --resource-group $rg --name $acr_name --query "provisioningState" -o tsv 2>/dev/null)
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
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            create_resource_group
            echo ""
            create_containerapps_environment
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
