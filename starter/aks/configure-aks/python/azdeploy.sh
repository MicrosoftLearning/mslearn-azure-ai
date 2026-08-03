#!/usr/bin/env bash

# Change the values of these variables as needed

rg="<your-resource-group-name>"  # Resource Group name
location="<your-azure-region>"   # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Disable Git Bash forward-slash path conversion (Windows only; no-op elsewhere).
export MSYS_NO_PATHCONV=1

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
aks_vm_size="Standard_D2s_v7"

# Run action commands quietly while preserving actionable failure details.
run_quiet() {
    local description="$1"
    shift
    local output rc
    output=$("$@" 2>&1)
    rc=$?
    if [ $rc -ne 0 ]; then
        echo "Error: ${description} failed (exit code ${rc})."
        if [ -n "$output" ]; then
            echo "$output"
        fi
        return $rc
    fi
    return 0
}

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
    echo "6. Delete failed AKS deployment"
    echo "7. Exit"
    echo "====================================================================="
}

# Function to create resource group if it doesn't exist
create_resource_group() {
    echo "Checking/creating resource group '$rg'..."

    local exists=$(az group exists --name $rg)
    if [ "$exists" = "false" ]; then
        run_quiet "Create resource group" az group create \
            --name $rg \
            --location $location \
            --only-show-errors || return 1
        echo "Resource group created: $rg"
    else
        echo "Resource group already exists: $rg"
    fi
}

# Function to create Azure Container Registry
create_acr() {
    echo "Creating Azure Container Registry '$acr_name'..."

    local existing_acr=$(az acr show --resource-group $rg --name $acr_name --query "name" -o tsv 2>/dev/null)
    if [ -z "$existing_acr" ]; then
        run_quiet "Create Azure Container Registry" az acr create \
            --resource-group $rg \
            --name $acr_name \
            --sku Basic \
            --admin-enabled true \
            --only-show-errors || return 1
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
    run_quiet "Build and push API image" az acr build \
        --resource-group $rg \
        --registry $acr_name \
        --image ${api_image_name}:latest \
        --file api/Dockerfile \
        --no-logs \
        --only-show-errors \
        api/ || return 1

    echo "Image built and pushed: ${acr_server}/${api_image_name}:latest"
}

# Function to create AKS cluster
create_aks_cluster() {
    local aks_state=$(az aks show --resource-group $rg --name $aks_cluster --query "provisioningState" -o tsv 2>/dev/null)
    case "$aks_state" in
        "Succeeded")
            echo "AKS cluster already exists: $aks_cluster (State: $aks_state)"
            return 0
            ;;
        "Failed"|"Canceled")
            echo "Error: AKS cluster '$aks_cluster' is in a $aks_state state."
            echo "Review the Azure error, correct the underlying issue, then use option 6"
            echo "to delete the failed deployment before running option 3 again."
            return 1
            ;;
        "")
            ;;
        *)
            echo "AKS cluster '$aks_cluster' is still provisioning (State: $aks_state)."
            echo "Please wait for it to finish, then check the deployment status from the menu."
            return 0
            ;;
    esac

    echo "Creating AKS cluster '$aks_cluster' with one $aks_vm_size node..."
    echo "This may take 5-10 minutes to complete. Please wait..."
    echo ""
    local start_time=$(date +%s)

    if ! run_quiet "Create AKS cluster" az aks create \
        --resource-group $rg \
        --location $location \
        --name $aks_cluster \
        --node-count 1 \
        --node-vm-size $aks_vm_size \
        --tier free \
        --vm-set-type VirtualMachineScaleSets \
        --load-balancer-sku standard \
        --enable-managed-identity \
        --network-plugin azure \
        --no-ssh-key \
        --attach-acr $acr_name \
        --only-show-errors; then
        echo ""
        echo "The AKS deployment failed. Review the Azure error details above."
        echo "Quota checks can fail before a cluster is created, while later failures"
        echo "can leave a cluster in a Failed state. Use option 5 to check the status."
        echo "For regional capacity or SKU availability errors, change the 'location'"
        echo "variable near the top of this script. For quota errors, use a region with"
        echo "available quota or request a quota increase."
        echo "Correct the reported issue, then use option 6 to delete any failed deployment."
        return 1
    fi

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))

    echo "AKS cluster creation completed: $aks_cluster"
    echo "  Deployment time: ${minutes}m ${seconds}s"

    # Assign Storage Account Contributor role to kubelet identity for Azure Files support
    echo "Configuring storage permissions for Azure Files..."
    local kubelet_id=$(az aks show --resource-group $rg --name $aks_cluster --query "identityProfile.kubeletidentity.clientId" -o tsv 2>/dev/null)
    local node_rg=$(az aks show --resource-group $rg --name $aks_cluster --query "nodeResourceGroup" -o tsv 2>/dev/null)
    local subscription_id=$(az account show --query id -o tsv 2>/dev/null)

    if [ -z "$kubelet_id" ] || [ -z "$node_rg" ] || [ -z "$subscription_id" ]; then
        echo "Error: Could not retrieve the AKS identity or node resource group."
        return 1
    fi

    run_quiet "Configure storage permissions" az role assignment create \
        --role "Storage Account Contributor" \
        --assignee "$kubelet_id" \
        --scope "/subscriptions/$subscription_id/resourceGroups/$node_rg" \
        --only-show-errors || return 1

    echo "Storage permissions configured"
}

# Function to delete an AKS deployment only when it is in a failed terminal state
delete_failed_aks_deployment() {
    local aks_state=$(az aks show --resource-group $rg --name $aks_cluster --query "provisioningState" -o tsv 2>/dev/null)

    if [ -z "$aks_state" ]; then
        echo "No AKS deployment was found: $aks_cluster"
        return 0
    fi

    if [ "$aks_state" != "Failed" ] && [ "$aks_state" != "Canceled" ]; then
        echo "Error: Refusing to delete AKS cluster '$aks_cluster' (State: $aks_state)."
        echo "This option only deletes deployments in a Failed or Canceled state."
        return 1
    fi

    echo "WARNING: This permanently deletes AKS cluster '$aks_cluster' and its"
    echo "AKS-managed resources. This action cannot be undone."
    read -p "Are you sure you want to delete the failed deployment? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        echo "Deletion canceled."
        return 0
    fi

    run_quiet "Delete failed AKS deployment" az aks delete \
        --resource-group $rg \
        --name $aks_cluster \
        --yes \
        --only-show-errors || return 1

    echo "Failed AKS deployment deleted: $aks_cluster"
}

# Function to get AKS credentials
get_aks_credentials() {
    echo "Getting AKS credentials for kubectl..."
    echo ""

    # Get AKS credentials
    run_quiet "Get AKS credentials" az aks get-credentials \
        --resource-group "$rg" \
        --name "$aks_cluster" \
        --overwrite-existing \
        --only-show-errors || return 1

    echo "AKS credentials configured"
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
    read -p "Please select an option (1-7): " choice

    case $choice in
        1|2|3|4|5|6|7) clear ;;
    esac

    case $choice in
        1)
            echo ""
            if create_resource_group; then
                echo ""
                create_acr
            fi
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
            echo ""
            delete_failed_aks_deployment
            echo ""
            read -p "Press Enter to continue..."
            ;;
        7)
            echo "Exiting..."
            clear
            exit 0
            ;;
        *)
            echo "Invalid option. Please select 1-7."
            read -p "Press Enter to continue..."
            ;;
    esac
done
