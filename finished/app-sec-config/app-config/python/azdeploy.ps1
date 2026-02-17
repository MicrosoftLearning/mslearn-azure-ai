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
$appconfigName = "appconfig-exercise-$userHash"
$kvName = "kv-exercise-$userHash"

function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    App Configuration Exercise - Deployment Script"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Location: $location"
    Write-Host "App Configuration: $appconfigName"
    Write-Host "Key Vault: $kvName"
    Write-Host "====================================================================="
    Write-Host "1. Create App Configuration"
    Write-Host "2. Create Key Vault"
    Write-Host "3. Assign roles"
    Write-Host "4. Store sample settings"
    Write-Host "5. Check deployment status"
    Write-Host "6. Retrieve connection info"
    Write-Host "7. Exit"
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

function Create-AppConfiguration {
    Write-Host "Creating App Configuration store '$appconfigName'..."

    az appconfig show --resource-group $rg --name $appconfigName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az appconfig create `
            --name $appconfigName `
            --resource-group $rg `
            --location $location `
            --sku Standard 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ App Configuration store created: $appconfigName"
        }
        else {
            Write-Host "Error: Failed to create App Configuration store"
            return
        }
    }
    else {
        Write-Host "✓ App Configuration store already exists: $appconfigName"
    }

    Write-Host ""
    Write-Host "Use option 2 to create Key Vault."
}

function Create-KeyVault {
    Write-Host "Creating Key Vault '$kvName'..."

    az keyvault show --resource-group $rg --name $kvName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        # Check for a soft-deleted vault with the same name and recover it
        $softDeleted = az keyvault show-deleted --name $kvName --query "name" -o tsv 2>$null
        if (-not [string]::IsNullOrWhiteSpace($softDeleted)) {
            Write-Host "  Recovering soft-deleted Key Vault '$kvName'..."
            az keyvault recover --name $kvName 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ Key Vault recovered: $kvName"
            }
            else {
                Write-Host "Error: Failed to recover soft-deleted Key Vault."
                Write-Host "You may need to purge it first: az keyvault purge --name $kvName"
                return
            }
        }
        else {
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
    }
    else {
        Write-Host "✓ Key Vault already exists: $kvName"
    }

    Write-Host ""
    Write-Host "Use option 3 to assign roles."
}

function Assign-Roles {
    Write-Host "Assigning roles..."

    # Get the signed-in user's UPN
    $userUpn = az ad signed-in-user show --query userPrincipalName -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($userObjectId) -or [string]::IsNullOrWhiteSpace($userUpn)) {
        Write-Host "Error: Unable to retrieve signed-in user information."
        Write-Host "Please ensure you are logged in with 'az login'."
        return
    }

    # Assign App Configuration Data Owner role
    $acStatus = az appconfig show --resource-group $rg --name $appconfigName --query "provisioningState" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($acStatus)) {
        Write-Host "Error: App Configuration store '$appconfigName' not found."
        Write-Host "Please run option 1 to create the store, then try again."
        return
    }

    $acId = az appconfig show --resource-group $rg --name $appconfigName --query "id" -o tsv

    $acRoleExists = az role assignment list `
        --assignee $userObjectId `
        --scope $acId `
        --role "App Configuration Data Owner" `
        --query "[0].id" -o tsv 2>$null

    if (-not [string]::IsNullOrWhiteSpace($acRoleExists)) {
        Write-Host "✓ App Configuration Data Owner role already assigned"
    }
    else {
        az role assignment create `
            --role "App Configuration Data Owner" `
            --assignee "$userObjectId" `
            --scope "$acId" 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ App Configuration Data Owner role assigned"
        }
        else {
            Write-Host "Error: Failed to assign App Configuration Data Owner role"
            return
        }
    }

    # Assign Key Vault Secrets Officer role
    $kvStatus = az keyvault show --resource-group $rg --name $kvName --query "properties.provisioningState" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($kvStatus)) {
        Write-Host "Error: Key Vault '$kvName' not found."
        Write-Host "Please run option 2 to create the vault, then try again."
        return
    }

    $kvId = az keyvault show --resource-group $rg --name $kvName --query "id" -o tsv

    $kvRoleExists = az role assignment list `
        --assignee $userObjectId `
        --scope $kvId `
        --role "Key Vault Secrets Officer" `
        --query "[0].id" -o tsv 2>$null

    if (-not [string]::IsNullOrWhiteSpace($kvRoleExists)) {
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
    Write-Host "Roles configured for: $userUpn"
    Write-Host "  - App Configuration Data Owner: read, create, and update settings"
    Write-Host "  - Key Vault Secrets Officer: read, create, update, and delete secrets"
}

function Store-Settings {
    Write-Host "Storing configuration settings..."

    # Prereq check: App Configuration store must exist
    $acStatus = az appconfig show --resource-group $rg --name $appconfigName --query "provisioningState" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($acStatus)) {
        Write-Host "Error: App Configuration store '$appconfigName' not found."
        Write-Host "Please run option 1 to create the store, then try again."
        return
    }

    if ($acStatus -ne "Succeeded") {
        Write-Host "Error: App Configuration store is not ready (current state: $acStatus)."
        Write-Host "Please wait for deployment to complete. Use option 5 to check status."
        return
    }

    # Prereq check: Key Vault must exist and be ready
    $kvStatus = az keyvault show --resource-group $rg --name $kvName --query "properties.provisioningState" -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($kvStatus)) {
        Write-Host "Error: Key Vault '$kvName' not found."
        Write-Host "Please run option 2 to create the vault, then try again."
        return
    }

    if ($kvStatus -ne "Succeeded") {
        Write-Host "Error: Key Vault is not ready (current state: $kvStatus)."
        Write-Host "Please wait for deployment to complete. Use option 5 to check status."
        return
    }

    # Store default (unlabeled) configuration settings
    az appconfig kv set --name $appconfigName --key "OpenAI:Endpoint" `
        --value "https://my-openai.openai.azure.com/" --yes 2>&1 | Out-Null
    Write-Host "✓ Setting stored: OpenAI:Endpoint (no label)"

    az appconfig kv set --name $appconfigName --key "OpenAI:DeploymentName" `
        --value "gpt-4o" --yes 2>&1 | Out-Null
    Write-Host "✓ Setting stored: OpenAI:DeploymentName (no label)"

    az appconfig kv set --name $appconfigName --key "Pipeline:BatchSize" `
        --value "10" --yes 2>&1 | Out-Null
    Write-Host "✓ Setting stored: Pipeline:BatchSize = 10 (no label)"

    az appconfig kv set --name $appconfigName --key "Pipeline:RetryCount" `
        --value "3" --yes 2>&1 | Out-Null
    Write-Host "✓ Setting stored: Pipeline:RetryCount = 3 (no label)"

    # Store Production-labeled overrides
    az appconfig kv set --name $appconfigName --key "Pipeline:BatchSize" `
        --value "200" --label "Production" --yes 2>&1 | Out-Null
    Write-Host "✓ Setting stored: Pipeline:BatchSize = 200 (Production)"

    az appconfig kv set --name $appconfigName --key "Pipeline:RetryCount" `
        --value "5" --label "Production" --yes 2>&1 | Out-Null
    Write-Host "✓ Setting stored: Pipeline:RetryCount = 5 (Production)"

    # Store sentinel key for dynamic refresh
    az appconfig kv set --name $appconfigName --key "Sentinel" `
        --value "1" --yes 2>&1 | Out-Null
    Write-Host "✓ Setting stored: Sentinel = 1"

    # Store secret in Key Vault
    az keyvault secret set `
        --vault-name $kvName `
        --name "openai-api-key" `
        --value "sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx" `
        --content-type "application/x-api-key" 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Secret stored in Key Vault: openai-api-key"
    }
    else {
        Write-Host "Error: Failed to store openai-api-key secret in Key Vault"
        return
    }

    # Create Key Vault reference in App Configuration
    $secretUri = az keyvault secret show --vault-name $kvName --name "openai-api-key" --query "id" -o tsv 2>$null

    az appconfig kv set-keyvault `
        --name $appconfigName `
        --key "OpenAI:ApiKey" `
        --secret-identifier "$secretUri" `
        --yes 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Key Vault reference created: OpenAI:ApiKey → openai-api-key"
    }
    else {
        Write-Host "Error: Failed to create Key Vault reference"
        return
    }

    Write-Host ""
    Write-Host "Use option 5 to check deployment status."
}

function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    # Check App Configuration store
    Write-Host "App Configuration ($appconfigName):"
    $acStatus = az appconfig show --resource-group $rg --name $appconfigName --query "provisioningState" -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($acStatus)) {
        Write-Host "  Status: Not created"
    }
    else {
        Write-Host "  Status: $acStatus"
        if ($acStatus -eq "Succeeded") {
            Write-Host "  ✓ App Configuration store is ready"
            $acEndpoint = az appconfig show --resource-group $rg --name $appconfigName --query "endpoint" -o tsv 2>$null
            Write-Host "  Endpoint: $acEndpoint"

            # Check settings
            Write-Host ""
            Write-Host "  Settings:"

            $settingCount = az appconfig kv list --name $appconfigName --query "length(@)" -o tsv 2>$null
            if (-not [string]::IsNullOrWhiteSpace($settingCount) -and [int]$settingCount -gt 0) {
                Write-Host "  ✓ $settingCount setting(s) stored"
            }
            else {
                Write-Host "  ⚠ No settings stored"
            }

            # Check Key Vault reference
            $kvRef = az appconfig kv list --name $appconfigName --key "OpenAI:ApiKey" --query "[0].contentType" -o tsv 2>$null
            if (-not [string]::IsNullOrWhiteSpace($kvRef)) {
                Write-Host "  ✓ Key Vault reference: OpenAI:ApiKey"
            }
            else {
                Write-Host "  ⚠ Key Vault reference not found: OpenAI:ApiKey"
            }
        }
        else {
            Write-Host "  ⚠ App Configuration store is still provisioning. Please wait and try again."
        }
    }

    Write-Host ""

    # Check Key Vault
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

            # Check secret
            Write-Host ""
            Write-Host "  Secrets:"
            $apiKeyExists = az keyvault secret show --vault-name $kvName --name "openai-api-key" --query "name" -o tsv 2>$null
            if (-not [string]::IsNullOrWhiteSpace($apiKeyExists)) {
                Write-Host "  ✓ Secret stored: openai-api-key"
            }
            else {
                Write-Host "  ⚠ Secret not stored: openai-api-key"
            }
        }
        else {
            Write-Host "  ⚠ Key Vault is still provisioning. Please wait and try again."
        }
    }

    # Check role assignments
    Write-Host ""
    Write-Host "Role Assignments:"
    $userUpn = az ad signed-in-user show --query userPrincipalName -o tsv 2>$null

    $acId = az appconfig show --resource-group $rg --name $appconfigName --query "id" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($acId)) {
        $acRoleExists = az role assignment list `
            --assignee $userObjectId `
            --scope $acId `
            --role "App Configuration Data Owner" `
            --query "[0].id" -o tsv 2>$null

        if (-not [string]::IsNullOrWhiteSpace($acRoleExists)) {
            Write-Host "  ✓ Role assigned: $userUpn (App Configuration Data Owner)"
        }
        else {
            Write-Host "  ⚠ App Configuration Data Owner role not assigned"
        }
    }

    $kvId = az keyvault show --resource-group $rg --name $kvName --query "id" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($kvId)) {
        $kvRoleExists = az role assignment list `
            --assignee $userObjectId `
            --scope $kvId `
            --role "Key Vault Secrets Officer" `
            --query "[0].id" -o tsv 2>$null

        if (-not [string]::IsNullOrWhiteSpace($kvRoleExists)) {
            Write-Host "  ✓ Role assigned: $userUpn (Key Vault Secrets Officer)"
        }
        else {
            Write-Host "  ⚠ Key Vault Secrets Officer role not assigned"
        }
    }
}

function Retrieve-ConnectionInfo {
    Write-Host "Retrieving connection information..."

    # Prereq check: App Configuration store must exist
    az appconfig show --resource-group $rg --name $appconfigName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: App Configuration store '$appconfigName' not found."
        Write-Host "Please run option 1 to create the store, then try again."
        return
    }

    # Prereq check: roles must be assigned
    $acId = az appconfig show --resource-group $rg --name $appconfigName --query "id" -o tsv
    $acRoleExists = az role assignment list `
        --assignee $userObjectId `
        --scope $acId `
        --role "App Configuration Data Owner" `
        --query "[0].id" -o tsv 2>$null

    if ([string]::IsNullOrWhiteSpace($acRoleExists)) {
        Write-Host "Error: App Configuration Data Owner role not assigned."
        Write-Host "Please run option 3 to assign roles, then try again."
        return
    }

    # Get the App Configuration endpoint
    $acEndpoint = az appconfig show --resource-group $rg --name $appconfigName --query "endpoint" -o tsv 2>$null

    $scriptDir = Split-Path -Parent $PSCommandPath

    # Create .env.ps1 file (for PowerShell shell variables)
    $envPs1File = Join-Path $scriptDir ".env.ps1"

    @(
        "`$env:AZURE_APPCONFIG_ENDPOINT = `"$acEndpoint`""
    ) | Set-Content -Path $envPs1File -Encoding UTF8

    Write-Host ""
    Write-Host "App Configuration Connection Information"
    Write-Host "==========================================================="
    Write-Host "Endpoint: $acEndpoint"
    Write-Host "Authentication: Microsoft Entra ID (DefaultAzureCredential)"
    Write-Host ""
    Write-Host "Environment variables saved to: .env.ps1"
}

while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-7)"

    switch ($choice) {
        "1" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-AppConfiguration
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "2" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-KeyVault
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "3" {
            Write-Host ""
            Assign-Roles
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "4" {
            Write-Host ""
            Store-Settings
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
            Write-Host ""
            Retrieve-ConnectionInfo
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
        "7" {
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host ""
            Write-Host "Invalid option. Please select 1-7."
            Write-Host ""
            Read-Host "Press Enter to continue"
        }
    }
}
