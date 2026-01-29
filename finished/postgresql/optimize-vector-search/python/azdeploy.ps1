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
$serverName = "psql-agent-$userHash"

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

# Function to create Azure Database for PostgreSQL Flexible Server
function Create-PostgresServer {
    Write-Host "Creating Azure Database for PostgreSQL Flexible Server '$serverName'..."
    Write-Host "This may take several minutes..."

    az postgres flexible-server show --resource-group $rg --name $serverName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        # General Purpose tier required for:
        # - PgBouncer connection pooling support (not available on Burstable)
        # - Sustained CPU for building vector indexes on large datasets
        # - Memory for HNSW index operations
        az postgres flexible-server create `
            --resource-group $rg `
            --name $serverName `
            --location $location `
            --sku-name Standard_D2ds_v4 `
            --tier GeneralPurpose `
            --storage-size 32 `
            --version 16 `
            --public-access 0.0.0.0-255.255.255.255 `
            --microsoft-entra-auth Enabled `
            --password-auth Disabled 2>&1 | Out-Null

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ PostgreSQL server created successfully"
            Write-Host "  Use option 2 to configure Microsoft Entra administrator."
        }
        else {
            Write-Host "Error: Failed to start PostgreSQL server deployment"
            return
        }
    }
    else {
        Write-Host "✓ PostgreSQL server already exists: $serverName"
    }
}

# Function to configure Microsoft Entra admin
function Configure-EntraAdmin {
    Write-Host "Configuring Microsoft Entra administrator..."

    # Prereq check: PostgreSQL server must exist
    $state = (az postgres flexible-server show --resource-group $rg --name $serverName --query "state" -o tsv 2>$null)
    if ([string]::IsNullOrWhiteSpace($state)) {
        Write-Host "Error: PostgreSQL server '$serverName' not found."
        Write-Host "Please run option 1 to create the PostgreSQL server, then try again."
        return
    }

    # Prereq check: Server must be in Ready state
    if ($state -ne "Ready") {
        Write-Host "Error: PostgreSQL server is not ready (current state: $state)."
        Write-Host "Please wait for deployment to complete. Use option 3 to check status."
        return
    }

    # Get the signed-in user's UPN (object ID already retrieved at startup)
    $userUpn = (az ad signed-in-user show --query userPrincipalName -o tsv 2>$null)

    if ([string]::IsNullOrWhiteSpace($script:userObjectId) -or [string]::IsNullOrWhiteSpace($userUpn)) {
        Write-Host "Error: Unable to retrieve signed-in user information."
        Write-Host "Please ensure you are logged in with 'az login'."
        return
    }

    Write-Host "Setting '$userUpn' as Entra administrator..."

    az postgres flexible-server microsoft-entra-admin create `
        --resource-group $rg `
        --server-name $serverName `
        --display-name "$userUpn" `
        --object-id "$script:userObjectId" 2>&1 | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Microsoft Entra administrator configured: $userUpn"
    }
    else {
        Write-Host "Error: Failed to configure Entra administrator"
    }
}

# Function to check deployment status
function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    # Check PostgreSQL server
    Write-Host "PostgreSQL Server ($serverName):"
    $state = (az postgres flexible-server show --resource-group $rg --name $serverName --query "state" -o tsv 2>$null)

    if ([string]::IsNullOrWhiteSpace($state)) {
        Write-Host "  Status: Not created"
    }
    else {
        Write-Host "  Status: $state"
        if ($state -eq "Ready") {
            Write-Host "  ✓ PostgreSQL server is ready"
        }

        # Check Entra admin configuration
        $adminName = (az postgres flexible-server microsoft-entra-admin list --resource-group $rg --server-name $serverName --query "[0].principalName" -o tsv 2>$null)
        if (-not [string]::IsNullOrWhiteSpace($adminName)) {
            Write-Host "  ✓ Entra administrator: $adminName"
        }
        else {
            Write-Host "  ⚠ Entra administrator not configured"
        }
    }
}

# Function to retrieve connection info and set environment variables
function Retrieve-ConnectionInfo {
    Write-Host "Retrieving connection information..."

    # Prereq check: PostgreSQL server must exist
    $state = (az postgres flexible-server show --resource-group $rg --name $serverName --query "state" -o tsv 2>$null)
    if ([string]::IsNullOrWhiteSpace($state)) {
        Write-Host "Error: PostgreSQL server '$serverName' not found."
        Write-Host "Please run option 1 to create the PostgreSQL server, then try again."
        return
    }

    # Prereq check: Server must be in Ready state
    if ($state -ne "Ready") {
        Write-Host "Error: PostgreSQL server is not ready (current state: $state)."
        Write-Host "Please wait for deployment to complete. Use option 3 to check status."
        return
    }

    # Prereq check: Entra admin must be configured
    $adminName = (az postgres flexible-server microsoft-entra-admin list --resource-group $rg --server-name $serverName --query "[0].principalName" -o tsv 2>$null)
    if ([string]::IsNullOrWhiteSpace($adminName)) {
        Write-Host "Error: Microsoft Entra administrator not configured on '$serverName'."
        Write-Host "Please run option 2 to configure the Entra administrator, then try again."
        return
    }

    # Get the signed-in user's UPN for the database user
    $userUpn = (az ad signed-in-user show --query userPrincipalName -o tsv 2>$null)

    if ([string]::IsNullOrWhiteSpace($userUpn)) {
        Write-Host "Error: Unable to retrieve signed-in user information."
        Write-Host "Please ensure you are logged in with 'az login'."
        return
    }

    # Get access token for PostgreSQL
    Write-Host "Retrieving access token..."
    $accessToken = (az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv 2>$null)

    if ([string]::IsNullOrWhiteSpace($accessToken)) {
        Write-Host "Error: Unable to retrieve access token."
        return
    }

    # Set connection variables
    $dbHost = "$serverName.postgres.database.azure.com"
    $dbName = "postgres"
    $dbUser = $userUpn

    $scriptDir = Split-Path -Parent $PSCommandPath
    $envFile = Join-Path $scriptDir ".env.ps1"

    # Create or update .env.ps1 file with environment variable assignments
    @(
        "`$env:DB_HOST = `"$dbHost`"",
        "`$env:DB_NAME = `"$dbName`"",
        "`$env:DB_USER = `"$dbUser`"",
        "`$env:PGPASSWORD = `"$accessToken`""
    ) | Set-Content -Path $envFile -Encoding UTF8

    Write-Host ""
    Write-Host "PostgreSQL Connection Information"
    Write-Host "==========================================================="
    Write-Host "Host: $dbHost"
    Write-Host "Database: $dbName"
    Write-Host "User: $dbUser"
    Write-Host "Password: (Entra token - expires in ~1 hour)"
    Write-Host ""
    Write-Host "Environment variables saved to: $envFile"
}

# Display menu
function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    Azure Database for PostgreSQL Deployment Menu"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Server Name: $serverName"
    Write-Host "Location: $location"
    Write-Host "====================================================================="
    Write-Host "1. Create PostgreSQL server with Entra authentication"
    Write-Host "2. Configure Microsoft Entra administrator"
    Write-Host "3. Check deployment status"
    Write-Host "4. Retrieve connection info and access token"
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
            Create-PostgresServer
            Write-Host ""
            Read-Host "Press Enter to continue..."
        }
        "2" {
            Write-Host ""
            Configure-EntraAdmin
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
