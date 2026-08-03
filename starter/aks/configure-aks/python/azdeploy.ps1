# Change the values of these variables as needed

$rg = "<your-resource-group-name>"  # Resource Group name
$location = "<your-azure-region>"   # Azure region for the resources

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
$aksVmSize = "Standard_D2s_v5"

# Run action commands quietly while preserving actionable failure details.
function Invoke-Quiet {
    param(
        [string]$Description,
        [scriptblock]$Command
    )
    $output = & $Command 2>&1
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        Write-Host "Error: $Description failed (exit code $rc)."
        if ($output) {
            Write-Host ($output | Out-String)
        }
        return $false
    }
    return $true
}

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
    Write-Host "4. Get AKS credentials for kubectl"
    Write-Host "5. Check deployment status"
    Write-Host "6. Delete failed AKS deployment"
    Write-Host "7. Exit"
    Write-Host "====================================================================="
}

# Function to create resource group if it doesn't exist
function Create-ResourceGroup {
    Write-Host "Checking/creating resource group '$rg'..."

    $exists = az group exists --name $rg
    if ($exists -eq "false") {
        if (-not (Invoke-Quiet "Create resource group" {
            az group create --name $rg --location $location --only-show-errors
        })) { return $false }
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

    $existingAcr = az acr show --resource-group $rg --name $acrName --query "name" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($existingAcr)) {
        $created = Invoke-Quiet "Create Azure Container Registry" {
            az acr create `
                --resource-group $rg `
                --name $acrName `
                --sku Basic `
                --admin-enabled true `
                --only-show-errors
        }
        if (-not $created) { return $false }
        Write-Host "ACR created: $acrName"
        Write-Host "ACR endpoint: $acrName.azurecr.io"
    }
    else {
        Write-Host "ACR already exists: $acrName"
        Write-Host "ACR endpoint: $acrName.azurecr.io"
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
    $built = Invoke-Quiet "Build and push API image" {
        az acr build `
            --resource-group $rg `
            --registry $acrName `
            --image "${apiImageName}:latest" `
            --file api/Dockerfile `
            --no-logs `
            --only-show-errors `
            api/
    }
    if (-not $built) { return $false }

    Write-Host "Image built and pushed: ${acrServer}/${apiImageName}:latest"
    return $true
}

# Function to create AKS cluster
function Create-AKSCluster {
    $aksState = az aks show --resource-group $rg --name $aksCluster --query "provisioningState" -o tsv 2>$null
    switch ($aksState) {
        "Succeeded" {
            Write-Host "AKS cluster already exists: $aksCluster (State: $aksState)"
            return $true
        }
        { $_ -eq "Failed" -or $_ -eq "Canceled" } {
            Write-Host "Error: AKS cluster '$aksCluster' is in a $aksState state."
            Write-Host "Review the Azure error, correct the underlying issue, then use option 6"
            Write-Host "to delete the failed deployment before running option 3 again."
            return $false
        }
        "" {}
        $null {}
        default {
            Write-Host "AKS cluster '$aksCluster' is still provisioning (State: $aksState)."
            Write-Host "Please wait for it to finish, then check the deployment status from the menu."
            return $true
        }
    }

    Write-Host "Creating AKS cluster '$aksCluster' with one $aksVmSize node..."
    Write-Host "This may take 5-10 minutes to complete. Please wait..."
    Write-Host ""
    $startTime = Get-Date

    $created = Invoke-Quiet "Create AKS cluster" {
        az aks create `
            --resource-group $rg `
            --location $location `
            --name $aksCluster `
            --node-count 1 `
            --node-vm-size $aksVmSize `
            --tier free `
            --vm-set-type VirtualMachineScaleSets `
            --load-balancer-sku standard `
            --enable-managed-identity `
            --network-plugin azure `
            --no-ssh-key `
            --attach-acr $acrName `
            --only-show-errors
    }
    if (-not $created) {
        Write-Host ""
        Write-Host "The AKS deployment failed. Review the Azure error details above."
        Write-Host "Quota checks can fail before a cluster is created, while later failures"
        Write-Host "can leave a cluster in a Failed state. Use option 5 to check the status."
        Write-Host "For regional capacity or SKU availability errors, change the 'location'"
        Write-Host "variable near the top of this script. For quota errors, use a region with"
        Write-Host "available quota or request a quota increase."
        Write-Host "Correct the reported issue, then use option 6 to delete any failed deployment."
        return $false
    }

    $duration = (Get-Date) - $startTime
    $minutes = [math]::Floor($duration.TotalMinutes)
    $seconds = $duration.Seconds
    Write-Host "AKS cluster creation completed: $aksCluster"
    Write-Host "  Deployment time: ${minutes}m ${seconds}s"

    # Assign Storage Account Contributor role to kubelet identity for Azure Files support
    Write-Host "Configuring storage permissions for Azure Files..."
    $kubeletId = az aks show --resource-group $rg --name $aksCluster --query "identityProfile.kubeletidentity.clientId" -o tsv 2>$null
    $nodeRg = az aks show --resource-group $rg --name $aksCluster --query "nodeResourceGroup" -o tsv 2>$null
    $subscriptionId = az account show --query id -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($kubeletId) -or [string]::IsNullOrWhiteSpace($nodeRg) -or [string]::IsNullOrWhiteSpace($subscriptionId)) {
        Write-Host "Error: Could not retrieve the AKS identity or node resource group."
        return $false
    }

    $assigned = Invoke-Quiet "Configure storage permissions" {
        az role assignment create `
            --role "Storage Account Contributor" `
            --assignee $kubeletId `
            --scope "/subscriptions/$subscriptionId/resourceGroups/$nodeRg" `
            --only-show-errors
    }
    if (-not $assigned) { return $false }

    Write-Host "Storage permissions configured"
    return $true
}

# Function to delete an AKS deployment only when it is in a failed terminal state
function Remove-FailedAKSDeployment {
    $aksState = az aks show --resource-group $rg --name $aksCluster --query "provisioningState" -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($aksState)) {
        Write-Host "No AKS deployment was found: $aksCluster"
        return $true
    }

    if ($aksState -ne "Failed" -and $aksState -ne "Canceled") {
        Write-Host "Error: Refusing to delete AKS cluster '$aksCluster' (State: $aksState)."
        Write-Host "This option only deletes deployments in a Failed or Canceled state."
        return $false
    }

    Write-Host "WARNING: This permanently deletes AKS cluster '$aksCluster' and its"
    Write-Host "AKS-managed resources. This action cannot be undone."
    $confirm = Read-Host "Are you sure you want to delete the failed deployment? (yes/no)"

    if ($confirm -ne "yes") {
        Write-Host "Deletion canceled."
        return $true
    }

    $deleted = Invoke-Quiet "Delete failed AKS deployment" {
        az aks delete `
            --resource-group $rg `
            --name $aksCluster `
            --yes `
            --only-show-errors
    }
    if (-not $deleted) { return $false }

    Write-Host "Failed AKS deployment deleted: $aksCluster"
    return $true
}

# Function to get AKS credentials
function Get-AKSCredentials {
    Write-Host "Getting AKS credentials for kubectl..."
    Write-Host ""

    # Get AKS credentials
    $configured = Invoke-Quiet "Get AKS credentials" {
        az aks get-credentials `
            --resource-group $rg `
            --name $aksCluster `
            --overwrite-existing `
            --only-show-errors
    }
    if (-not $configured) { return $false }

    Write-Host "AKS credentials configured"
    Write-Host ""
    Write-Host "You can now use kubectl to interact with your AKS cluster."
    Write-Host ""
    Write-Host "Example commands:"
    Write-Host "  kubectl get nodes"
    Write-Host "  kubectl get pods -n default"
    Write-Host "  kubectl apply -f k8s/configmap.yaml"
    Write-Host "  kubectl apply -f k8s/secrets.yaml"
    Write-Host "  kubectl apply -f k8s/pvc.yaml"

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
            Write-Host "  $([char]0x2713) ACR is ready"
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
            Write-Host "  $([char]0x2713) AKS cluster is ready for deployment"
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
            Write-Host "  ConfigMap: $([char]0x2713) Created"
        } else {
            Write-Host "  ConfigMap: Not created"
        }

        # Check Secret
        $secretStatus = kubectl get secret api-secrets -n default -o jsonpath='{.metadata.name}' 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  Secrets: $([char]0x2713) Created"
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
            Write-Host "  Deployment: $([char]0x2713) Available"
        } else {
            Write-Host "  Deployment: Not available"
        }

        # Check Service
        $serviceIp = kubectl get svc aks-config-api-service -n default -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>&1
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrEmpty($serviceIp)) {
            Write-Host "  Service: $([char]0x2713) Exposed at $serviceIp"
        } else {
            Write-Host "  Service: LoadBalancer IP pending or not created"
        }
    }

    return $true
}

# Main menu loop
while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-7)"

    if ($choice -in @("1", "2", "3", "4", "5", "6", "7")) {
        Clear-Host
    }

    switch ($choice) {
        "1" {
            Write-Host ""
            if (Create-ResourceGroup) {
                Write-Host ""
                Create-ACR | Out-Null
            }
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
            Check-DeploymentStatus | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "6" {
            Write-Host ""
            Remove-FailedAKSDeployment | Out-Null
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
