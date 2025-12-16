# Change the values of these variables as needed

# $rg = "<your-resource-group-name>"  # Resource Group name
# $location = "<your-azure-region>"   # Azure region for the resources

$rg = "rg-exercises"           # Resource Group name
$location = "eastus2"          # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from Azure user object ID (based on az login account)
$userObjectId = (az ad signed-in-user show --query "id" -o tsv 2>&1) | Where-Object { $_ -notmatch 'ERROR' } | Select-Object -First 1
if ([string]::IsNullOrEmpty($userObjectId)) {
    Write-Host "Error: Not authenticated with Azure. Please run: az login"
    exit 1
}

# Create hash from user object ID
$sha1 = [System.Security.Cryptography.SHA1]::Create()
$hashBytes = $sha1.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($userObjectId))
$userHash = [System.BitConverter]::ToString($hashBytes).Replace("-", "").Substring(0, 8).ToLower()

# Resource names with hash for uniqueness
$acrName = "acr$userHash"
$aksCluster = "aks-$userHash"
$apiImageName = "aks-config-api"

# Function to display menu
function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    AKS Configuration Exercise - Deployment Script"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Location: $location"
    Write-Host "ACR Name: $acrName"
    Write-Host "AKS Cluster: $aksCluster"
    Write-Host "====================================================================="
    Write-Host "1. Create Azure Container Registry (ACR)"
    Write-Host "2. Build and push API image to ACR"
    Write-Host "3. Create AKS cluster"
    Write-Host "4. Deploy API to AKS (Deployment and Service only)"
    Write-Host "5. Check deployment status"
    Write-Host "6. Exit"
    Write-Host "====================================================================="
}

# Function to create resource group if it doesn't exist
function Create-ResourceGroup {
    Write-Host "Checking/creating resource group '$rg'..."

    $exists = az group exists --name $rg
    if ($exists -eq "false") {
        az group create --name $rg --location $location 2>&1 | Out-Null
        Write-Host "Resource group created: $rg"
    }
    else {
        Write-Host "Resource group already exists: $rg"
    }

    return $true
}

# Function to create Azure Container Registry
function Create-ACR {
    Write-Host "Creating Azure Container Registry '$acrName'..."

    $acrCheck = az acr show --resource-group $rg --name $acrName 2>&1
    if ($LASTEXITCODE -ne 0) {
        az acr create `
            --resource-group $rg `
            --name $acrName `
            --sku Basic `
            --admin-enabled true 2>&1 | Out-Null
        Write-Host "ACR created: $acrName"
    }
    else {
        Write-Host "ACR already exists: $acrName"
    }

    return $true
}

# Function to build and push API image
function Build-AndPushImage {
    Write-Host "Building and pushing API image to ACR..."

    # Get ACR login server
    $acrServer = az acr show --resource-group $rg --name $acrName --query loginServer -o tsv

    if ([string]::IsNullOrEmpty($acrServer)) {
        Write-Host "Error: Could not retrieve ACR login server."
        return $false
    }

    # Build image using ACR Tasks
    az acr build `
        --resource-group $rg `
        --registry $acrName `
        --image "${apiImageName}:latest" `
        --file api/Dockerfile `
        api/ 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Image built and pushed: ${acrServer}/${apiImageName}:latest"
        return $true
    }
    else {
        Write-Host "Error building/pushing image."
        return $false
    }
}

# Function to create AKS cluster
function Create-AKSCluster {
    Write-Host "Creating AKS cluster '$aksCluster'..."
    Write-Host "This may take 5-10 minutes to complete. Please wait..."
    Write-Host ""

    $aksCheck = az aks show --resource-group $rg --name $aksCluster 2>&1
    if ($LASTEXITCODE -ne 0) {
        $startTime = Get-Date

        az aks create `
            --resource-group $rg `
            --name $aksCluster `
            --node-count 1 `
            --vm-set-type VirtualMachineScaleSets `
            --load-balancer-sku standard `
            --enable-managed-identity `
            --network-plugin azure `
            --generate-ssh-keys `
            --attach-acr $acrName 2>&1 | Out-Null

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: Failed to create AKS cluster."
            return $false
        }

        # Verify cluster is fully provisioned and nodes are Running
        Write-Host "Waiting for cluster to be fully operational..."
        az aks wait --resource-group $rg --name $aksCluster --updated 2>&1 | Out-Null

        $endTime = Get-Date
        $duration = $endTime - $startTime
        $minutes = [math]::Floor($duration.TotalMinutes)
        $seconds = $duration.Seconds

        Write-Host "✓ AKS cluster creation completed: $aksCluster"
        Write-Host "  Deployment time: ${minutes}m ${seconds}s"
    }
    else {
        Write-Host "AKS cluster already exists: $aksCluster"
    }

    return $true
}

# Function to deploy to AKS
function Deploy-ToAKS {
    Write-Host "Deploying API to AKS..."
    Write-Host ""
    Write-Host "NOTE: This script only deploys the Deployment and Service."
    Write-Host "Students should manually create ConfigMap, Secrets, and PVC first."
    Write-Host ""

    # Get AKS credentials
    Write-Host "Getting AKS credentials..."
    az aks get-credentials `
        --resource-group $rg `
        --name $aksCluster `
        --overwrite-existing 2>&1 | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to get AKS credentials."
        return $false
    }
    Write-Host "✓ AKS credentials configured"
    Write-Host ""

    # Verify required Kubernetes resources exist
    Write-Host "Verifying required Kubernetes resources..."

    # Check ConfigMap
    $configMapCheck = kubectl get configmap api-config -n default 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠ Warning: ConfigMap 'api-config' not found. Please create it first."
        Write-Host "  Use: kubectl apply -f k8s/configmap.yaml"
    } else {
        Write-Host "✓ ConfigMap 'api-config' found"
    }

    # Check Secrets
    $secretCheck = kubectl get secret api-secrets -n default 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠ Warning: Secret 'api-secrets' not found. Please create it first."
        Write-Host "  Use: kubectl apply -f k8s/secrets.yaml"
    } else {
        Write-Host "✓ Secret 'api-secrets' found"
    }

    # Check PVC
    $pvcCheck = kubectl get pvc api-logs-pvc -n default 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "⚠ Warning: PersistentVolumeClaim 'api-logs-pvc' not found. Please create it first."
        Write-Host "  Use: kubectl apply -f k8s/pvc.yaml"
    } else {
        Write-Host "✓ PersistentVolumeClaim 'api-logs-pvc' found"
    }

    Write-Host ""
    $confirm = Read-Host "Continue with deployment? (yes/no)"
    if ($confirm -ne "yes") {
        Write-Host "Deployment cancelled."
        return $true
    }
    Write-Host ""

    # Update the deployment.yaml with the correct ACR endpoint
    Write-Host "Deploying Kubernetes manifests..."
    $deploymentContent = Get-Content k8s/deployment.yaml -Raw
    $deploymentContent = $deploymentContent -replace "ACR_ENDPOINT", "$acrName.azurecr.io"
    $deploymentContent | kubectl apply -f - -n default 2>&1 | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to apply deployment manifest."
        return $false
    }

    Write-Host "✓ Deployment manifest applied with ACR endpoint: $acrName.azurecr.io"

    # Apply the service manifest
    kubectl apply -f k8s/service.yaml -n default 2>&1 | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to apply service manifest."
        return $false
    }

    Write-Host "✓ Service manifest applied"
    Write-Host ""

    # Wait for LoadBalancer service to get external IP
    Write-Host "Waiting for LoadBalancer external IP (this may take a few minutes)..."
    $maxAttempts = 60
    $attempt = 0
    $externalIp = ""

    while ($attempt -lt $maxAttempts) {
        $externalIp = (kubectl get svc aks-config-api-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}' -n default 2>&1) | Where-Object { $_ -notmatch 'Error' -and $_ -notmatch 'not found' } | Select-Object -First 1
        if (-not [string]::IsNullOrEmpty($externalIp) -and -not $externalIp.StartsWith("10.")) {
            break
        }
        $attempt++
        Start-Sleep -Seconds 2
    }

    if ([string]::IsNullOrEmpty($externalIp)) {
        Write-Host "Error: Could not obtain external IP for the service."
        Write-Host "You can check the service status manually with: kubectl get svc aks-config-api-service"
        return $false
    }

    Write-Host "✓ External IP obtained: $externalIp"
    Write-Host ""

    # Update client/.env with the API endpoint
    Write-Host "Updating client/.env with API endpoint..."
@"
# API Endpoint for AKS-deployed service
API_ENDPOINT=http://$externalIp
"@ | Out-File -FilePath client/.env -Encoding utf8
    Write-Host "✓ client/.env updated"
    Write-Host ""
    Write-Host "=========================================="
    Write-Host "Deployment completed successfully!"
    Write-Host "=========================================="
    Write-Host "API Endpoint: http://$externalIp"
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "1. Run the client to test the API:"
    Write-Host "   python client/main.py"
    Write-Host "=========================================="

    return $true
}

# Function to check deployment status
function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    # Check ACR
    Write-Host "Azure Container Registry ($acrName):"
    $acrStatus = az acr show --resource-group $rg --name $acrName --query "provisioningState" -o tsv 2>&1 | Where-Object { $_ -notmatch 'ERROR' } | Select-Object -First 1
    if (-not [string]::IsNullOrEmpty($acrStatus)) {
        Write-Host "  Status: $acrStatus"
        if ($acrStatus -eq "Succeeded") {
            Write-Host "  ✓ ACR is ready"
        }
    }
    else {
        Write-Host "  Status: Not found or not ready"
    }

    # Check AKS
    Write-Host ""
    Write-Host "AKS Cluster ($aksCluster):"
    $aksStatus = az aks show --resource-group $rg --name $aksCluster --query "provisioningState" -o tsv 2>&1 | Where-Object { $_ -notmatch 'ERROR' } | Select-Object -First 1
    if (-not [string]::IsNullOrEmpty($aksStatus)) {
        Write-Host "  Status: $aksStatus"
        if ($aksStatus -eq "Succeeded") {
            Write-Host "  ✓ AKS cluster is ready for deployment"
        }
    }
    else {
        Write-Host "  Status: Not found or not ready"
    }

    # Check Kubernetes resources if kubectl is configured
    $kubectlCheck = kubectl cluster-info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Kubernetes Resources:"

        # Check ConfigMap
        $configMapStatus = kubectl get configmap api-config -n default -o jsonpath='{.metadata.name}' 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ConfigMap: ✓ Created"
        } else {
            Write-Host "  ConfigMap: Not created"
        }

        # Check Secret
        $secretStatus = kubectl get secret api-secrets -n default -o jsonpath='{.metadata.name}' 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  Secrets: ✓ Created"
        } else {
            Write-Host "  Secrets: Not created"
        }

        # Check PVC
        $pvcStatus = kubectl get pvc api-logs-pvc -n default -o jsonpath='{.status.phase}' 2>&1
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrEmpty($pvcStatus)) {
            Write-Host "  PVC: $pvcStatus"
        } else {
            Write-Host "  PVC: Not created"
        }

        # Check Deployment
        $deploymentStatus = kubectl get deployment aks-config-api -n default -o jsonpath='{.status.conditions[?(@.type=="Available")].status}' 2>&1
        if ($deploymentStatus -eq "True") {
            Write-Host "  Deployment: ✓ Available"
        } else {
            Write-Host "  Deployment: Not available"
        }

        # Check Service
        $serviceIp = kubectl get svc aks-config-api-service -n default -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>&1
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrEmpty($serviceIp)) {
            Write-Host "  Service: ✓ Exposed at $serviceIp"
        } else {
            Write-Host "  Service: LoadBalancer IP pending or not created"
        }
    }

    return $true
}

# Main menu loop
while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-6)"

    switch ($choice) {
        "1" {
            Write-Host ""
            Create-ResourceGroup | Out-Null
            Write-Host ""
            Create-ACR | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "2" {
            Write-Host ""
            Build-AndPushImage | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "3" {
            Write-Host ""
            Create-AKSCluster | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "4" {
            Write-Host ""
            Deploy-ToAKS | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "5" {
            Write-Host ""
            Check-DeploymentStatus | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "6" {
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host "Invalid option. Please select 1-6."
            Read-Host "Press Enter to continue"
        }
    }
}
