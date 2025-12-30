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
    echo "2. Delete/Purge Foundry deployment"
    echo "3. Create Azure Container Registry (ACR)"
    echo "4. Build and push API image to ACR"
    echo "5. Create AKS cluster"
    echo "6. Check deployment status"
    echo "7. Deploy to AKS"
    echo "8. Exit"
    echo "====================================================================="
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
        az group create --name "$rg" --location "$location" > /dev/null 2>&1
        if [ $? -ne 0 ]; then
            echo "Error: Failed to create resource group."
            return 1
        fi
    else
        echo "✓ Resource group already exists"
    fi

    # Create Foundry resource (AIServices kind)
    echo ""
    echo "Checking for existing Microsoft Foundry resource: $foundry_resource"

    local foundry_exists=$(az cognitiveservices account show \
        --name "$foundry_resource" \
        --resource-group "$rg" 2>/dev/null)

    if [ -z "$foundry_exists" ]; then
        echo "Creating Microsoft Foundry resource: $foundry_resource"
        az cognitiveservices account create \
            --name "$foundry_resource" \
            --resource-group "$rg" \
            --location "$location" \
            --kind AIServices \
            --sku s0 \
            --yes > /dev/null 2>&1

        if [ $? -ne 0 ]; then
            echo "Error: Failed to create Foundry resource."
            return 1
        fi
        echo "✓ Foundry resource created"
    else
        echo "✓ Foundry resource already exists"
    fi

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
        --name "$foundry_resource" \
        --resource-group "$rg" \
        --deployment-name "gpt-4o-mini" \
        --model-name "gpt-4o-mini" \
        --model-version "2024-07-18" \
        --model-format "OpenAI" \
        --sku-capacity "1" \
        --sku-name "Standard" > /dev/null 2>&1

    if [ $? -ne 0 ]; then
        echo "Error: Failed to deploy model."
        return 1
    fi
    echo "✓ Model deployed successfully"

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
        az group create --name $rg --location $location > /dev/null 2>&1
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
            --admin-enabled true > /dev/null 2>&1
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
        api/ > /dev/null 2>&1

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
    echo "This may take 5-10 minutes to complete. Please wait..."
    echo ""

    local exists=$(az aks show --resource-group $rg --name $aks_cluster 2>/dev/null)
    if [ -z "$exists" ]; then
        local start_time=$(date +%s)

        az aks create \
            --resource-group $rg \
            --name $aks_cluster \
            --node-count 1 \
            --vm-set-type VirtualMachineScaleSets \
            --load-balancer-sku standard \
            --enable-managed-identity \
            --network-plugin azure \
            --generate-ssh-keys \
            --attach-acr $acr_name > /dev/null 2>&1

        if [ $? -ne 0 ]; then
            echo "Error: Failed to create AKS cluster."
            return 1
        fi

        # Verify cluster is fully provisioned and nodes are Running
        echo "Waiting for cluster to be fully operational..."
        az aks wait --resource-group $rg --name $aks_cluster --updated > /dev/null 2>&1

        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        local minutes=$((duration / 60))
        local seconds=$((duration % 60))

        echo "✓ AKS cluster creation completed: $aks_cluster"
        echo "  Deployment time: ${minutes}m ${seconds}s"
    else
        echo "AKS cluster already exists: $aks_cluster"
    fi
}

# Function to deploy to AKS
deploy_to_aks() {
    echo "Deploying application to AKS..."
    echo ""

    # Get AKS credentials
    echo "Getting AKS credentials..."
    az aks get-credentials \
        --resource-group "$rg" \
        --name "$aks_cluster" \
        --overwrite-existing > /dev/null 2>&1

    if [ $? -ne 0 ]; then
        echo "Error: Failed to get AKS credentials."
        return 1
    fi
    echo "✓ AKS credentials configured"
    echo ""

    # Get Foundry credentials
    echo "Retrieving Foundry credentials..."
    local endpoint=$(az cognitiveservices account show \
        --name "$foundry_resource" \
        --resource-group "$rg" \
        --query "properties.endpoint" -o tsv 2>/dev/null)

    local key=$(az cognitiveservices account keys list \
        --name "$foundry_resource" \
        --resource-group "$rg" \
        --query "key1" -o tsv 2>/dev/null)

    if [ -z "$endpoint" ] || [ -z "$key" ]; then
        echo "Error: Could not retrieve Foundry credentials."
        return 1
    fi
    echo "✓ Foundry credentials retrieved"
    echo ""

    # Create or update the foundry-credentials secret
    echo "Creating Foundry credentials secret in AKS..."
    kubectl delete secret foundry-credentials -n default > /dev/null 2>&1
    local secret_output=$(kubectl create secret generic foundry-credentials \
        --from-literal=endpoint="$endpoint" \
        --from-literal=api-key="$key" \
        -n default 2>&1)

    if [ $? -ne 0 ]; then
        echo "Error: Failed to create Foundry credentials secret."
        echo "Details: $secret_output"
        return 1
    fi
    echo "✓ Foundry credentials secret created"
    echo ""

    # Update the deployment.yaml with the correct ACR endpoint
    echo "Deploying Kubernetes manifests..."
    sed "s|ACR_ENDPOINT|${acr_name}.azurecr.io|g" k8s/deployment.yaml | kubectl apply -f - -n default 2>&1 > /dev/null

    if [ $? -ne 0 ]; then
        echo "Error: Failed to apply deployment manifest."
        return 1
    fi

    echo "✓ Deployment manifest updated with ACR endpoint: ${acr_name}.azurecr.io"

    # Apply the service manifest
    kubectl apply -f k8s/service.yaml -n default 2>&1 > /dev/null

    if [ $? -ne 0 ]; then
        echo "Error: Failed to apply service manifest."
        return 1
    fi

    echo "✓ Service manifest applied"
    echo ""

    # Wait for LoadBalancer service to get external IP
    echo "Waiting for LoadBalancer external IP (this may take a few minutes)..."
    local max_attempts=60
    local attempt=0
    local external_ip=""

    while [ $attempt -lt $max_attempts ]; do
        external_ip=$(kubectl get svc aks-api-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}' -n default 2>/dev/null)
        if [ ! -z "$external_ip" ] && [[ "$external_ip" != "10."* ]]; then
            break
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    if [ -z "$external_ip" ]; then
        echo "Error: Could not obtain external IP for the service."
        echo "You can check the service status manually with: kubectl get svc aks-api-service"
        return 1
    fi

    echo "✓ External IP obtained: $external_ip"
    echo ""

    # Update client/.env with the API endpoint
    echo "Updating client/.env with API endpoint..."
    cat > client/.env << EOF
# API Endpoint for AKS-deployed service
API_ENDPOINT=http://$external_ip
EOF
    echo "✓ client/.env updated"
    echo ""
    echo "=========================================="
    echo "Deployment completed successfully!"
    echo "=========================================="
    echo "API Endpoint: http://$external_ip"
    echo ""
    echo "Next steps:"
    echo "1. Run the client to test the API:"
    echo "   python client/main.py"
    echo "=========================================="
}

# Function to delete and purge Foundry resource
delete_foundry_resource() {
    echo "Deleting and purging Foundry resource: $foundry_resource"
    echo ""
    read -p "Are you sure you want to delete the Foundry resources? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        echo "Cancelled. Foundry resource was not deleted."
        return 0
    fi

    echo ""
    local exists=$(az cognitiveservices account show \
        --name "$foundry_resource" \
        --resource-group "$rg" 2>/dev/null)

    if [ -z "$exists" ]; then
        echo "Foundry resource does not exist: $foundry_resource"
        return 0
    fi

    echo "Deleting Foundry resource..."
    az cognitiveservices account delete \
        --name "$foundry_resource" \
        --resource-group "$rg" \
        --yes > /dev/null 2>&1

    if [ $? -ne 0 ]; then
        echo "Error: Failed to delete Foundry resource."
        return 1
    fi

    echo "✓ Resource deleted"
    echo ""
    echo "Purging resource to free up the name..."
    az cognitiveservices account purge \
        --name "$foundry_resource" \
        --resource-group "$rg" \
        --location "$location" > /dev/null 2>&1

    if [ $? -ne 0 ]; then
        echo "Error: Failed to purge Foundry resource."
        return 1
    fi

    echo "✓ Resource purged"
    echo "The Foundry resource has been deleted and purged."
}

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    # Check Foundry model deployment
    echo "Foundry Model Deployment (gpt-4o-mini):"
    foundry_deployment_status=$(az cognitiveservices account deployment show \
        --name "$foundry_resource" \
        --resource-group "$rg" \
        --deployment-name "gpt-4o-mini" \
        --query "properties.provisioningState" -o tsv 2>/dev/null)

    if [ ! -z "$foundry_deployment_status" ]; then
        echo "  Status: $foundry_deployment_status"
        if [ "$foundry_deployment_status" = "Succeeded" ]; then
            echo "  ✓ Model deployed and ready"
        fi
    else
        echo "  Status: Not found or not deployed"
    fi

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
    read -p "Please select an option (1-8): " choice

    case $choice in
        1)
            echo ""
            provision_foundry_resources
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            delete_foundry_resource
            echo ""
            read -p "Press Enter to continue..."
            ;;
        3)
            echo ""
            create_resource_group
            echo ""
            create_acr
            echo ""
            read -p "Press Enter to continue..."
            ;;
        4)
            echo ""
            build_and_push_image
            echo ""
            read -p "Press Enter to continue..."
            ;;
        5)
            echo ""
            create_aks_cluster
            echo ""
            read -p "Press Enter to continue..."
            ;;
        6)
            echo ""
            check_deployment_status
            echo ""
            read -p "Press Enter to continue..."
            ;;
        7)
            echo ""
            deploy_to_aks
            echo ""
            read -p "Press Enter to continue..."
            ;;
        8)
            echo "Exiting..."
            clear
            exit 0
            ;;
        *)
            echo "Invalid option. Please select 1-8."
            read -p "Press Enter to continue..."
            ;;
    esac
done
