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
$foundryResource = "foundry-resource-$userHash"
$acrName = "acr$userHash"
$aksCluster = "aks-$userHash"
$apiImageName = "aks-api"
$aksVmSize = "Standard_D2s_v7"

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
    Write-Host "    AKS Deployment with Foundry Model Integration"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Location: $location"
    Write-Host "Foundry Resource: $foundryResource"
    Write-Host "ACR Name: $acrName"
    Write-Host "AKS Cluster: $aksCluster"
    Write-Host "====================================================================="
    Write-Host "1. Provision gpt-5-mini model in Microsoft Foundry"
    Write-Host "2. Create Azure Container Registry (ACR)"
    Write-Host "3. Build and push API image to ACR"
    Write-Host "4. Create AKS cluster"
    Write-Host "5. Check deployment status"
    Write-Host "6. Deploy to AKS"
    Write-Host "7. Delete/Purge Foundry deployment"
    Write-Host "8. Delete failed AKS deployment"
    Write-Host "9. Exit"
    Write-Host "====================================================================="
}

# Function to provision Microsoft Foundry project and deploy gpt-5-mini model using Azure CLI
function Provision-FoundryResources {
    Write-Host "Provisioning Microsoft Foundry project with gpt-5-mini model..."
    Write-Host ""

    # Check if we're authenticated with Azure
    $accountCheck = az account show 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Not authenticated with Azure. Please run: az login"
        return $false
    }

    # Check if resource group exists, create if needed
    Write-Host "Checking resource group: $rg"
    $rgExists = az group exists --name $rg
    if ($rgExists -eq "false") {
        Write-Host "Creating resource group: $rg in $location"
        if (-not (Invoke-Quiet "Create resource group" {
            az group create --name $rg --location $location --only-show-errors
        })) { return $false }
    }
    else {
        Write-Host "$([char]0x2713) Resource group already exists"
    }

    # Create Foundry resource (AIServices kind)
    Write-Host ""
    Write-Host "Checking for existing Microsoft Foundry resource: $foundryResource"

    $foundryCheck = az cognitiveservices account show --name $foundryResource --resource-group $rg 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Creating Microsoft Foundry resource: $foundryResource"
        $created = Invoke-Quiet "Create Microsoft Foundry resource" {
            az cognitiveservices account create `
                --name $foundryResource `
                --resource-group $rg `
                --location $location `
                --custom-domain $foundryResource `
                --kind AIServices `
                --sku s0 `
                --yes `
                --only-show-errors
        }
        if (-not $created) { return $false }
        Write-Host "$([char]0x2713) Foundry resource created"
        Write-Host "Waiting for resource to be fully ready..."
        Start-Sleep -Seconds 10
    }
    else {
        Write-Host "$([char]0x2713) Foundry resource already exists"
    }

    # Retrieve endpoint for the resource
    Write-Host ""
    Write-Host "Retrieving Foundry endpoint..."
    $endpoint = az cognitiveservices account show `
        --name $foundryResource `
        --resource-group $rg `
        --query properties.endpoint -o tsv 2>&1 | Where-Object { $_ -notmatch 'ERROR' } | Select-Object -First 1

    if ([string]::IsNullOrEmpty($endpoint)) {
        Write-Host "Error: Failed to retrieve endpoint."
        return $false
    }
    Write-Host "$([char]0x2713) Endpoint retrieved successfully"

    # Deploy gpt-5-mini model
    Write-Host ""
    Write-Host "Checking for existing gpt-5-mini deployment..."
    $deploymentExists = az cognitiveservices account deployment show `
        --name $foundryResource `
        --resource-group $rg `
        --deployment-name "gpt-5-mini" `
        --query "name" -o tsv 2>$null

    if ([string]::IsNullOrEmpty($deploymentExists)) {
        Write-Host "Deploying gpt-5-mini model (this may take a few minutes)..."
        $deployed = Invoke-Quiet "Deploy gpt-5-mini model" {
            az cognitiveservices account deployment create `
                --name $foundryResource `
                --resource-group $rg `
                --deployment-name "gpt-5-mini" `
                --model-name "gpt-5-mini" `
                --model-version "2025-08-07" `
                --model-format "OpenAI" `
                --sku-capacity "1" `
                --sku-name "GlobalStandard" `
                --only-show-errors
        }
        if (-not $deployed) { return $false }
        Write-Host "$([char]0x2713) Model deployed successfully"
    }
    else {
        Write-Host "$([char]0x2713) gpt-5-mini deployment already exists"
    }

    Write-Host ""
    Write-Host "$([char]0x2713) Foundry provisioning complete!"
    Write-Host ""
    Write-Host "Foundry Resource Details:"
    Write-Host "  Resource: $foundryResource"
    Write-Host "  Endpoint: $endpoint"

    return $true
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
            Write-Host "Review the Azure error, correct the underlying issue, then use option 8"
            Write-Host "to delete the failed deployment before running option 4 again."
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
        Write-Host "Correct the reported issue, then use option 8 to delete any failed deployment."
        return $false
    }

    $duration = (Get-Date) - $startTime
    $minutes = [math]::Floor($duration.TotalMinutes)
    $seconds = $duration.Seconds
    Write-Host "AKS cluster creation completed: $aksCluster"
    Write-Host "  Deployment time: ${minutes}m ${seconds}s"
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

# Function to deploy to AKS
function Deploy-ToAKS {
    Write-Host "Deploying application to AKS..."
    Write-Host ""

    # Get AKS credentials
    Write-Host "Getting AKS credentials..."
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

    # Get Foundry endpoint
    Write-Host "Retrieving Foundry endpoint..."
    $endpoint = az cognitiveservices account show --name $foundryResource --resource-group $rg --query "properties.endpoint" -o tsv 2>$null

    if ([string]::IsNullOrEmpty($endpoint)) {
        Write-Host "Error: Could not retrieve Foundry endpoint."
        return $false
    }
    Write-Host "$([char]0x2713) Foundry endpoint retrieved"
    Write-Host ""

    # Assign Cognitive Services OpenAI User role to AKS kubelet identity
    Write-Host "Assigning Cognitive Services OpenAI User role to AKS identity..."
    $kubeletIdentity = az aks show --name $aksCluster --resource-group $rg --query "identityProfile.kubeletidentity.objectId" -o tsv 2>$null

    $foundryResourceId = az cognitiveservices account show --name $foundryResource --resource-group $rg --query "id" -o tsv 2>$null

    if ([string]::IsNullOrEmpty($kubeletIdentity) -or [string]::IsNullOrEmpty($foundryResourceId)) {
        Write-Host "Error: Could not retrieve AKS identity or Foundry resource ID."
        return $false
    }

    $assigned = Invoke-Quiet "Assign Cognitive Services OpenAI User role" {
        az role assignment create `
            --assignee-object-id $kubeletIdentity `
            --assignee-principal-type ServicePrincipal `
            --role "Cognitive Services OpenAI User" `
            --scope $foundryResourceId `
            --only-show-errors
    }
    if (-not $assigned) { return $false }

    Write-Host "Role assigned to AKS kubelet identity (may take 1-2 minutes to propagate)"
    Write-Host ""

    # Update the deployment.yaml with the correct ACR endpoint and Foundry endpoint
    Write-Host "Deploying Kubernetes manifests..."
    $deploymentContent = Get-Content k8s/deployment.yaml -Raw
    $deploymentContent = $deploymentContent -replace "ACR_ENDPOINT", "$acrName.azurecr.io"
    $deploymentContent = $deploymentContent -replace "FOUNDRY_ENDPOINT", $endpoint
    $deploymentContent | kubectl apply -f - -n default 2>$null | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to apply deployment manifest."
        return $false
    }

    Write-Host "$([char]0x2713) Deployment manifest updated with ACR endpoint: $acrName.azurecr.io and Foundry endpoint"

    # Apply the service manifest
    kubectl apply -f k8s/service.yaml -n default 2>$null | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to apply service manifest."
        return $false
    }

    Write-Host "$([char]0x2713) Service manifest applied"
    Write-Host ""

    # Wait for LoadBalancer service to get external IP
    Write-Host "Waiting for LoadBalancer external IP (this may take a few minutes)..."
    $maxAttempts = 60
    $attempt = 0
    $externalIp = ""

    while ($attempt -lt $maxAttempts) {
        $externalIp = (kubectl get svc aks-api-service -o jsonpath='{.status.loadBalancer.ingress[0].ip}' -n default 2>&1) | Where-Object { $_ -notmatch 'Error' -and $_ -notmatch 'not found' } | Select-Object -First 1
        if (-not [string]::IsNullOrEmpty($externalIp) -and -not $externalIp.StartsWith("10.")) {
            break
        }
        $attempt++
        Start-Sleep -Seconds 2
    }

    if ([string]::IsNullOrEmpty($externalIp)) {
        Write-Host "Error: Could not obtain external IP for the service."
        Write-Host "You can check the service status manually with: kubectl get svc aks-api-service"
        return $false
    }

    Write-Host "$([char]0x2713) External IP obtained: $externalIp"
    Write-Host ""

    # Update client/.env with the API endpoint
    Write-Host "Updating client/.env with API endpoint..."
@"
# API Endpoint for AKS-deployed service
API_ENDPOINT=http://$externalIp
"@ | Out-File -FilePath client/.env -Encoding utf8
    Write-Host "$([char]0x2713) client/.env updated"
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

# Function to delete and purge Foundry resource
function Delete-FoundryResource {
    Write-Host "Deleting and purging Foundry resource: $foundryResource"
    Write-Host ""
    $confirm = Read-Host "Are you sure you want to delete the Foundry resources? (yes/no)"

    if ($confirm -ne "yes") {
        Write-Host "Cancelled. Foundry resource was not deleted."
        return $true
    }

    Write-Host ""
    $foundryCheck = az cognitiveservices account show --name $foundryResource --resource-group $rg 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Foundry resource does not exist: $foundryResource"
        return $true
    }

    Write-Host "Deleting Foundry resource..."
    $deleteOutput = az cognitiveservices account delete --name $foundryResource --resource-group $rg 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to delete Foundry resource."
        Write-Host "Details: $deleteOutput"
        return $false
    }

    Write-Host "$([char]0x2713) Resource deleted"
    Write-Host ""
    Write-Host "Purging resource to free up the name..."
    $purgeOutput = az cognitiveservices account purge `
        --name $foundryResource `
        --resource-group $rg `
        --location $location 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to purge Foundry resource."
        Write-Host "Details: $purgeOutput"
        return $false
    }

    Write-Host "$([char]0x2713) Resource purged"
    Write-Host "The Foundry resource has been deleted and purged."

    return $true
}

# Function to check deployment status
function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    # Check Foundry model deployment
    Write-Host "Foundry Model Deployment (gpt-5-mini):"
    $foundryDeploymentStatus = az cognitiveservices account deployment show --name $foundryResource --resource-group $rg --deployment-name "gpt-5-mini" --query "properties.provisioningState" -o tsv 2>&1 | Where-Object { $_ -notmatch 'ERROR' } | Select-Object -First 1

    if (-not [string]::IsNullOrEmpty($foundryDeploymentStatus)) {
        Write-Host "  Status: $foundryDeploymentStatus"
        if ($foundryDeploymentStatus -eq "Succeeded") {
            Write-Host "  $([char]0x2713) Model deployed and ready"
        }
    }
    else {
        Write-Host "  Status: Not found or not deployed"
    }

    # Check ACR
    Write-Host ""
    Write-Host "Azure Container Registry ($acrName):"
    $acrStatus = az acr show --resource-group $rg --name $acrName --query "provisioningState" -o tsv 2>&1 | Where-Object { $_ -notmatch 'ERROR' } | Select-Object -First 1
    if (-not [string]::IsNullOrEmpty($acrStatus)) {
        Write-Host "  Status: $acrStatus"
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

    return $true
}

# Main menu loop
while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-9)"

    if ($choice -in @("1", "2", "3", "4", "5", "6", "7", "8", "9")) {
        Clear-Host
    }

    switch ($choice) {
        "1" {
            Write-Host ""
            Provision-FoundryResources | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "2" {
            Write-Host ""
            if (Create-ResourceGroup) {
                Write-Host ""
                Create-ACR | Out-Null
            }
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "3" {
            Write-Host ""
            Build-AndPushImage | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "4" {
            Write-Host ""
            Create-AKSCluster | Out-Null
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
            Deploy-ToAKS | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "7" {
            Write-Host ""
            Delete-FoundryResource | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "8" {
            Write-Host ""
            Remove-FailedAKSDeployment | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "9" {
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host "Invalid option. Please select 1-9."
            Read-Host "Press Enter to continue"
        }
    }
}
