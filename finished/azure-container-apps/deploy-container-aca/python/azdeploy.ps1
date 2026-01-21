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
$appPlan = "plan-docprocessor-$userHash"
$appName = "app-docprocessor-$userHash"
$containerImage = "docprocessor:v1"
$acaEnv = "aca-env-exercise-$userHash"
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
    Write-Host "1. Create resource group + Container Apps environment"
    Write-Host "2. Create Azure Container Registry and build container image"
    Write-Host "3. Check setup status"
    Write-Host "4. Exit"
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

function Install-ContainerAppsTools {
    Write-Host "Ensuring Azure CLI and Container Apps extension are available..."
    az upgrade 2>$null | Out-Null
    az extension add --name containerapp --upgrade 2>$null | Out-Null

    Write-Host "Registering required resource providers (idempotent)..."
    az provider register --namespace Microsoft.App 2>$null | Out-Null
    az provider register --namespace Microsoft.OperationalInsights 2>$null | Out-Null
}

function Create-ContainerAppsEnvironment {
    Write-Host "Creating Container Apps environment '$acaEnv' (if needed)..."

    az containerapp env show --name $acaEnv --resource-group $rg 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az containerapp env create `
            --name $acaEnv `
            --resource-group $rg `
            --location $location 2>$null | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Container Apps environment created: $acaEnv"
        }
        else {
            Write-Host "Error: Failed to create Container Apps environment"
        }
    }
    else {
        Write-Host "✓ Container Apps environment already exists: $acaEnv"
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

    $acrServer = az acr show -n $acrName --query loginServer -o tsv 2>$null

    @(
        "`$env:RESOURCE_GROUP = `"$rg`"",
        "`$env:ACR_NAME = `"$acrName`"",
        "`$env:ACR_SERVER = `"$acrServer`"",
        "`$env:ACA_ENVIRONMENT = `"$acaEnv`"",
        "`$env:CONTAINER_IMAGE = `"$containerImage`"",
        "`$env:LOCATION = `"$location`""
    ) | Set-Content -Path $envFile -Encoding UTF8

    Write-Host ""
    Write-Host "Environment variables saved to: $envFile"
    Write-Host "Run '. .\\.env.ps1' to load them into your shell."

    Write-Host ""
    Write-Host "Next (student steps in the exercise):"
    Write-Host "  - Deploy the Container App using: az containerapp create ..."
    Write-Host "  - Configure secrets using: az containerapp secret set / az containerapp update"
}

function Check-DeploymentStatus {
    Write-Host "Checking setup status..."
    Write-Host ""

    Write-Host "Container Apps Environment ($acaEnv):"
    $envStatus = az containerapp env show --resource-group $rg --name $acaEnv --query "provisioningState" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($envStatus)) {
        Write-Host "  Status: $envStatus"
        if ($envStatus -eq "Succeeded") {
            Write-Host "  ✓ Environment is ready"
        }
    }
    else {
        Write-Host "  Status: Not created"
    }

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
    Write-Host "Tip: run '. .\\.env.ps1' after option 2 to load variables."
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-4)"

            Install-ContainerAppsTools
            Create-ContainerAppsEnvironment
    switch ($choice) {
        "1" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-AcrAndBuildImage
            Install-ContainerAppsTools
            Create-ContainerAppsEnvironment
            Write-Host ""
            Read-Host "Press Enter to continue"
            Write-EnvFile
        }
        "2" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-AppServicePlan
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "3" {
            Write-Host ""
            Check-DeploymentStatus
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "4" {
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host "Invalid option. Please select 1-4."
            Read-Host "Press Enter to continue"
        }
    }
}
