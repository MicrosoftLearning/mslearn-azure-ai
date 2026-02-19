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
$userObjectId = (az ad signed-in-user show --query "id" -o tsv 2>$null)

# Resource names with hash for uniqueness
$appinsightsName = "appi-exercise-$userHash"

function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    Analyze Logs Exercise - Deployment Script"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Location: $location"
    Write-Host "App Insights: $appinsightsName"
    Write-Host "===================================================================="
    Write-Host "1. Create Application Insights"
    Write-Host "2. Assign role"
    Write-Host "3. Check deployment status"
    Write-Host "4. Retrieve connection info"
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

function Create-ApplicationInsights {
    Write-Host "Creating Application Insights '$appinsightsName'..."

    $appiExists = az monitor app-insights component show --resource-group $rg --app $appinsightsName --query "name" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($appiExists)) {
        az monitor app-insights component create `
            --resource-group $rg `
            --app $appinsightsName `
            --location $location 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Application Insights created: $appinsightsName"
        }
        else {
            Write-Host "Error: Failed to create Application Insights"
            return
        }
    }
    else {
        Write-Host "✓ Application Insights already exists: $appinsightsName"
    }

    Write-Host ""
    Write-Host "Use option 2 to assign the role."
}

function Assign-Role {
    Write-Host "Assigning Monitoring Metrics Publisher role..."

    # Prereq check: Application Insights must exist
    $appiExists = az monitor app-insights component show --resource-group $rg --app $appinsightsName --query "name" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($appiExists)) {
        Write-Host "Error: Application Insights '$appinsightsName' not found."
        Write-Host "Please run option 1 to create the resource, then try again."
        return
    }

    # Get the signed-in user's UPN
    $userUpn = az ad signed-in-user show --query userPrincipalName -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($userObjectId) -or [string]::IsNullOrWhiteSpace($userUpn)) {
        Write-Host "Error: Unable to retrieve signed-in user information."
        Write-Host "Please ensure you are logged in with 'az login'."
        return
    }

    $appiId = az monitor app-insights component show --resource-group $rg --app $appinsightsName --query "id" -o tsv

    # Check if role is already assigned
    $roleExists = az role assignment list `
        --assignee $userObjectId `
        --scope $appiId `
        --role "Monitoring Metrics Publisher" `
        --query "[0].id" -o tsv 2>$null

    if (-not [string]::IsNullOrWhiteSpace($roleExists)) {
        Write-Host "✓ Monitoring Metrics Publisher role already assigned"
    }
    else {
        az role assignment create `
            --role "Monitoring Metrics Publisher" `
            --assignee "$userObjectId" `
            --scope "$appiId" 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Monitoring Metrics Publisher role assigned"
        }
        else {
            Write-Host "Error: Failed to assign Monitoring Metrics Publisher role"
            return
        }
    }

    Write-Host ""
    Write-Host "Role configured for: $userUpn"
    Write-Host "  - Monitoring Metrics Publisher: publish telemetry using Entra authentication"
}

function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    Write-Host "Application Insights ($appinsightsName):"
    $appiStatus = az monitor app-insights component show --resource-group $rg --app $appinsightsName --query "provisioningState" -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($appiStatus)) {
        Write-Host "  Status: Not created"
    }
    else {
        Write-Host "  Status: $appiStatus"
        if ($appiStatus -eq "Succeeded") {
            Write-Host "  ✓ Application Insights is ready"
            $connString = az monitor app-insights component show --resource-group $rg --app $appinsightsName --query "connectionString" -o tsv 2>$null
            Write-Host "  Connection string: $($connString.Substring(0, [Math]::Min(60, $connString.Length)))..."
        }
        else {
            Write-Host "  ⚠ Application Insights is still provisioning. Please wait and try again."
        }
    }

    # Check role assignment
    Write-Host ""
    Write-Host "Role Assignment:"
    $userUpn = az ad signed-in-user show --query userPrincipalName -o tsv 2>$null
    $appiId = az monitor app-insights component show --resource-group $rg --app $appinsightsName --query "id" -o tsv 2>$null

    if (-not [string]::IsNullOrWhiteSpace($appiId)) {
        $roleExists = az role assignment list `
            --assignee $userObjectId `
            --scope $appiId `
            --role "Monitoring Metrics Publisher" `
            --query "[0].id" -o tsv 2>$null

        if (-not [string]::IsNullOrWhiteSpace($roleExists)) {
            Write-Host "  ✓ Role assigned: $userUpn (Monitoring Metrics Publisher)"
        }
        else {
            Write-Host "  ⚠ Role not assigned"
        }
    }
    else {
        Write-Host "  ⚠ Application Insights not created yet"
    }
}

function Retrieve-ConnectionInfo {
    Write-Host "Retrieving connection information..."

    # Prereq check: Application Insights must exist
    $appiExists = az monitor app-insights component show --resource-group $rg --app $appinsightsName --query "name" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($appiExists)) {
        Write-Host "Error: Application Insights '$appinsightsName' not found."
        Write-Host "Please run option 1 to create the resource, then try again."
        return
    }

    # Prereq check: role must be assigned
    $appiId = az monitor app-insights component show --resource-group $rg --app $appinsightsName --query "id" -o tsv
    $roleExists = az role assignment list `
        --assignee $userObjectId `
        --scope $appiId `
        --role "Monitoring Metrics Publisher" `
        --query "[0].id" -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($roleExists)) {
        Write-Host "Error: Monitoring Metrics Publisher role not assigned."
        Write-Host "Please run option 2 to assign the role, then try again."
        return
    }

    # Get the connection string and signed-in user email
    $connString = az monitor app-insights component show --resource-group $rg --app $appinsightsName --query "connectionString" -o tsv 2>$null
    $alertEmail = az account show --query user.name -o tsv 2>$null

    $scriptDir = Split-Path -Parent $PSCommandPath

    # Create .env.ps1 file (for PowerShell shell variables)
    $envPs1File = Join-Path $scriptDir ".env.ps1"

    @(
        "`$env:APPLICATIONINSIGHTS_CONNECTION_STRING = `"$connString`""
        "`$env:OTEL_SERVICE_NAME = `"document-pipeline-app`""
        "`$env:RESOURCE_GROUP = `"$rg`""
        "`$env:APPINSIGHTS_NAME = `"$appinsightsName`""
        "`$env:APPINSIGHTS_RESOURCE_ID = `"$appiId`""
        "`$env:ALERT_EMAIL = `"$alertEmail`""
    ) | Set-Content -Path $envPs1File -Encoding UTF8

    Write-Host ""
    Write-Host "Application Insights Connection Information"
    Write-Host "==========================================================="
    Write-Host "Connection string: $($connString.Substring(0, [Math]::Min(60, $connString.Length)))..."
    Write-Host "Authentication: Microsoft Entra ID (DefaultAzureCredential)"
    Write-Host ""
    Write-Host "Environment variables saved to: .env.ps1"
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-5)"

    switch ($choice) {
        "1" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-ApplicationInsights
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "2" {
            Write-Host ""
            Assign-Role
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
            Write-Host ""
            Retrieve-ConnectionInfo
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "5" {
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host ""
            Write-Host "Invalid option. Please select 1-5."
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
    }
}
