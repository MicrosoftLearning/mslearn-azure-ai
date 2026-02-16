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
$userObjectId = (az ad signed-in-user show --query "id" -o tsv 2>$null)

# Resource names with hash for uniqueness
$kvName = "kv-exercise-$userHash"

function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    Key Vault Secrets Exercise - Deployment Script"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Location: $location"
    Write-Host "Key Vault: $kvName"
    Write-Host "====================================================================="
    Write-Host "1. Create Key Vault"
    Write-Host "2. Assign role"
    Write-Host "3. Store secrets"
    Write-Host "4. Check deployment status"
    Write-Host "5. Retrieve connection info"
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

function Create-KeyVault {
    Write-Host "Creating Key Vault '$kvName'..."

    az keyvault show --resource-group $rg --name $kvName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az keyvault create `
            --name $kvName `
            --resource-group $rg `
            --location $location `
            --enable-rbac-authorization true 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Key Vault created: $kvName"
        }
        else {
            Write-Host "Error: Failed to create Key Vault"
            return
        }
    }
    else {
        Write-Host "✓ Key Vault already exists: $kvName"
    }

    Write-Host ""
    Write-Host "Use option 2 to assign the role."
}

function Assign-Role {
    Write-Host "Assigning Key Vault Secrets Officer role..."

    # Prereq check: vault must exist
    $kvStatus = az keyvault show --resource-group $rg --name $kvName --query "properties.provisioningState" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($kvStatus)) {
        Write-Host "Error: Key Vault '$kvName' not found."
        Write-Host "Please run option 1 to create the vault, then try again."
        return
    }

    if ($kvStatus -ne "Succeeded") {
        Write-Host "Error: Key Vault is not ready (current state: $kvStatus)."
        Write-Host "Please wait for deployment to complete. Use option 4 to check status."
        return
    }

    # Get the signed-in user's UPN
    $userUpn = az ad signed-in-user show --query userPrincipalName -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($userObjectId) -or [string]::IsNullOrWhiteSpace($userUpn)) {
        Write-Host "Error: Unable to retrieve signed-in user information."
        Write-Host "Please ensure you are logged in with 'az login'."
        return
    }

    $kvId = az keyvault show --resource-group $rg --name $kvName --query "id" -o tsv

    # Check if role is already assigned
    $roleExists = az role assignment list `
        --assignee $userObjectId `
        --scope $kvId `
        --role "Key Vault Secrets Officer" `
        --query "[0].id" -o tsv 2>$null

    if (-not [string]::IsNullOrWhiteSpace($roleExists)) {
        Write-Host "✓ Key Vault Secrets Officer role already assigned"
    }
    else {
        az role assignment create `
            --role "Key Vault Secrets Officer" `
            --assignee "$userObjectId" `
            --scope "$kvId" 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Key Vault Secrets Officer role assigned"
        }
        else {
            Write-Host "Error: Failed to assign Key Vault Secrets Officer role"
            return
        }
    }

    Write-Host ""
    Write-Host "Role configured for: $userUpn"
    Write-Host "  - Key Vault Secrets Officer: read, create, update, and delete secrets"
}

function Store-Secrets {
    Write-Host "Storing sample secrets..."

    # Prereq check: vault must exist and be ready
    $kvStatus = az keyvault show --resource-group $rg --name $kvName --query "properties.provisioningState" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($kvStatus)) {
        Write-Host "Error: Key Vault '$kvName' not found."
        Write-Host "Please run option 1 to create the vault, then try again."
        return
    }

    if ($kvStatus -ne "Succeeded") {
        Write-Host "Error: Key Vault is not ready (current state: $kvStatus)."
        Write-Host "Please wait for deployment to complete. Use option 4 to check status."
        return
    }

    # Store openai-api-key secret
    az keyvault secret set `
        --vault-name $kvName `
        --name "openai-api-key" `
        --value "sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx" `
        --content-type "application/x-api-key" `
        --tags environment=development service=openai 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Secret stored: openai-api-key"
    }
    else {
        Write-Host "Error: Failed to store openai-api-key secret"
        return
    }

    # Store cosmosdb-connection-string secret
    az keyvault secret set `
        --vault-name $kvName `
        --name "cosmosdb-connection-string" `
        --value "AccountEndpoint=https://mycosmosdb.documents.azure.com:443/;AccountKey=abc123def456ghi789==" `
        --content-type "application/x-connection-string" `
        --tags environment=development service=cosmosdb 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Secret stored: cosmosdb-connection-string"
    }
    else {
        Write-Host "Error: Failed to store cosmosdb-connection-string secret"
        return
    }

    Write-Host ""
    Write-Host "Use option 4 to check deployment status."
}

function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    Write-Host "Key Vault ($kvName):"
    $kvStatus = az keyvault show --resource-group $rg --name $kvName --query "properties.provisioningState" -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($kvStatus)) {
        Write-Host "  Status: Not created"
    }
    else {
        Write-Host "  Status: $kvStatus"
        if ($kvStatus -eq "Succeeded") {
            Write-Host "  ✓ Key Vault is ready"
            $kvUri = az keyvault show --resource-group $rg --name $kvName --query "properties.vaultUri" -o tsv 2>$null
            Write-Host "  Vault URI: $kvUri"

            # Check secrets
            Write-Host ""
            Write-Host "Secrets:"

            $apiKeyExists = az keyvault secret show --vault-name $kvName --name "openai-api-key" --query "name" -o tsv 2>$null
            if (-not [string]::IsNullOrWhiteSpace($apiKeyExists)) {
                Write-Host "  ✓ Secret stored: openai-api-key"
            }
            else {
                Write-Host "  ⚠ Secret not stored: openai-api-key"
            }

            $connStrExists = az keyvault secret show --vault-name $kvName --name "cosmosdb-connection-string" --query "name" -o tsv 2>$null
            if (-not [string]::IsNullOrWhiteSpace($connStrExists)) {
                Write-Host "  ✓ Secret stored: cosmosdb-connection-string"
            }
            else {
                Write-Host "  ⚠ Secret not stored: cosmosdb-connection-string"
            }

            # Check role assignment
            Write-Host ""
            Write-Host "Role Assignment:"
            $userUpn = az ad signed-in-user show --query userPrincipalName -o tsv 2>$null
            $kvId = az keyvault show --resource-group $rg --name $kvName --query "id" -o tsv

            $roleExists = az role assignment list `
                --assignee $userObjectId `
                --scope $kvId `
                --role "Key Vault Secrets Officer" `
                --query "[0].id" -o tsv 2>$null

            if (-not [string]::IsNullOrWhiteSpace($roleExists)) {
                Write-Host "  ✓ Role assigned: $userUpn (Key Vault Secrets Officer)"
            }
            else {
                Write-Host "  ⚠ Role not assigned"
            }
        }
        else {
            Write-Host "  ⚠ Key Vault is still provisioning. Please wait and try again."
        }
    }
}

function Retrieve-ConnectionInfo {
    Write-Host "Retrieving connection information..."

    # Prereq check: vault must exist
    az keyvault show --resource-group $rg --name $kvName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Key Vault '$kvName' not found."
        Write-Host "Please run option 1 to create the vault, then try again."
        return
    }

    # Prereq check: role must be assigned
    $kvId = az keyvault show --resource-group $rg --name $kvName --query "id" -o tsv
    $roleExists = az role assignment list `
        --assignee $userObjectId `
        --scope $kvId `
        --role "Key Vault Secrets Officer" `
        --query "[0].id" -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($roleExists)) {
        Write-Host "Error: Key Vault Secrets Officer role not assigned."
        Write-Host "Please run option 2 to assign the role, then try again."
        return
    }

    # Get the vault URI
    $kvUri = az keyvault show --resource-group $rg --name $kvName --query "properties.vaultUri" -o tsv 2>$null

    $scriptDir = Split-Path -Parent $PSCommandPath

    # Create .env.ps1 file (for PowerShell shell variables)
    $envPs1File = Join-Path $scriptDir ".env.ps1"

    @(
        "`$env:KEY_VAULT_URL = `"$kvUri`""
    ) | Set-Content -Path $envPs1File -Encoding UTF8

    Write-Host ""
    Write-Host "Key Vault Connection Information"
    Write-Host "==========================================================="
    Write-Host "Vault URL: $kvUri"
    Write-Host "Authentication: Microsoft Entra ID (DefaultAzureCredential)"
    Write-Host ""
    Write-Host "Environment variables saved to: .env.ps1"
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-6)"

    switch ($choice) {
        "1" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-KeyVault
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
            Store-Secrets
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
            Write-Host ""
            Retrieve-ConnectionInfo
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "6" {
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host ""
            Write-Host "Invalid option. Please select 1-6."
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
    }
}
