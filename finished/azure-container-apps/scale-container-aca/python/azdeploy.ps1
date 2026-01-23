#!/usr/bin/env pwsh

# Change the values of these variables as needed

# $rg = "<your-resource-group-name>"  # Resource Group name
# $location = "<your-azure-region>"   # Azure region for the resources

$rg = "rg-exercises"           # Resource Group name
$location = "eastus2"          # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

function Get-UserHash {
    $userObjectId = (az ad signed-in-user show --query "id" -o tsv 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($userObjectId)) {
        Write-Host "Error: Not authenticated with Azure. Please run: az login"
        exit 1
    }

    $sha1 = [System.Security.Cryptography.SHA1]::Create()
    $hashBytes = $sha1.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($userObjectId))
    return ([System.BitConverter]::ToString($hashBytes).Replace("-", "").Substring(0, 8).ToLower())
}

$userHash = Get-UserHash

# Resource names with hash for uniqueness
$acrName = "acr$userHash"
$acaEnv = "aca-env-$userHash"
$sbNamespace = "sb-$userHash"
$queueName = "orders"
$containerAppName = "queue-processor"
$containerImage = "queue-processor:v1"

function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    Azure Container Apps Scaling Exercise - Deployment Script"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Location: $location"
    Write-Host "Container Apps Environment: $acaEnv"
    Write-Host "ACR Name: $acrName"
    Write-Host "Service Bus Namespace: $sbNamespace"
    Write-Host "====================================================================="
    Write-Host "1. Create Azure Container Registry and build container image"
    Write-Host "2. Create Container Apps environment"
    Write-Host "3. Create Service Bus namespace and queue"
    Write-Host "4. Configure managed identity for queue-processor app"
    Write-Host "5. Check deployment status"
    Write-Host "6. Exit"
    Write-Host "====================================================================="
}

function Create-ResourceGroup {
    Write-Host "Checking/creating resource group '$rg'..."

    $exists = az group exists --name $rg
    if ($exists -eq "false") {
        az group create --name $rg --location $location 2>&1 | Out-Null
        Write-Host "✓ Resource group created: $rg"
    }
    else {
        Write-Host "✓ Resource group already exists: $rg"
    }
}

function Create-AcrAndBuildImage {
    Write-Host "Creating Azure Container Registry '$acrName'..."

    az acr show --resource-group $rg --name $acrName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az acr create `
            --resource-group $rg `
            --name $acrName `
            --sku Basic `
            --admin-enabled false 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ ACR created: $acrName"
            Write-Host "  Login server: $acrName.azurecr.io"
        }
        else {
            Write-Host "Error: Failed to create ACR"
            return
        }
    }
    else {
        Write-Host "✓ ACR already exists: $acrName"
        Write-Host "  Login server: $acrName.azurecr.io"
    }

    Write-Host ""
    Write-Host "Building and pushing container image to ACR..."
    Write-Host "This may take a few minutes..."

    az acr build `
        --resource-group $rg `
        --registry $acrName `
        --image $containerImage `
        --file api/Dockerfile `
        api/ 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Image built and pushed: $acrName.azurecr.io/$containerImage"
    }
    else {
        Write-Host "Error: Failed to build/push image"
    }
}

function Write-EnvFile {
    $scriptDir = Split-Path -Parent $PSCommandPath
    $envFile = Join-Path $scriptDir ".env.ps1"

    @(
        "`$env:RESOURCE_GROUP = `"$rg`"",
        "`$env:ACR_NAME = `"$acrName`"",
        "`$env:ACR_SERVER = `"$acrName.azurecr.io`"",
        "`$env:ACA_ENVIRONMENT = `"$acaEnv`"",
        "`$env:CONTAINER_APP_NAME = `"$containerAppName`"",
        "`$env:CONTAINER_IMAGE = `"$containerImage`"",
        "`$env:SERVICE_BUS_NAMESPACE = `"$sbNamespace`"",
        "`$env:SERVICE_BUS_FQDN = `"$sbNamespace.servicebus.windows.net`"",
        "`$env:QUEUE_NAME = `"$queueName`"",
        "`$env:LOCATION = `"$location`""
    ) | Set-Content -Path $envFile -Encoding UTF8

    Write-Host ""
    Write-Host "Environment variables saved to: $envFile"
    Write-Host "Run '. .\.env.ps1' to load them into your shell."
}

function Create-ContainerAppsEnvironment {
    Write-Host "Creating Container Apps environment '$acaEnv' (if needed)..."
    Write-Host "This may take a few minutes..."

    az containerapp env show --name $acaEnv --resource-group $rg 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az containerapp env create `
            --name $acaEnv `
            --resource-group $rg `
            --location $location 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Container Apps environment created: $acaEnv"
        }
        else {
            Write-Host "Error: Failed to create Container Apps environment"
            return
        }
    }
    else {
        Write-Host "✓ Container Apps environment already exists: $acaEnv"
    }

    Write-EnvFile
}

function Create-ServiceBus {
    Write-Host "Creating Service Bus namespace '$sbNamespace'..."

    az servicebus namespace show --resource-group $rg --name $sbNamespace 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az servicebus namespace create `
            --resource-group $rg `
            --name $sbNamespace `
            --location $location `
            --sku Standard 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Service Bus namespace created: $sbNamespace"
        }
        else {
            Write-Host "Error: Failed to create Service Bus namespace"
            return
        }
    }
    else {
        Write-Host "✓ Service Bus namespace already exists: $sbNamespace"
    }

    Write-Host ""
    Write-Host "Creating queue '$queueName'..."

    az servicebus queue show --resource-group $rg --namespace-name $sbNamespace --name $queueName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az servicebus queue create `
            --resource-group $rg `
            --namespace-name $sbNamespace `
            --name $queueName 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Queue created: $queueName"
        }
        else {
            Write-Host "Error: Failed to create queue"
            return
        }
    }
    else {
        Write-Host "✓ Queue already exists: $queueName"
    }

    Write-EnvFile
}

function Configure-ManagedIdentity {
    Write-Host "Configuring managed identity for '$containerAppName'..."
    Write-Host ""

    # Check if container app exists
    az containerapp show --resource-group $rg --name $containerAppName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Container app '$containerAppName' not found."
        Write-Host "Please deploy the container app first using the exercise steps."
        return
    }

    # Get the principal ID of the container app's system-assigned identity
    Write-Host "Getting container app identity..."
    $principalId = az containerapp identity show `
        --resource-group $rg `
        --name $containerAppName `
        --query principalId `
        --output tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($principalId)) {
        Write-Host "Error: Container app does not have a system-assigned identity."
        Write-Host "Please create the container app with --system-assigned flag."
        return
    }
    Write-Host "✓ Principal ID: $principalId"

    # Get Service Bus namespace resource ID
    Write-Host ""
    Write-Host "Getting Service Bus resource ID..."
    $sbResourceId = az servicebus namespace show `
        --resource-group $rg `
        --name $sbNamespace `
        --query id `
        --output tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($sbResourceId)) {
        Write-Host "Error: Service Bus namespace '$sbNamespace' not found."
        Write-Host "Please run option 3 first to create the Service Bus namespace."
        return
    }
    Write-Host "✓ Service Bus resource ID obtained"

    # Assign Azure Service Bus Data Receiver role (for receiving messages)
    Write-Host ""
    Write-Host "Assigning 'Azure Service Bus Data Receiver' role..."
    az role assignment create `
        --assignee $principalId `
        --role "Azure Service Bus Data Receiver" `
        --scope $sbResourceId 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Service Bus Data Receiver role assigned"
    }
    else {
        Write-Host "  Role may already be assigned or assignment failed"
    }

    # Assign Azure Service Bus Data Owner role (for KEDA scaler to query metrics)
    Write-Host ""
    Write-Host "Assigning 'Azure Service Bus Data Owner' role (required for KEDA scaling)..."
    az role assignment create `
        --assignee $principalId `
        --role "Azure Service Bus Data Owner" `
        --scope $sbResourceId 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Service Bus Data Owner role assigned"
    }
    else {
        Write-Host "  Role may already be assigned or assignment failed"
    }

    Write-Host ""
    Write-Host "====================================================================="
    Write-Host "Managed identity configuration complete!"
    Write-Host ""
    Write-Host "NOTE: Azure role assignments can take 1-2 minutes to propagate."
    Write-Host "If the app fails to connect to Service Bus, wait a moment and retry."
    Write-Host "====================================================================="
}

function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    Write-Host "Container Apps Environment ($acaEnv):"
    $envStatus = (az containerapp env show --resource-group $rg --name $acaEnv --query "properties.provisioningState" -o tsv 2>$null) | Select-Object -Last 1
    if (-not [string]::IsNullOrWhiteSpace($envStatus)) {
        Write-Host "  Status: $envStatus"
        if ($envStatus -eq "Succeeded") {
            Write-Host "  ✓ Container Apps environment is ready"
        }
    }
    else {
        Write-Host "  Status: Not created"
    }

    Write-Host ""
    Write-Host "Azure Container Registry ($acrName):"
    $acrStatus = az acr show --resource-group $rg --name $acrName --query "provisioningState" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($acrStatus)) {
        Write-Host "  Status: $acrStatus"
        if ($acrStatus -eq "Succeeded") {
            Write-Host "  ✓ ACR is ready"
            az acr repository show --name $acrName --image $containerImage 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  ✓ Container image: $containerImage"
            }
            else {
                Write-Host "  Container image not found"
            }
        }
    }
    else {
        Write-Host "  Status: Not created"
    }

    Write-Host ""
    Write-Host "Service Bus Namespace ($sbNamespace):"
    $sbStatus = az servicebus namespace show --resource-group $rg --name $sbNamespace --query "provisioningState" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($sbStatus)) {
        Write-Host "  Status: $sbStatus"
        if ($sbStatus -eq "Succeeded") {
            Write-Host "  ✓ Service Bus namespace is ready"
            $queueStatus = az servicebus queue show --resource-group $rg --namespace-name $sbNamespace --name $queueName --query "status" -o tsv 2>$null
            if (-not [string]::IsNullOrWhiteSpace($queueStatus)) {
                Write-Host "  ✓ Queue '$queueName': $queueStatus"
            }
            else {
                Write-Host "  Queue '$queueName' not found"
            }
        }
    }
    else {
        Write-Host "  Status: Not created"
    }

    Write-Host ""
    Write-Host "Container App ($containerAppName):"
    $appStatus = az containerapp show --resource-group $rg --name $containerAppName --query "properties.provisioningState" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($appStatus)) {
        Write-Host "  Status: $appStatus"
        $hasIdentity = az containerapp identity show --resource-group $rg --name $containerAppName --query "principalId" -o tsv 2>$null
        if (-not [string]::IsNullOrWhiteSpace($hasIdentity)) {
            Write-Host "  ✓ System-assigned identity configured"
        }
        else {
            Write-Host "  ⚠ No system-assigned identity"
        }
        $replicaCount = az containerapp replica list --resource-group $rg --name $containerAppName --query "length([])" -o tsv 2>$null
        if ([string]::IsNullOrWhiteSpace($replicaCount)) { $replicaCount = "0" }
        Write-Host "  Running replicas: $replicaCount"
    }
    else {
        Write-Host "  Status: Not deployed"
    }
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-6)"

    switch ($choice) {
        "1" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-AcrAndBuildImage
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "2" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-ContainerAppsEnvironment
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "3" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-ServiceBus
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "4" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-ServiceBus
            Write-Host ""
            Configure-ManagedIdentity
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "5" {
            Write-Host ""
            Check-DeploymentStatus
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
