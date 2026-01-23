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
sb_namespace="sb-${user_hash}"
queue_name="orders"
container_app_name="queue-processor"
container_image="queue-processor:v1"

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
    echo "Service Bus Namespace: $sb_namespace"
    echo "====================================================================="
    echo "1. Create Azure Container Registry and build container image"
    echo "2. Create Container Apps environment"
    echo "3. Create Service Bus namespace and queue"
    echo "4. Configure managed identity for queue-processor app"
    echo "5. Check deployment status"
    echo "6. Exit"
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

# Function to create Service Bus namespace and queue
create_servicebus() {
    echo "Creating Service Bus namespace '$sb_namespace'..."

    local sb_exists=$(az servicebus namespace show --resource-group $rg --name $sb_namespace 2>/dev/null)
    if [ -z "$sb_exists" ]; then
        az servicebus namespace create \
            --resource-group $rg \
            --name $sb_namespace \
            --location $location \
            --sku Standard > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Service Bus namespace created: $sb_namespace"
        else
            echo "Error: Failed to create Service Bus namespace"
            return 1
        fi
    else
        echo "✓ Service Bus namespace already exists: $sb_namespace"
    fi

    echo ""
    echo "Creating queue '$queue_name'..."

    local queue_exists=$(az servicebus queue show --resource-group $rg --namespace-name $sb_namespace --name $queue_name 2>/dev/null)
    if [ -z "$queue_exists" ]; then
        az servicebus queue create \
            --resource-group $rg \
            --namespace-name $sb_namespace \
            --name $queue_name > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            echo "✓ Queue created: $queue_name"
        else
            echo "Error: Failed to create queue"
            return 1
        fi
    else
        echo "✓ Queue already exists: $queue_name"
    fi

    # Update environment file with Service Bus info
    write_env_file
}

# Function to configure managed identity for the container app
configure_managed_identity() {
    echo "Configuring managed identity for '$container_app_name'..."
    echo ""

    # Check if container app exists
    local app_exists=$(az containerapp show --resource-group $rg --name $container_app_name 2>/dev/null)
    if [ -z "$app_exists" ]; then
        echo "Error: Container app '$container_app_name' not found."
        echo "Please deploy the container app first using the exercise steps."
        return 1
    fi

    # Get the principal ID of the container app's system-assigned identity
    echo "Getting container app identity..."
    local principal_id=$(az containerapp identity show \
        --resource-group $rg \
        --name $container_app_name \
        --query principalId \
        --output tsv 2>/dev/null)

    if [ -z "$principal_id" ]; then
        echo "Error: Container app does not have a system-assigned identity."
        echo "Please create the container app with --system-assigned flag."
        return 1
    fi
    echo "✓ Principal ID: $principal_id"

    # Get Service Bus namespace resource ID
    echo ""
    echo "Getting Service Bus resource ID..."
    local sb_resource_id=$(az servicebus namespace show \
        --resource-group $rg \
        --name $sb_namespace \
        --query id \
        --output tsv 2>/dev/null)

    if [ -z "$sb_resource_id" ]; then
        echo "Error: Service Bus namespace '$sb_namespace' not found."
        echo "Please run option 3 first to create the Service Bus namespace."
        return 1
    fi
    echo "✓ Service Bus resource ID obtained"

    # Assign Azure Service Bus Data Receiver role (for receiving messages)
    echo ""
    echo "Assigning 'Azure Service Bus Data Receiver' role..."
    az role assignment create \
        --assignee "$principal_id" \
        --role "Azure Service Bus Data Receiver" \
        --scope "$sb_resource_id" > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        echo "✓ Service Bus Data Receiver role assigned"
    else
        echo "  Role may already be assigned or assignment failed"
    fi

    # Assign Azure Service Bus Data Owner role (for KEDA scaler to query metrics)
    echo ""
    echo "Assigning 'Azure Service Bus Data Owner' role (required for KEDA scaling)..."
    az role assignment create \
        --assignee "$principal_id" \
        --role "Azure Service Bus Data Owner" \
        --scope "$sb_resource_id" > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        echo "✓ Service Bus Data Owner role assigned"
    else
        echo "  Role may already be assigned or assignment failed"
    fi

    echo ""
    echo "====================================================================="
    echo "Managed identity configuration complete!"
    echo ""
    echo "NOTE: Azure role assignments can take 1-2 minutes to propagate."
    echo "If the app fails to connect to Service Bus, wait a moment and retry."
    echo "====================================================================="
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
export SERVICE_BUS_NAMESPACE="$sb_namespace"
export SERVICE_BUS_FQDN="$sb_namespace.servicebus.windows.net"
export QUEUE_NAME="$queue_name"
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

    # Check Service Bus
    echo ""
    echo "Service Bus Namespace ($sb_namespace):"
    local sb_status=$(az servicebus namespace show --resource-group $rg --name $sb_namespace --query "provisioningState" -o tsv 2>/dev/null)
    if [ ! -z "$sb_status" ]; then
        echo "  Status: $sb_status"
        if [ "$sb_status" = "Succeeded" ]; then
            echo "  ✓ Service Bus namespace is ready"
            # Check if queue exists
            local queue_status=$(az servicebus queue show --resource-group $rg --namespace-name $sb_namespace --name $queue_name --query "status" -o tsv 2>/dev/null)
            if [ ! -z "$queue_status" ]; then
                echo "  ✓ Queue '$queue_name': $queue_status"
            else
                echo "  Queue '$queue_name' not found"
            fi
        fi
    else
        echo "  Status: Not created"
    fi

    # Check Container App
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
        local replica_count=$(az containerapp replica list --resource-group $rg --name $container_app_name --query "length([])" -o tsv 2>/dev/null)
        echo "  Running replicas: ${replica_count:-0}"
    else
        echo "  Status: Not deployed"
    fi
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
            create_servicebus
            echo ""
            read -p "Press Enter to continue..."
            ;;
        4)
            echo ""
            create_resource_group
            echo ""
            create_servicebus
            echo ""
            configure_managed_identity
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
            echo "Exiting..."
            clear
            exit 0
            ;;
        *)
            echo "Invalid option. Please select 1-6."
            read -p "Press Enter to continue..."
            ;;
    esac
done
