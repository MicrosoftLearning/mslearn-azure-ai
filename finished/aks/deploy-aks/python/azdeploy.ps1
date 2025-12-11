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
$foundryResource = "foundry-resource-$userHash"
$acrName = "acr$userHash"
$aksCluster = "aks-$userHash"
$apiImageName = "aks-api"

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
    Write-Host "1. Provision gpt-4o-mini model in Microsoft Foundry"
    Write-Host "2. Delete/Purge Foundry deployment"
    Write-Host "3. Create Azure Container Registry (ACR)"
    Write-Host "4. Build and push API image to ACR"
    Write-Host "5. Create AKS cluster"
    Write-Host "6. Check deployment status"
    Write-Host "7. Deploy to AKS"
    Write-Host "8. Exit"
    Write-Host "====================================================================="
}

# Function to provision Microsoft Foundry project and deploy gpt-4o-mini model using Azure CLI
function Provision-FoundryResources {
    Write-Host "Provisioning Microsoft Foundry project with gpt-4o-mini model..."
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
        az group create --name $rg --location $location 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: Failed to create resource group." -ForegroundColor Red
            return $false
        }
    }
    else {
        Write-Host "✓ Resource group already exists"
    }

    # Create Foundry resource (AIServices kind)
    Write-Host ""
    Write-Host "Checking for existing Microsoft Foundry resource: $foundryResource"

    $foundryExists = az cognitiveservices account show --name $foundryResource --resource-group $rg 2>&1 | Where-Object { $_ -notmatch 'ERROR' }

    if ([string]::IsNullOrEmpty($foundryExists)) {
        Write-Host "Creating Microsoft Foundry resource: $foundryResource"
        az cognitiveservices account create `
            --name $foundryResource `
            --resource-group $rg `
            --location $location `
            --kind AIServices `
            --sku s0 `
            --yes 2>&1 | Out-Null

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: Failed to create Foundry resource."
            return $false
        }
        Write-Host "✓ Foundry resource created"
    }
    else {
        Write-Host "✓ Foundry resource already exists"
    }

    # Retrieve endpoint and key for the resource
    Write-Host ""
    Write-Host "Retrieving Foundry credentials..."
    $endpoint = az cognitiveservices account show `
        --name $foundryResource `
        --resource-group $rg `
        --query properties.endpoint -o tsv

    $key = az cognitiveservices account keys list `
        --name $foundryResource `
        --resource-group $rg `
        --query key1 -o tsv

    if ([string]::IsNullOrEmpty($endpoint) -or [string]::IsNullOrEmpty($key)) {
        Write-Host "Error: Failed to retrieve endpoint or key."
        return $false
    }
    Write-Host "✓ Credentials retrieved successfully"

    # Deploy gpt-4o-mini model
    Write-Host ""
    Write-Host "Deploying gpt-4o-mini model (this may take a few minutes)..."
    az cognitiveservices account deployment create `
        --name $foundryResource `
        --resource-group $rg `
        --deployment-name "gpt-4o-mini" `
        --model-name "gpt-4o-mini" `
        --model-version "2024-07-18" `
        --model-format "OpenAI" `
        --sku-capacity "1" `
        --sku-name "Standard" 2>&1 | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to deploy model."
        return $false
    }
    Write-Host "✓ Model deployed successfully"

    Write-Host ""
    Write-Host "✓ Foundry provisioning complete!"
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

    $exists = az acr show --resource-group $rg --name $acrName 2>&1 | Where-Object { $_ -notmatch 'ERROR' }
    if ([string]::IsNullOrEmpty($exists)) {
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

    $exists = az aks show --resource-group $rg --name $aksCluster 2>&1 | Where-Object { $_ -notmatch 'ERROR' }
    if ([string]::IsNullOrEmpty($exists)) {
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
    Write-Host "Deploying application to AKS..."
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

    # Get Foundry credentials
    Write-Host "Retrieving Foundry credentials..."
    $endpoint = az cognitiveservices account show --name $foundryResource --resource-group $rg --query "properties.endpoint" -o tsv 2>&1 | Where-Object { $_ -notmatch 'ERROR' } | Select-Object -First 1

    $key = az cognitiveservices account keys list --name $foundryResource --resource-group $rg --query "key1" -o tsv 2>&1 | Where-Object { $_ -notmatch 'ERROR' } | Select-Object -First 1

    if ([string]::IsNullOrEmpty($endpoint) -or [string]::IsNullOrEmpty($key)) {
        Write-Host "Error: Could not retrieve Foundry credentials."
        return $false
    }
    Write-Host "✓ Foundry credentials retrieved"
    Write-Host ""

    # Create or update the foundry-credentials secret
    Write-Host "Creating Foundry credentials secret in AKS..."
    kubectl delete secret foundry-credentials -n default 2>$null | Out-Null
    $secretOutput = kubectl create secret generic foundry-credentials `
        --from-literal=endpoint="$endpoint" `
        --from-literal=api-key="$key" `
        -n default 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to create Foundry credentials secret."
        Write-Host "Details: $secretOutput"
        return $false
    }
    Write-Host "✓ Foundry credentials secret created"
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

    Write-Host "✓ Deployment manifest updated with ACR endpoint: $acrName.azurecr.io"

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
    $exists = az cognitiveservices account show --name $foundryResource --resource-group $rg 2>&1 | Where-Object { $_ -notmatch 'ERROR' }

    if ([string]::IsNullOrEmpty($exists)) {
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

    Write-Host "✓ Resource deleted"
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

    Write-Host "✓ Resource purged"
    Write-Host "The Foundry resource has been deleted and purged."

    return $true
}

# Function to check deployment status
function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    # Check Foundry model deployment
    Write-Host "Foundry Model Deployment (gpt-4o-mini):"
    $foundryDeploymentStatus = az cognitiveservices account deployment show --name $foundryResource --resource-group $rg --deployment-name "gpt-4o-mini" --query "properties.provisioningState" -o tsv 2>&1 | Where-Object { $_ -notmatch 'ERROR' } | Select-Object -First 1

    if (-not [string]::IsNullOrEmpty($foundryDeploymentStatus)) {
        Write-Host "  Status: $foundryDeploymentStatus"
        if ($foundryDeploymentStatus -eq "Succeeded") {
            Write-Host "  ✓ Model deployed and ready"
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
            Write-Host "  ✓ AKS cluster is ready for deployment"
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
    $choice = Read-Host "Please select an option (1-8)"

    switch ($choice) {
        "1" {
            Write-Host ""
            Provision-FoundryResources | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "2" {
            Write-Host ""
            Delete-FoundryResource | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "3" {
            Write-Host ""
            Create-ResourceGroup | Out-Null
            Write-Host ""
            Create-ACR | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "4" {
            Write-Host ""
            Build-AndPushImage | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "5" {
            Write-Host ""
            Create-AKSCluster | Out-Null
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
            Write-Host ""
            Deploy-ToAKS | Out-Null
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "8" {
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host "Invalid option. Please select 1-8."
            Read-Host "Press Enter to continue"
        }
    }
}
