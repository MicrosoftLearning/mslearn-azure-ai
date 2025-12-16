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
aks_cluster="aks-${user_hash}"
api_image_name="aks-config-api"

# Function to display menu
show_menu() {
    clear
    echo "====================================================================="
    echo "    AKS Configuration Exercise - Deployment Script"
    echo "====================================================================="
    echo "Resource Group: $rg"
    echo "Location: $location"
    echo "ACR Name: $acr_name"
    echo "AKS Cluster: $aks_cluster"
    echo "====================================================================="
    echo "1. Create Azure Container Registry (ACR)"
    echo "2. Build and push API image to ACR"
    echo "3. Create AKS cluster"
    echo "4. Deploy API to AKS (Deployment and Service only)"
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
    echo "Deploying API to AKS..."
    echo ""
    echo "NOTE: This script only deploys the Deployment and Service."
    echo "Students should manually create ConfigMap, Secrets, and PVC first."
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

    # Verify required Kubernetes resources exist
    echo "Verifying required Kubernetes resources..."

    # Check ConfigMap
    if ! kubectl get configmap api-config -n default &> /dev/null; then
        echo "⚠ Warning: ConfigMap 'api-config' not found. Please create it first."
        echo "  Use: kubectl apply -f k8s/configmap.yaml"
    else
        echo "✓ ConfigMap 'api-config' found"
    fi

    # Check Secrets
    if ! kubectl get secret api-secrets -n default &> /dev/null; then
        echo "⚠ Warning: Secret 'api-secrets' not found. Please create it first."
        echo "  Use: kubectl apply -f k8s/secrets.yaml"
    else
        echo "✓ Secret 'api-secrets' found"
    fi

    # Check PVC
    if ! kubectl get pvc api-logs-pvc -n default &> /dev/null; then
        echo "⚠ Warning: PersistentVolumeClaim 'api-logs-pvc' not found. Please create it first."
        echo "  Use: kubectl apply -f k8s/pvc.yaml"
    else
        echo "✓ PersistentVolumeClaim 'api-logs-pvc' found"
    fi

    echo ""
    read -p "Continue with deployment? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Deployment cancelled."
        return 0
    fi
    echo ""

    # Update the deployment.yaml with the correct ACR endpoint
    echo "Deploying Kubernetes manifests..."
    sed "s|ACR_ENDPOINT|${acr_name}.azurecr.io|g" k8s/deployment.yaml | kubectl apply -f - -n default 2>&1 > /dev/null

    if [ $? -ne 0 ]; then
        echo "Error: Failed to apply deployment manifest."
        return 1
    fi

    echo "✓ Deployment manifest applied with ACR endpoint: ${acr_name}.azurecr.io"

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
        external_ip=$(kubectl get svc aks-config-api-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}' -n default 2>/dev/null)
        if [ ! -z "$external_ip" ] && [[ "$external_ip" != "10."* ]]; then
            break
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    if [ -z "$external_ip" ]; then
        echo "Error: Could not obtain external IP for the service."
        echo "You can check the service status manually with: kubectl get svc aks-config-api-service"
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

# Function to check deployment status
check_deployment_status() {
    echo "Checking deployment status..."
    echo ""

    # Check ACR
    echo "Azure Container Registry ($acr_name):"
    acr_status=$(az acr show --resource-group $rg --name $acr_name --query "provisioningState" -o tsv 2>/dev/null)
    if [ ! -z "$acr_status" ]; then
        echo "  Status: $acr_status"
        if [ "$acr_status" = "Succeeded" ]; then
            echo "  ✓ ACR is ready"
        fi
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

    # Check Kubernetes resources if AKS credentials are available
    if kubectl cluster-info &> /dev/null; then
        echo ""
        echo "Kubernetes Resources:"

        # Check ConfigMap
        configmap_status=$(kubectl get configmap api-config -n default -o jsonpath='{.metadata.name}' 2>/dev/null)
        if [ ! -z "$configmap_status" ]; then
            echo "  ConfigMap: ✓ Created"
        else
            echo "  ConfigMap: Not created"
        fi

        # Check Secret
        secret_status=$(kubectl get secret api-secrets -n default -o jsonpath='{.metadata.name}' 2>/dev/null)
        if [ ! -z "$secret_status" ]; then
            echo "  Secrets: ✓ Created"
        else
            echo "  Secrets: Not created"
        fi

        # Check PVC
        pvc_status=$(kubectl get pvc api-logs-pvc -n default -o jsonpath='{.status.phase}' 2>/dev/null)
        if [ ! -z "$pvc_status" ]; then
            echo "  PVC: $pvc_status"
        else
            echo "  PVC: Not created"
        fi

        # Check Deployment
        deployment_status=$(kubectl get deployment aks-config-api -n default -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>/dev/null)
        if [ "$deployment_status" = "True" ]; then
            echo "  Deployment: ✓ Available"
        else
            echo "  Deployment: Not available"
        fi

        # Check Service
        service_ip=$(kubectl get svc aks-config-api-service -n default -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
        if [ ! -z "$service_ip" ]; then
            echo "  Service: ✓ Exposed at $service_ip"
        else
            echo "  Service: LoadBalancer IP pending or not created"
        fi
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
            create_acr
            echo ""
            read -p "Press Enter to continue..."
            ;;
        2)
            echo ""
            build_and_push_image
            echo ""
            read -p "Press Enter to continue..."
            ;;
        3)
            echo ""
            create_aks_cluster
            echo ""
            read -p "Press Enter to continue..."
            ;;
        4)
            echo ""
            deploy_to_aks
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
