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
$containerAppName = "ai-api"
$containerImage = "ai-api:v1"

function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    Azure Container Apps Exercise - Deployment Script"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Location: $location"
    Write-Host "Container Apps Environment: $acaEnv"
    Write-Host "ACR Name: $acrName"
    Write-Host "====================================================================="
    Write-Host "1. Create Azure Container Registry and build container image"
    Write-Host "2. Create Container Apps environment"
    Write-Host "3. Deploy the container app and configure secrets"
    Write-Host "4. Check deployment status"
    Write-Host "5. Exit"
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
    Write-Host ""
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

function Create-ContainerAppsEnvironment {
    Write-Host ""
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
        "`$env:TARGET_PORT = `"8000`"",
        "`$env:MODEL_NAME = `"gpt-4o-mini`"",
        "`$env:EMBEDDINGS_API_KEY = `"demo-key-12345`"",
        "`$env:LOCATION = `"$location`""
    ) | Set-Content -Path $envFile -Encoding UTF8

    Write-Host ""
    Write-Host "Environment variables saved to: $envFile"
    Write-Host "Run '. .\.env.ps1' to load them into your shell."
}

function Deploy-ContainerAppAndConfigureSecrets {
    Write-Host "Deploying Container App '$containerAppName' and configuring secrets..."
    Write-Host ""

    # Ensure ACR exists (image is expected to have been built in option 1)
    az acr show --resource-group $rg --name $acrName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: ACR '$acrName' not found. Run option 1 first."
        return
    }

    # Ensure Container Apps environment exists (should have been created in option 2)
    az containerapp env show --name $acaEnv --resource-group $rg 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Container Apps environment '$acaEnv' not found. Run option 2 first."
        return
    }

    # Ensure the container image exists in ACR
    az acr repository show --name $acrName --image $containerImage 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Container image '$containerImage' not found in ACR. Run option 1 first."
        return
    }

    # Create the Container App if it doesn't exist
    az containerapp show --name $containerAppName --resource-group $rg 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Creating Container App '$containerAppName'..."
        # Using --registry-identity system automatically assigns AcrPull role
        az containerapp create `
            --name $containerAppName `
            --resource-group $rg `
            --environment $acaEnv `
            --image "$acrName.azurecr.io/$containerImage" `
            --ingress external `
            --target-port 8000 `
            --env-vars MODEL_NAME=gpt-4o-mini `
            --registry-server "$acrName.azurecr.io" `
            --registry-identity system 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Container App created: $containerAppName"
        }
        else {
            Write-Host "Error: Failed to create Container App"
            return
        }
    }
    else {
        Write-Host "✓ Container App already exists: $containerAppName"
    }

    # Configure secrets
    Write-Host "Setting Container App secret..."
    az containerapp secret set `
        --name $containerAppName `
        --resource-group $rg `
        --secrets embeddings-api-key=demo-key-12345 2>&1 | Out-Null

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Failed to set secrets on Container App"
        return
    }

    # Reference secret from environment variable
    Write-Host "Configuring environment variable to reference secret..."
    az containerapp update `
        --name $containerAppName `
        --resource-group $rg `
        --set-env-vars EMBEDDINGS_API_KEY=secretref:embeddings-api-key 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Container App updated with secret reference"
    }
    else {
        Write-Host "Error: Failed to update Container App configuration"
        return
    }

    # Write environment variables to file (moved here to avoid duplication with deploy exercise)
    Write-EnvFile
}

function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    # Check ACR
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

    # Check Container Apps environment
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

    # Check Container App
    Write-Host ""
    Write-Host "Container App ($containerAppName):"
    $appStatus = az containerapp show --resource-group $rg --name $containerAppName --query "properties.provisioningState" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($appStatus)) {
        Write-Host "  Status: $appStatus"
        if ($appStatus -eq "Succeeded") {
            Write-Host "  ✓ Container App is deployed"
        }
    }
    else {
        Write-Host "  Status: Not created"
    }
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-5)"

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
            Deploy-ContainerAppAndConfigureSecrets
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "4" {
            Write-Host ""
            Check-DeploymentStatus
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "5" {
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host "Invalid option. Please select 1-5."
            Read-Host "Press Enter to continue"
        }
    }
}
