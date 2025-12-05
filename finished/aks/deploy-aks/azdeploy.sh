#!/usr/bin/env bash

# Change the values of these variables as needed

rg="rg-exercises"           # Resource Group name
location="westus2"          # Azure region for the resources
subscription_id=""          # Leave empty to use default subscription

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from username (always produces valid Azure resource name)
user_hash=$(echo -n "$USER" | sha1sum | cut -c1-8)

# Resource names with hash for uniqueness
foundry_deployment="gpt4o-${user_hash}"
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
    echo "Foundry Deployment: $foundry_deployment"
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

# Function to setup .env files with credentials retrieved from AZD
setup_env_files() {
    echo "Setting up .env files with Foundry credentials..."
    echo ""

    # Get Foundry endpoint and key from AZD outputs
    foundry_endpoint=$(azd env get-values --output json 2>/dev/null | grep -o '"FOUNDRY_ENDPOINT":"[^"]*' | cut -d'"' -f4)
    foundry_key=$(azd env get-values --output json 2>/dev/null | grep -o '"FOUNDRY_KEY":"[^"]*' | cut -d'"' -f4)

    if [ -z "$foundry_endpoint" ] || [ -z "$foundry_key" ]; then
        echo "Warning: Could not retrieve Foundry credentials from AZD."
        echo "Please verify the Foundry deployment is complete."
        echo "You may need to manually add Foundry credentials to api/.env"
        foundry_endpoint="<FOUNDRY_ENDPOINT>"
        foundry_key="<FOUNDRY_KEY>"
    fi

    # Create or update api/.env
    echo "Creating api/.env..."
    cat > api/.env << EOF
# Foundry Model Configuration
FOUNDRY_ENDPOINT=$foundry_endpoint
FOUNDRY_KEY=$foundry_key
FOUNDRY_DEPLOYMENT=gpt-4o-mini
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

# Function to provision Foundry resources using AZD
provision_foundry_resources() {
    echo "Provisioning gpt-4o-mini model in Microsoft Foundry..."
    echo "Note: This uses 'azd provision' to provision Foundry resources."
    echo ""

    # Check if azure.yaml exists for AZD
    if [ ! -f "azure.yaml" ]; then
        echo "Error: azure.yaml not found in current directory."
        echo "Please ensure you're in the project root directory."
        return 1
    fi

    # Create fresh AZD environment with unique name
    azd_env_name="${aks_cluster}-env"
    echo "Setting up AZD environment: $azd_env_name"
    azd env new "$azd_env_name" --confirm >/dev/null 2>&1 || azd env new "$azd_env_name" >/dev/null 2>&1

    # Set AZD environment variables
    echo "Configuring AZD environment variables..."
    azd env set AZURE_LOCATION "$location" >/dev/null
    azd env set AZURE_RESOURCE_GROUP "$rg" >/dev/null
    azd env set AZURE_ENV_NAME "$azd_env_name" >/dev/null

    # Run azd provision
    echo "Provisioning resources with AZD (this may take several minutes)..."
    echo ""
    azd provision

    if [ $? -eq 0 ]; then
        echo ""
        echo "✓ Resources provisioned successfully."
        echo "Retrieving Foundry credentials and creating .env files..."
        setup_env_files
    else
        echo "Error provisioning resources. Please check the output above and try again."
        return 1
    fi
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
}

# Main menu loop
while true; do
    show_menu
    read -p "Please select an option (1-7): " choice

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
