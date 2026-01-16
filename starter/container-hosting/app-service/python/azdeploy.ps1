#!/usr/bin/env pwsh

# Change the values of these variables as needed

$rg = "<your-resource-group-name>"  # Resource Group name
$location = "<your-azure-region>"   # Azure region for the resources

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

function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    App Service Container Exercise - Deployment Script"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Location: $location"
    Write-Host "ACR Name: $acrName"
    Write-Host "App Service Plan: $appPlan"
    Write-Host "====================================================================="
    Write-Host "1. Create Azure Container Registry and build container image"
    Write-Host "2. Create App Service Plan"
    Write-Host "3. Check deployment status"
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
        "`$env:APP_PLAN = `"$appPlan`"",
        "`$env:APP_NAME = `"$appName`"",
        "`$env:LOCATION = `"$location`""
    ) | Set-Content -Path $envFile -Encoding UTF8

    Write-Host ""
    Write-Host "Environment variables saved to: $envFile"
    Write-Host "Run '. .\\.env.ps1' to load them into your shell."
}

function Create-AppServicePlan {
    Write-Host "Creating App Service Plan '$appPlan'..."

    az appservice plan show --resource-group $rg --name $appPlan 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az appservice plan create `
            --resource-group $rg `
            --name $appPlan `
            --sku B1 `
            --is-linux 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ App Service Plan created: $appPlan"
            Write-Host "  SKU: B1 (Basic tier - supports always-on and custom containers)"
        }
        else {
            Write-Host "Error: Failed to create App Service Plan"
            return
        }
    }
    else {
        Write-Host "✓ App Service Plan already exists: $appPlan"
    }

    Write-EnvFile
}

function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
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
    Write-Host "App Service Plan ($appPlan):"
    $planStatus = az appservice plan show --resource-group $rg --name $appPlan --query "provisioningState" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($planStatus)) {
        Write-Host "  Status: $planStatus"
        $planSku = az appservice plan show --resource-group $rg --name $appPlan --query "sku.name" -o tsv 2>$null
        if (-not [string]::IsNullOrWhiteSpace($planSku)) {
            Write-Host "  SKU: $planSku"
        }
        if ($planStatus -eq "Succeeded") {
            Write-Host "  ✓ App Service Plan is ready"
        }
    }
    else {
        Write-Host "  Status: Not created"
    }

    Write-Host ""
    Write-Host "Web App ($appName):"
    $appState = az webapp show --resource-group $rg --name $appName --query "state" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($appState)) {
        Write-Host "  State: $appState"
        Write-Host "  URL: https://$appName.azurewebsites.net"

        $principalId = az webapp identity show --resource-group $rg --name $appName --query "principalId" -o tsv 2>$null
        if (-not [string]::IsNullOrWhiteSpace($principalId)) {
            Write-Host "  ✓ Managed identity configured"
        }
        else {
            Write-Host "  Managed identity: Not configured"
        }
    }
    else {
        Write-Host "  Status: Not created (student task)"
    }

    Write-Host ""
    Write-Host "====================================================================="
    Write-Host "Environment Variables (.env.ps1 file):"
    Write-Host "  RESOURCE_GROUP=$rg"
    Write-Host "  ACR_NAME=$acrName"
    Write-Host "  APP_PLAN=$appPlan"
    Write-Host "  APP_NAME=$appName"
    Write-Host "  LOCATION=$location"
    Write-Host "====================================================================="
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-4)"

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
