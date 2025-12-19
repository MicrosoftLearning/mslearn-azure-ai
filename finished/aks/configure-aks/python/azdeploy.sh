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
    echo "4. Get AKS credentials for kubectl"
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
        echo "ACR endpoint: $acr_name.azurecr.io"
    else
        echo "ACR already exists: $acr_name"
        echo "ACR endpoint: $acr_name.azurecr.io"
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

        # Assign Storage Account Contributor role to kubelet identity for Azure Files support
        echo "Configuring storage permissions for Azure Files..."
        local kubelet_id=$(az aks show --resource-group $rg --name $aks_cluster --query "identityProfile.kubeletidentity.clientId" -o tsv)
        local node_rg=$(az aks show --resource-group $rg --name $aks_cluster --query "nodeResourceGroup" -o tsv)

        az role assignment create \
            --role "Storage Account Contributor" \
            --assignee "$kubelet_id" \
            --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$node_rg" > /dev/null 2>&1

        echo "✓ Storage permissions configured"
    else
        echo "AKS cluster already exists: $aks_cluster"
    fi
}

# Function to get AKS credentials
get_aks_credentials() {
    echo "Getting AKS credentials for kubectl..."
    echo ""

    # Get AKS credentials
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
    echo "You can now use kubectl to interact with your AKS cluster."
    echo ""
    echo "Example commands:"
    echo "  kubectl get nodes"
    echo "  kubectl get pods -n default"
    echo "  kubectl apply -f k8s/configmap.yaml"
    echo "  kubectl apply -f k8s/secrets.yaml"
    echo "  kubectl apply -f k8s/pvc.yaml"
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
            get_aks_credentials
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
