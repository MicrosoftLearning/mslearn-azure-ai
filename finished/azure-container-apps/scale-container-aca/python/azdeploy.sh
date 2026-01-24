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
aca_env="aca-env-${user_hash}"
container_app_name="agent-api"
container_image="agent-api:v1"

# Function to display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    Azure Container Apps Scaling Exercise - Deployment Script"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Location: $location"
    echo "Container Apps Environment: $aca_env"
    echo "ACR Name: $acr_name"
    echo "====================================================================="
    echo "1. Create Azure Container Registry and build container image"
    echo "2. Create Container Apps environment"
    echo "3. Create Container App"
    echo "4. Check deployment status"
    echo "5. Exit"
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

# Function to create the Container App (ingress enabled, no scale rules)
create_container_app() {
    echo "Creating Container App '$container_app_name' (if needed)..."
    echo "This may take a few minutes..."

    local acr_server="$acr_name.azurecr.io"
    local container_image_fqdn="$acr_server/$container_image"

    az containerapp show --resource-group "$rg" --name "$container_app_name" > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        # Prereq check: Container Apps environment must exist
        az containerapp env show --name "$aca_env" --resource-group "$rg" > /dev/null 2>&1
        if [ $? -ne 0 ]; then
            echo "Error: Container Apps environment '$aca_env' not found."
            echo "Please run option 2 to create the Container Apps environment, then try again."
            return 1
        fi

        # Prereq check: container image must exist in ACR
        # (This will also fail if the ACR itself doesn't exist yet.)
        az acr repository show --name "$acr_name" --image "$container_image" > /dev/null 2>&1
        if [ $? -ne 0 ]; then
            echo "Error: Container image '$container_image' isn't available in '$acr_name'."
            echo "Please run option 1 to create ACR and build/push the image, then try again."
            return 1
        fi

        az containerapp create \
            --name "$container_app_name" \
            --resource-group "$rg" \
            --environment "$aca_env" \
            --image "$container_image_fqdn" \
            --registry-server "$acr_server" \
            --registry-identity system \
            --system-assigned \
            --ingress external \
            --target-port 8080 \
            --min-replicas 1 \
            --max-replicas 1 \
            --env-vars "AGENT_DEFAULT_DELAY_MS=500" > /dev/null 2>&1

        if [ $? -ne 0 ]; then
            echo "Error: Failed to create Container App"
            return 1
        fi
        echo "✓ Container App created: $container_app_name"
    else
        echo "✓ Container App already exists: $container_app_name"
    fi

    # Ensure the system-assigned identity can pull from ACR
    echo ""
    echo "Ensuring Container App identity can pull from ACR (AcrPull)..."

    local principal_id=$(az containerapp identity show \
        --resource-group "$rg" \
        --name "$container_app_name" \
        --query principalId \
        --output tsv 2>/dev/null)

    if [ -z "$principal_id" ]; then
        echo "Error: Unable to resolve Container App principalId"
        return 1
    fi

    local acr_id=$(az acr show --resource-group "$rg" --name "$acr_name" --query id --output tsv 2>/dev/null)
    if [ -z "$acr_id" ]; then
        echo "Error: Unable to resolve ACR resource id"
        return 1
    fi

    az role assignment create \
        --assignee "$principal_id" \
        --role "AcrPull" \
        --scope "$acr_id" > /dev/null 2>&1

    echo "✓ AcrPull role assigned (or already present)"

    # Persist env vars for the lab + dashboard
    write_env_file
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
}

# Function to write environment variables to file
write_env_file() {
    local env_file="$(dirname "$0")/.env"

    local container_app_fqdn=$(az containerapp show \
        --name "$container_app_name" \
        --resource-group "$rg" \
        --query "properties.configuration.ingress.fqdn" \
        --output tsv 2>/dev/null)

    local container_app_url=""
    if [ -n "$container_app_fqdn" ]; then
        container_app_url="https://$container_app_fqdn"
    fi

    cat > "$env_file" << EOF
export RESOURCE_GROUP="$rg"
export ACA_ENVIRONMENT="$aca_env"
export CONTAINER_APP_NAME="$container_app_name"
export CONTAINER_APP_FQDN="$container_app_fqdn"
export CONTAINER_APP_URL="$container_app_url"
export CONTAINER_IMAGE="$container_image"
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
    echo ""
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

    echo ""
    echo "Container App ($container_app_name):"
    local app_status=$(az containerapp show --resource-group $rg --name $container_app_name --query "properties.provisioningState" -o tsv 2>/dev/null)
    if [ ! -z "$app_status" ]; then
        echo "  Status: $app_status"
        local has_identity=$(az containerapp identity show --resource-group $rg --name $container_app_name --query "principalId" -o tsv 2>/dev/null)
        if [ ! -z "$has_identity" ]; then
            echo "  ✓ System-assigned identity configured"
        else
            echo "  ⚠ No system-assigned identity"
        fi
        local fqdn=$(az containerapp show --resource-group $rg --name $container_app_name --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null)
        if [ ! -z "$fqdn" ]; then
            echo "  ✓ Ingress FQDN: $fqdn"
        else
            echo "  ⚠ Ingress not enabled (no FQDN)"
        fi
        local replica_count=$(az containerapp replica list --resource-group $rg --name $container_app_name --query "length([])" -o tsv 2>/dev/null)
        echo "  Running replicas: ${replica_count:-0}"
    else
        echo "  Status: Not deployed"
    fi
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
            create_resource_group
            echo ""
            create_container_app
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
            echo "Exiting..."
            clear
            exit 0
            ;;
        *)
            echo "Invalid option. Please select 1-5."
            read -p "Press Enter to continue..."
            ;;
    esac
done
