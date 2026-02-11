#!/usr/bin/env pwsh

# Change the values of these variables as needed

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
$namespaceName = "sbns-exercise-$userHash"

function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    Service Bus Messaging Exercise - Deployment Script"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Location: $location"
    Write-Host "Namespace: $namespaceName"
    Write-Host "====================================================================="
    Write-Host "1. Create Service Bus namespace"
    Write-Host "2. Check deployment status"
    Write-Host "3. Assign role and create .env file"
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

function Create-ServiceBusNamespace {
    Write-Host "Creating Service Bus namespace '$namespaceName'..."

    az servicebus namespace show --resource-group $rg --name $namespaceName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az servicebus namespace create `
            --name $namespaceName `
            --resource-group $rg `
            --location $location `
            --sku Standard 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Service Bus namespace created: $namespaceName"
        }
        else {
            Write-Host "Error: Failed to create Service Bus namespace"
            return
        }
    }
    else {
        Write-Host "✓ Service Bus namespace already exists: $namespaceName"
    }
}

function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    Write-Host "Service Bus Namespace ($namespaceName):"
    $nsStatus = az servicebus namespace show --resource-group $rg --name $namespaceName --query "provisioningState" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($nsStatus)) {
        Write-Host "  Provisioning State: $nsStatus"
        if ($nsStatus -eq "Succeeded") {
            Write-Host "  ✓ Namespace is ready"
            $nsSku = az servicebus namespace show --resource-group $rg --name $namespaceName --query "sku.name" -o tsv 2>$null
            Write-Host "  SKU: $nsSku"
            $nsEndpoint = az servicebus namespace show --resource-group $rg --name $namespaceName --query "serviceBusEndpoint" -o tsv 2>$null
            Write-Host "  Endpoint: $nsEndpoint"
        }
        else {
            Write-Host "  ⚠ Namespace is still provisioning. Please wait and try again."
        }
    }
    else {
        Write-Host "  Status: Not created"
    }
}

function Assign-RoleAndCreateEnv {
    Write-Host "Assigning Azure Service Bus Data Owner role..."

    # Get the namespace resource ID
    $nsId = az servicebus namespace show --resource-group $rg --name $namespaceName --query "id" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($nsId)) {
        Write-Host ""
        Write-Host "Error: Unable to find the Service Bus namespace."
        Write-Host "Please check the deployment status to ensure the resource is fully provisioned."
        return
    }

    # Assign the Azure Service Bus Data Owner role
    az role assignment create `
        --role "Azure Service Bus Data Owner" `
        --assignee "$userObjectId" `
        --scope "$nsId" 2>&1 | Out-Null

    Write-Host "✓ Role assigned: Azure Service Bus Data Owner"

    # Get the FQDN
    $fqdn = "$namespaceName.servicebus.windows.net"

    # Create .env file (for Python dotenv)
    $scriptDir = Split-Path -Parent $PSCommandPath
    $envFile = Join-Path $scriptDir ".env"

    @(
        "SERVICE_BUS_FQDN=$fqdn"
    ) | Set-Content -Path $envFile -Encoding UTF8

    # Create .env.ps1 file (for PowerShell shell variables)
    $envPs1File = Join-Path $scriptDir ".env.ps1"

    @(
        "`$env:RESOURCE_GROUP = `"$rg`"",
        "`$env:NAMESPACE_NAME = `"$namespaceName`"",
        "`$env:SERVICE_BUS_FQDN = `"$fqdn`""
    ) | Set-Content -Path $envPs1File -Encoding UTF8

    Clear-Host
    Write-Host ""
    Write-Host "Service Bus Connection Information"
    Write-Host "==========================================================="
    Write-Host "FQDN: $fqdn"
    Write-Host ""
    Write-Host "Environment variables saved to: $envFile and $envPs1File"
    Write-Host "Run '. .\.env.ps1' to load them into your shell."
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-4)"

    switch ($choice) {
        "1" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-ServiceBusNamespace
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "2" {
            Write-Host ""
            Check-DeploymentStatus
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "3" {
            Write-Host ""
            Assign-RoleAndCreateEnv
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "4" {
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host ""
            Write-Host "Invalid option. Please select 1-4."
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
    }
}
