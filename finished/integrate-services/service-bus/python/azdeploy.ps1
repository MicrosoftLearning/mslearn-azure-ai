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

    Write-Host ""
    Write-Host "Use option 2 to assign the data plane role."
}

function Assign-Role {
    Write-Host "Assigning Azure Service Bus Data Owner role..."

    # Prereq check: namespace must exist
    $nsStatus = az servicebus namespace show --resource-group $rg --name $namespaceName --query "provisioningState" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($nsStatus)) {
        Write-Host "Error: Service Bus namespace '$namespaceName' not found."
        Write-Host "Please run option 1 to create the namespace, then try again."
        return
    }

    if ($nsStatus -ne "Succeeded") {
        Write-Host "Error: Service Bus namespace is not ready (current state: $nsStatus)."
        Write-Host "Please wait for deployment to complete. Use option 3 to check status."
        return
    }

    # Get the signed-in user's UPN
    $userUpn = az ad signed-in-user show --query userPrincipalName -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($userObjectId) -or [string]::IsNullOrWhiteSpace($userUpn)) {
        Write-Host "Error: Unable to retrieve signed-in user information."
        Write-Host "Please ensure you are logged in with 'az login'."
        return
    }

    $nsId = az servicebus namespace show --resource-group $rg --name $namespaceName --query "id" -o tsv

    # Check if role is already assigned
    $roleExists = az role assignment list `
        --assignee $userObjectId `
        --scope $nsId `
        --role "Azure Service Bus Data Owner" `
        --query "[0].id" -o tsv 2>$null

    if (-not [string]::IsNullOrWhiteSpace($roleExists)) {
        Write-Host "✓ Azure Service Bus Data Owner role already assigned"
    }
    else {
        az role assignment create `
            --role "Azure Service Bus Data Owner" `
            --assignee "$userObjectId" `
            --scope "$nsId" 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Azure Service Bus Data Owner role assigned"
        }
        else {
            Write-Host "Error: Failed to assign Azure Service Bus Data Owner role"
            return
        }
    }

    Write-Host ""
    Write-Host "Role configured for: $userUpn"
    Write-Host "  - Azure Service Bus Data Owner: send, receive, and manage entities"
}

function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    Write-Host "Service Bus Namespace ($namespaceName):"
    $nsStatus = az servicebus namespace show --resource-group $rg --name $namespaceName --query "provisioningState" -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($nsStatus)) {
        Write-Host "  Status: Not created"
    }
    else {
        Write-Host "  Status: $nsStatus"
        if ($nsStatus -eq "Succeeded") {
            Write-Host "  ✓ Namespace is ready"
            $nsSku = az servicebus namespace show --resource-group $rg --name $namespaceName --query "sku.name" -o tsv 2>$null
            Write-Host "  SKU: $nsSku"
            $nsEndpoint = az servicebus namespace show --resource-group $rg --name $namespaceName --query "serviceBusEndpoint" -o tsv 2>$null
            Write-Host "  Endpoint: $nsEndpoint"

            # Check role assignment
            $userUpn = az ad signed-in-user show --query userPrincipalName -o tsv 2>$null
            $nsId = az servicebus namespace show --resource-group $rg --name $namespaceName --query "id" -o tsv

            $roleExists = az role assignment list `
                --assignee $userObjectId `
                --scope $nsId `
                --role "Azure Service Bus Data Owner" `
                --query "[0].id" -o tsv 2>$null

            if (-not [string]::IsNullOrWhiteSpace($roleExists)) {
                Write-Host "  ✓ Role assigned: $userUpn (Azure Service Bus Data Owner)"
            }
            else {
                Write-Host "  ⚠ Role not assigned"
            }
        }
        else {
            Write-Host "  ⚠ Namespace is still provisioning. Please wait and try again."
        }
    }
}

function Retrieve-ConnectionInfo {
    Write-Host "Retrieving connection information..."

    # Prereq check: namespace must exist
    az servicebus namespace show --resource-group $rg --name $namespaceName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Service Bus namespace '$namespaceName' not found."
        Write-Host "Please run option 1 to create the namespace, then try again."
        return
    }

    # Prereq check: role must be assigned
    $nsId = az servicebus namespace show --resource-group $rg --name $namespaceName --query "id" -o tsv
    $roleExists = az role assignment list `
        --assignee $userObjectId `
        --scope $nsId `
        --role "Azure Service Bus Data Owner" `
        --query "[0].id" -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($roleExists)) {
        Write-Host "Error: Azure Service Bus Data Owner role not assigned."
        Write-Host "Please run option 2 to assign the role, then try again."
        return
    }

    # Get the FQDN
    $fqdn = "$namespaceName.servicebus.windows.net"

    $scriptDir = Split-Path -Parent $PSCommandPath

    # Create .env.ps1 file (for PowerShell shell variables)
    $envPs1File = Join-Path $scriptDir ".env.ps1"

    @(
        "`$env:RESOURCE_GROUP = `"$rg`"",
        "`$env:NAMESPACE_NAME = `"$namespaceName`"",
        "`$env:SERVICE_BUS_FQDN = `"$fqdn`""
    ) | Set-Content -Path $envPs1File -Encoding UTF8

    Write-Host ""
    Write-Host "Service Bus Connection Information"
    Write-Host "==========================================================="
    Write-Host "FQDN: $fqdn"
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
            Create-ServiceBusNamespace
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
