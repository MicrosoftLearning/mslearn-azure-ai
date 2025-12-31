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
$apiImageName = "aks-troubleshoot-api"

# Function to display menu
function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    AKS Troubleshooting Exercise - Deployment Script"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Location: $location"
    Write-Host "ACR Name: $acrName"
    Write-Host "AKS Cluster: $aksCluster"
    Write-Host "====================================================================="
    Write-Host "1. Create Azure Container Registry (ACR)"
    Write-Host "2. Build and push API image to ACR"
    Write-Host "3. Create AKS cluster"
    Write-Host "4. Get AKS credentials for kubectl"
    Write-Host "5. Deploy application to AKS"
    Write-Host "6. Check deployment status"
    Write-Host "7. Exit"
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
    Write-Host "ACR endpoint: $acrName.azurecr.io"

    # Update all deployment YAML files with the ACR image URL
    Write-Host "Updating deployment YAML files with ACR image..."
    $imageUrl = "$acrName.azurecr.io/${apiImageName}:latest"
    Get-ChildItem -Path "k8s/*-deployment.yaml" | ForEach-Object {
        $content = Get-Content $_.FullName -Raw
        $content = $content -replace 'image:.*', "image: $imageUrl"
        Set-Content -Path $_.FullName -Value $content -NoNewline
    }
    Write-Host "✓ Deployment YAML files updated"

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

# Function to get AKS credentials
function Get-AKSCredentials {
    Write-Host "Getting AKS credentials for kubectl..."
    Write-Host ""

    # Get AKS credentials
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
    Write-Host "You can now use kubectl to interact with your AKS cluster."
    Write-Host ""
    Write-Host "Example commands:"
    Write-Host "  kubectl get nodes"
    Write-Host "  kubectl get pods --all-namespaces"

    return $true
}

# Function to deploy application to AKS
function Deploy-ToAKS {
    Write-Host "Deploying application to AKS..."
    Write-Host ""

    # Create namespace
    Write-Host "Creating namespace 'aks-troubleshoot'..."
    kubectl create namespace aks-troubleshoot --dry-run=client -o yaml | kubectl apply -f -

    # Apply deployment and service
    Write-Host "Deploying API..."
    kubectl apply -f k8s/api-deployment.yaml -n aks-troubleshoot

    # Apply service
    Write-Host "Creating Service..."
    kubectl apply -f k8s/api-service.yaml -n aks-troubleshoot

    Write-Host ""
    Write-Host "Waiting for deployment to be ready..."
    kubectl rollout status deployment/api-deployment -n aks-troubleshoot --timeout=120s

    Write-Host ""
    Write-Host "✓ Application deployed successfully!"
    Write-Host ""
    Write-Host "To test the application:"
    Write-Host "  kubectl port-forward service/api-service 8080:80 -n aks-troubleshoot"
    Write-Host "  curl http://localhost:8080/healthz"

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
            Write-Host "  ✓ AKS cluster is ready"
        }
    }
    else {
        Write-Host "  Status: Not found or not ready"
    }

    # Check Kubernetes resources if kubectl is configured
    $kubectlCheck = kubectl cluster-info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Kubernetes Resources (aks-troubleshoot namespace):"

        # Check namespace
        $nsStatus = kubectl get namespace aks-troubleshoot -o jsonpath='{.status.phase}' 2>&1
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrEmpty($nsStatus)) {
            Write-Host "  Namespace: ✓ $nsStatus"
        } else {
            Write-Host "  Namespace: Not created"
        }

        # Check Deployment
        $deploymentReady = kubectl get deployment api-deployment -n aks-troubleshoot -o jsonpath='{.status.readyReplicas}' 2>&1
        $deploymentDesired = kubectl get deployment api-deployment -n aks-troubleshoot -o jsonpath='{.spec.replicas}' 2>&1
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrEmpty($deploymentReady)) {
            Write-Host "  Deployment: ${deploymentReady}/${deploymentDesired} replicas ready"
        } else {
            Write-Host "  Deployment: Not created"
        }

        # Check Pods
        Write-Host ""
        Write-Host "  Pods:"
        $pods = kubectl get pods -n aks-troubleshoot -o custom-columns="NAME:.metadata.name,READY:.status.containerStatuses[0].ready,STATUS:.status.phase" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $pods -split "`n" | ForEach-Object { Write-Host "    $_" }
        } else {
            Write-Host "    No pods found"
        }

        # Check Service
        Write-Host ""
        Write-Host "  Service:"
        $svc = kubectl get svc -n aks-troubleshoot -o custom-columns="NAME:.metadata.name,TYPE:.spec.type,CLUSTER-IP:.spec.clusterIP,EXTERNAL-IP:.status.loadBalancer.ingress[0].ip,PORT:.spec.ports[0].port" 2>&1
        if ($LASTEXITCODE -eq 0) {
            $svc -split "`n" | ForEach-Object { Write-Host "    $_" }
        } else {
            Write-Host "    No services found"
        }

        # Check EndpointSlices
        Write-Host ""
        Write-Host "  EndpointSlices:"
        $endpointslices = kubectl get endpointslices -n aks-troubleshoot -o custom-columns="NAME:.metadata.name,ENDPOINTS:.endpoints[0].addresses[0]" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $endpointslices -split "`n" | ForEach-Object { Write-Host "    $_" }
        } else {
            Write-Host "    No endpoint slices found"
        }
    }

    return $true
}

# Main menu loop
while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-7)"

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
            Get-AKSCredentials | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "5" {
            Write-Host ""
            Deploy-ToAKS | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "6" {
            Write-Host ""
            Check-DeploymentStatus | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "7" {
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host "Invalid option. Please select 1-7."
            Read-Host "Press Enter to continue"
        }
    }
}
