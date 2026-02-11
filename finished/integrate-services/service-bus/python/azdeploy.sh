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
acr_name="acr${user_hash}"
app_plan="plan-docprocessor-${user_hash}"
app_name="app-docprocessor-${user_hash}"
container_image="docprocessor:v1"

# Function to display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    App Service Container Exercise - Deployment Script"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Location: $location"
    echo "ACR Name: $acr_name"
    echo "App Service Plan: $app_plan"
    echo "====================================================================="
    echo "1. Create Azure Container Registry and build container image"
    echo "2. Create App Service Plan"
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

# Function to create App Service Plan
create_app_service_plan() {
    echo "Creating App Service Plan '$app_plan'..."

    local plan_exists=$(az appservice plan show --resource-group $rg --name $app_plan 2>/dev/null)
    if [ -z "$plan_exists" ]; then
        az appservice plan create \
            --resource-group $rg \
            --name $app_plan \
            --sku B1 \
            --is-linux > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ App Service Plan created: $app_plan"
            echo "  SKU: B1 (Basic tier - supports always-on and custom containers)"
        else
            echo "Error: Failed to create App Service Plan"
            return 1
        fi
    else
        echo "✓ App Service Plan already exists: $app_plan"
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
export APP_PLAN="$app_plan"
export APP_NAME="$app_name"
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

    # Check App Service Plan
    echo ""
    echo "App Service Plan ($app_plan):"
    local plan_status=$(az appservice plan show --resource-group $rg --name $app_plan --query "provisioningState" -o tsv 2>/dev/null)
    if [ ! -z "$plan_status" ]; then
        echo "  Status: $plan_status"
        local plan_sku=$(az appservice plan show --resource-group $rg --name $app_plan --query "sku.name" -o tsv 2>/dev/null)
        echo "  SKU: $plan_sku"
        if [ "$plan_status" = "Succeeded" ]; then
            echo "  ✓ App Service Plan is ready"
        fi
    else
        echo "  Status: Not created"
    fi

    # Check Web App
    echo ""
    echo "Web App ($app_name):"
    local app_state=$(az webapp show --resource-group $rg --name $app_name --query "state" -o tsv 2>/dev/null)
    if [ ! -z "$app_state" ]; then
        echo "  State: $app_state"
        echo "  URL: https://$app_name.azurewebsites.net"

        # Check managed identity
        local identity=$(az webapp identity show --resource-group $rg --name $app_name --query "principalId" -o tsv 2>/dev/null)
        if [ ! -z "$identity" ]; then
            echo "  ✓ Managed identity configured"
        else
            echo "  Managed identity: Not configured"
        fi
    else
        echo "  Status: Not created (student task)"
    fi

    echo ""
    echo "====================================================================="
    echo "Environment Variables (.env file):"
    echo "  RESOURCE_GROUP=$rg"
    echo "  ACR_NAME=$acr_name"
    echo "  APP_PLAN=$app_plan"
    echo "  APP_NAME=$app_name"
    echo "  LOCATION=$location"
    echo "====================================================================="
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
            create_app_service_plan
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
