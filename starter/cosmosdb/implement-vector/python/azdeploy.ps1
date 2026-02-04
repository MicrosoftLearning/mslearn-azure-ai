#!/usr/bin/env pwsh

# Change the values of these variables as needed

# $rg = "<your-resource-group-name>"  # Resource Group name
# $location = "<your-azure-region>"   # Azure region for the resources

$rg = "rg-exercises"           # Resource Group name
$location = "canadacentral"          # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from Azure user object ID (based on az login account)
$script:userObjectId = (az ad signed-in-user show --query "id" -o tsv 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($script:userObjectId)) {
    Write-Host "Error: Not authenticated with Azure. Please run: az login"
    exit 1
}

$sha1 = [System.Security.Cryptography.SHA1]::Create()
$hashBytes = $sha1.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($script:userObjectId))
$userHash = ([System.BitConverter]::ToString($hashBytes).Replace("-", "").Substring(0, 8).ToLower())
$accountName = "cosmos-vector-$userHash"
$databaseName = "vectorstore"
$containerName = "vectors"

# Function to create resource group if it doesn't exist
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

# Function to create Azure Cosmos DB for NoSQL account with vector search capability
function Create-CosmosDBAccount {
    Write-Host "Creating Azure Cosmos DB for NoSQL account '$accountName'..."
    Write-Host "This may take several minutes..."

    # Check if Cosmos DB account already exists
    az cosmosdb show --resource-group $rg --name $accountName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        # Create Cosmos DB account with serverless capacity mode and vector search capability
        # EnableNoSQLVectorSearch enables the VectorDistance function for similarity queries
        az cosmosdb create `
            --resource-group $rg `
            --name $accountName `
            --locations regionName=$location `
            --capabilities EnableServerless EnableNoSQLVectorSearch `
            --default-consistency-level Session 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Cosmos DB account created with vector search capability"
        }
        else {
            Write-Host "Error: Failed to create Cosmos DB account"
            return
        }
    }
    else {
        Write-Host "✓ Cosmos DB account already exists: $accountName"
    }

    # Create database
    Write-Host "Creating database '$databaseName'..."
    az cosmosdb sql database show --resource-group $rg --account-name $accountName --name $databaseName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        az cosmosdb sql database create `
            --resource-group $rg `
            --account-name $accountName `
            --name $databaseName 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Database created: $databaseName"
        }
        else {
            Write-Host "Error: Failed to create database"
            return
        }
    }
    else {
        Write-Host "✓ Database already exists: $databaseName"
    }

    Write-Host ""
    Write-Host "Use option 2 to configure Entra ID access."
}

# Function to configure Entra ID RBAC for the signed-in user
function Configure-EntraAccess {
    Write-Host "Configuring Microsoft Entra ID access..."

    # Prereq check: Cosmos DB account must exist
    $status = (az cosmosdb show --resource-group $rg --name $accountName --query "provisioningState" -o tsv 2>$null)
    if ([string]::IsNullOrWhiteSpace($status)) {
        Write-Host "Error: Cosmos DB account '$accountName' not found."
        Write-Host "Please run option 1 to create the Cosmos DB account, then try again."
        return
    }

    if ($status -ne "Succeeded") {
        Write-Host "Error: Cosmos DB account is not ready (current state: $status)."
        Write-Host "Please wait for deployment to complete. Use option 3 to check status."
        return
    }

    # Get the signed-in user's UPN
    $userUpn = (az ad signed-in-user show --query userPrincipalName -o tsv 2>$null)

    if ([string]::IsNullOrWhiteSpace($script:userObjectId) -or [string]::IsNullOrWhiteSpace($userUpn)) {
        Write-Host "Error: Unable to retrieve signed-in user information."
        Write-Host "Please ensure you are logged in with 'az login'."
        return
    }

    $accountId = (az cosmosdb show --resource-group $rg --name $accountName --query "id" -o tsv)

    # Assign Azure RBAC Contributor role (for control plane: create/delete databases, containers)
    Write-Host "Assigning Azure RBAC 'Contributor' role to '$userUpn'..."
    $azureRoleExists = (az role assignment list `
        --assignee $script:userObjectId `
        --scope $accountId `
        --role "Contributor" `
        --query "[0].id" -o tsv 2>$null)

    if (-not [string]::IsNullOrWhiteSpace($azureRoleExists)) {
        Write-Host "✓ Azure RBAC Contributor role already assigned"
    }
    else {
        az role assignment create `
            --assignee $script:userObjectId `
            --scope $accountId `
            --role "Contributor" 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Azure RBAC Contributor role assigned"
        }
        else {
            Write-Host "Error: Failed to assign Azure RBAC Contributor role"
            return
        }
    }

    # Assign Cosmos DB Built-in Data Contributor role (for data plane: read/write items)
    Write-Host "Assigning 'Cosmos DB Built-in Data Contributor' role to '$userUpn'..."

    # Use the built-in role name for better maintainability
    $cosmosRoleName = "Cosmos DB Built-in Data Contributor"

    # Check if role assignment already exists
    $cosmosRoleExists = (az cosmosdb sql role assignment list `
        --resource-group $rg `
        --account-name $accountName `
        --query "[?principalId=='$($script:userObjectId)']" `
        -o tsv 2>$null)

    if (-not [string]::IsNullOrWhiteSpace($cosmosRoleExists)) {
        Write-Host "✓ Cosmos DB Data Contributor role already assigned"
    }
    else {
        az cosmosdb sql role assignment create `
            --resource-group $rg `
            --account-name $accountName `
            --role-definition-name "$cosmosRoleName" `
            --principal-id $script:userObjectId `
            --scope $accountId 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Cosmos DB Data Contributor role assigned"
        }
        else {
            Write-Host "Error: Failed to assign Cosmos DB Data Contributor role"
            return
        }
    }

    Write-Host ""
    Write-Host "Entra ID access configured for: $userUpn"
    Write-Host "  - Azure RBAC Contributor: manage databases and containers"
    Write-Host "  - Cosmos DB Data Contributor: read/write data"
}

# Function to check deployment status
function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    # Check Cosmos DB account
    Write-Host "Cosmos DB Account ($accountName):"
    $status = (az cosmosdb show --resource-group $rg --name $accountName --query "provisioningState" -o tsv 2>$null)

    if ([string]::IsNullOrWhiteSpace($status)) {
        Write-Host "  Status: Not created"
    }
    else {
        Write-Host "  Status: $status"
        if ($status -eq "Succeeded") {
            Write-Host "  ✓ Cosmos DB account is ready"

            # Check for vector search capability
            $capabilities = (az cosmosdb show --resource-group $rg --name $accountName --query "capabilities[].name" -o tsv 2>$null)
            if ($capabilities -match "EnableNoSQLVectorSearch") {
                Write-Host "  ✓ Vector search capability enabled"
            }
            else {
                Write-Host "  ⚠ Vector search capability not enabled"
            }

            # Check database
            az cosmosdb sql database show --resource-group $rg --account-name $accountName --name $databaseName 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  ✓ Database: $databaseName"
            }
            else {
                Write-Host "  ⚠ Database not created"
            }

            # Check Entra ID RBAC
            $userUpn = (az ad signed-in-user show --query userPrincipalName -o tsv 2>$null)
            $accountId = (az cosmosdb show --resource-group $rg --name $accountName --query "id" -o tsv)

            # Check Azure RBAC
            $azureRole = (az role assignment list `
                --assignee $script:userObjectId `
                --scope $accountId `
                --role "Contributor" `
                --query "[0].id" -o tsv 2>$null)

            # Check Cosmos DB data plane RBAC
            $cosmosRole = (az cosmosdb sql role assignment list `
                --resource-group $rg `
                --account-name $accountName `
                --query "[?principalId=='$($script:userObjectId)']" `
                -o tsv 2>$null)

            if (-not [string]::IsNullOrWhiteSpace($azureRole) -and -not [string]::IsNullOrWhiteSpace($cosmosRole)) {
                Write-Host "  ✓ Entra ID access: $userUpn (full control)"
            }
            elseif (-not [string]::IsNullOrWhiteSpace($cosmosRole)) {
                Write-Host "  ⚠ Entra ID access: $userUpn (data only, missing Azure RBAC)"
            }
            elseif (-not [string]::IsNullOrWhiteSpace($azureRole)) {
                Write-Host "  ⚠ Entra ID access: $userUpn (control plane only, missing data role)"
            }
            else {
                Write-Host "  ⚠ Entra ID access not configured"
            }
        }
    }
}

# Function to retrieve connection info and set environment variables
function Retrieve-ConnectionInfo {
    Write-Host "Retrieving connection information..."

    # Prereq check: Cosmos DB account must exist
    az cosmosdb show --resource-group $rg --name $accountName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: Cosmos DB account '$accountName' not found."
        Write-Host "Please run option 1 to create the Cosmos DB account, then try again."
        return
    }

    # Prereq check: Both RBAC roles must be configured
    $accountId = (az cosmosdb show --resource-group $rg --name $accountName --query "id" -o tsv)
    $cosmosRole = (az cosmosdb sql role assignment list `
        --resource-group $rg `
        --account-name $accountName `
        --query "[?principalId=='$($script:userObjectId)']" `
        -o tsv 2>$null)

    if ([string]::IsNullOrWhiteSpace($cosmosRole)) {
        Write-Host "Error: Entra ID access not configured for this account."
        Write-Host "Please run option 2 to configure Entra ID access, then try again."
        return
    }

    # Get endpoint
    $endpoint = (az cosmosdb show --resource-group $rg --name $accountName --query "documentEndpoint" -o tsv 2>$null)

    if ([string]::IsNullOrWhiteSpace($endpoint)) {
        Write-Host "Error: Unable to retrieve connection information."
        return
    }

    $scriptDir = Split-Path -Parent $PSCommandPath
    $envFile = Join-Path $scriptDir ".env.ps1"

    # Create or update .env.ps1 file with environment variable assignments (no key needed for Entra auth)
    @(
        "`$env:COSMOS_ENDPOINT = `"$endpoint`"",
        "`$env:COSMOS_DATABASE = `"$databaseName`"",
        "`$env:COSMOS_CONTAINER = `"$containerName`""
    ) | Set-Content -Path $envFile -Encoding UTF8

    Write-Host ""
    Write-Host "Cosmos DB Connection Information"
    Write-Host "==========================================================="
    Write-Host "Endpoint: $endpoint"
    Write-Host "Database: $databaseName"
    Write-Host "Container: $containerName"
    Write-Host "Authentication: Microsoft Entra ID (DefaultAzureCredential)"
    Write-Host ""
    Write-Host "Environment variables saved to: $envFile"
}

# Display menu
function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    Azure Cosmos DB Vector Search Deployment Menu"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Account Name: $accountName"
    Write-Host "Location: $location"
    Write-Host "====================================================================="
    Write-Host "1. Create Cosmos DB account (with vector search capability)"
    Write-Host "2. Configure Entra ID access"
    Write-Host "3. Check deployment status"
    Write-Host "4. Retrieve connection info"
    Write-Host "5. Exit"
    Write-Host "====================================================================="
}

# Main menu loop
while ($true) {
    Show-Menu
    $choice = Read-Host "Please select an option (1-5)"

    switch ($choice) {
        "1" {
            Write-Host ""
            Create-ResourceGroup
            Write-Host ""
            Create-CosmosDBAccount
            Write-Host ""
            Read-Host "Press Enter to continue..."
        }
        "2" {
            Write-Host ""
            Configure-EntraAccess
            Write-Host ""
            Read-Host "Press Enter to continue..."
        }
        "3" {
            Write-Host ""
            Check-DeploymentStatus
            Write-Host ""
            Read-Host "Press Enter to continue..."
        }
        "4" {
            Write-Host ""
            Retrieve-ConnectionInfo
            Write-Host ""
            Read-Host "Press Enter to continue..."
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
            Read-Host "Press Enter to continue..."
        }
    }

    Write-Host ""
}
