#!/usr/bin/env bash

# Change the values of these variables as needed

rg="rg-exercises"           # Resource Group name
location="westus2"          # Azure region for the resources
#subscription="16b3c013-d300-468d-ac64-7eda0820b6d3"             # Azure subscription ID (leave empty to use default)

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from username (always produces valid Azure resource name)
user_hash=$(echo -n "$USER" | sha1sum | cut -c1-8)

# Resource names with hash for uniqueness
foundry_resource="foundry-resource-${user_hash}"
acr_name="acr${user_hash}"
aks_cluster="aks-${user_hash}"
api_image_name="aks-api"

# Function to display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    AKS Deployment with Foundry Model Integration"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Location: $location"
    echo "Foundry Resource: $foundry_resource"
    echo "ACR Name: $acr_name"
    echo "AKS Cluster: $aks_cluster"
    echo "====================================================================="
    echo "1. Provision gpt-4o-mini model in Microsoft Foundry"
    echo "2. Create Azure Container Registry (ACR)"
    echo "3. Build and push API image to ACR"
    echo "4. Create AKS cluster"
    echo "5. Check deployment status"
    echo "6. Exit"
    echo "====================================================================="
}

# Function to setup .env files with credentials from Foundry project
setup_env_files() {
    local endpoint=$1
    local key=$2

    echo "Creating .env files with Foundry credentials..."
    echo ""

    # Create or update api/.env
    echo "Creating api/.env..."
    cat > api/.env << EOF
# Azure Foundry Model Configuration
OPENAI_API_ENDPOINT=$endpoint
OPENAI_API_KEY=$key
OPENAI_DEPLOYMENT_NAME=gpt-4o-mini
OPENAI_API_VERSION=2024-10-21
EOF

    echo "✓ Created api/.env"

    # Create or update client/.env
    echo "Creating client/.env..."
    cat > client/.env << EOF
# API Endpoint (will be updated after AKS deployment)
API_ENDPOINT=http://localhost:8000
EOF

    echo "✓ Created client/.env"
    echo ""
    echo "Next: Run menu option 2 (Create Azure Container Registry) to continue deployment."
}

# Function to provision Microsoft Foundry project and deploy gpt-4o-mini model using Azure CLI
provision_foundry_resources() {
    echo "Provisioning Microsoft Foundry project with gpt-4o-mini model..."
    echo ""

    # Check if we're authenticated with Azure
    if ! az account show &> /dev/null; then
        echo "Not authenticated with Azure. Please run: az login"
        return 1
    fi

    # Set subscription if specified
    if [ ! -z "$subscription" ]; then
        echo "Setting subscription to: $subscription"
        az account set --subscription "$subscription"
        if [ $? -ne 0 ]; then
            echo "Error: Failed to set subscription."
            return 1
        fi
    fi

    # Check if resource group exists, create if needed
    echo "Checking resource group: $rg"
    if ! az group exists --name "$rg" | grep -q "true"; then
        echo "Creating resource group: $rg in $location"
        az group create --name "$rg" --location "$location"
        if [ $? -ne 0 ]; then
            echo "Error: Failed to create resource group."
            return 1
        fi
    else
        echo "✓ Resource group already exists"
    fi

    # Create Foundry resource (AIServices kind)
    echo ""
    echo "Creating Microsoft Foundry resource: $foundry_resource"
    az cognitiveservices account create \
        --name "$foundry_resource" \
        --resource-group "$rg" \
        --location "$location" \
        --kind AIServices \
        --sku s0 \
        --public-network-access Enabled \
        --yes

    if [ $? -ne 0 ]; then
        echo "Error: Failed to create Foundry resource."
        return 1
    fi
    echo "✓ Foundry resource created"

    # Retrieve endpoint and key for the resource
    echo ""
    echo "Retrieving Foundry credentials..."
    local endpoint=$(az cognitiveservices account show \
        --name "$foundry_resource" \
        --resource-group "$rg" \
        --query properties.endpoint -o tsv)

    local key=$(az cognitiveservices account keys list \
        --name "$foundry_resource" \
        --resource-group "$rg" \
        --query key1 -o tsv)

    if [ -z "$endpoint" ] || [ -z "$key" ]; then
        echo "Error: Failed to retrieve endpoint or key."
        return 1
    fi
    echo "✓ Credentials retrieved successfully"

    # Deploy gpt-4o-mini model
    echo ""
    echo "Deploying gpt-4o-mini model (this may take a few minutes)..."
    az cognitiveservices account deployment create \
        --name "$foundry_resource_name" \
        --resource-group "$rg" \
        --deployment-name "gpt-4o-mini" \
        --model-name "gpt-4o-mini" \
        --model-version "2024-11-20" \
        --model-format "OpenAI" \
        --sku-capacity "1" \
        --sku-name "Standard"

    if [ $? -ne 0 ]; then
        echo "Error: Failed to deploy model."
        return 1
    fi
    echo "✓ Model deployed successfully"

    # Setup environment files
    setup_env_files "$endpoint" "$key"

    echo ""
    echo "✓ Foundry provisioning complete!"
    echo ""
    echo "Foundry Resource Details:"
    echo "  Resource: $foundry_resource"
    echo "  Endpoint: $endpoint"
}

# Function to create resource group if it doesn't exist
create_resource_group() {
    echo "Checking/creating resource group '$rg'..."

    local exists=$(az group exists --name $rg)
    if [ "$exists" = "false" ]; then
        az group create --name $rg --location $location
        echo "Resource group created: $rg"
    else
        echo "Resource group already exists: $rg"
    fi
}

# Function to create Azure Container Registry
create_acr() {
    echo "Creating Azure Container Registry '$acr_name'..."

    local exists=$(az acr show --resource-group $rg --name $acr_name 2>/dev/null)
    if [ -z "$exists" ]; then
        az acr create \
            --resource-group $rg \
            --name $acr_name \
            --sku Basic \
            --admin-enabled true
        echo "ACR created: $acr_name"
    else
        echo "ACR already exists: $acr_name"
    fi
}

# Function to build and push API image
build_and_push_image() {
    echo "Building and pushing API image to ACR..."

    # Get ACR login server
    acr_server=$(az acr show --resource-group $rg --name $acr_name --query loginServer -o tsv)

    if [ -z "$acr_server" ]; then
        echo "Error: Could not retrieve ACR login server."
        return 1
    fi

    # Build image using ACR Tasks
    az acr build \
        --resource-group $rg \
        --registry $acr_name \
        --image ${api_image_name}:latest \
        --file api/Dockerfile \
        api/

    if [ $? -eq 0 ]; then
        echo "Image built and pushed: ${acr_server}/${api_image_name}:latest"
    else
        echo "Error building/pushing image."
        return 1
    fi
}

# Function to create AKS cluster
create_aks_cluster() {
    echo "Creating AKS cluster '$aks_cluster'..."
    echo "Using smallest SKU (Standard_B2s, 1 node) for cost efficiency."

    local exists=$(az aks show --resource-group $rg --name $aks_cluster 2>/dev/null)
    if [ -z "$exists" ]; then
        az aks create \
            --resource-group $rg \
            --name $aks_cluster \
            --node-count 1 \
            --vm-set-type VirtualMachineScaleSets \
            --load-balancer-sku standard \
            --enable-managed-identity \
            --network-plugin azure \
            --attach-acr $acr_name \
            --no-wait

        echo "AKS cluster creation initiated: $aks_cluster"
        echo "This may take 10-15 minutes to complete."
        echo "Use menu option 5 to check deployment status."
    else
        echo "AKS cluster already exists: $aks_cluster"
    fi
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    # Check Foundry deployment (via AZD or environment)
    echo "Foundry Model Deployment ($foundry_deployment):"
    # Note: Status check depends on how AZD tracks deployments
    echo "  (Check Foundry portal for deployment status)"

    # Check ACR
    echo ""
    echo "Azure Container Registry ($acr_name):"
    acr_status=$(az acr show --resource-group $rg --name $acr_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ ! -z "$acr_status" ]; then
        echo "  Status: $acr_status"
    else
        echo "  Status: Not found or not ready"
    fi

    # Check AKS
    echo ""
    echo "AKS Cluster ($aks_cluster):"
    aks_status=$(az aks show --resource-group $rg --name $aks_cluster --query "provisioningState" -o tsv 2>/dev/null)
    if [ ! -z "$aks_status" ]; then
        echo "  Status: $aks_status"
        if [ "$aks_status" = "Succeeded" ]; then
            echo "  ✓ AKS cluster is ready for deployment"
        fi
    else
        echo "  Status: Not found or not ready"
    fi
}

# Main menu loop
while true; do
    show_menu
    read -p "Please select an option (1-6): " choice

    case $choice in
        1)
            echo ""
            provision_foundry_resources
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            create_resource_group
            echo ""
            create_acr
            echo ""
            read -p "Press Enter to continue..."
            ;;
        3)
            echo ""
            build_and_push_image
            echo ""
            read -p "Press Enter to continue..."
            ;;
        4)
            echo ""
            create_aks_cluster
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
