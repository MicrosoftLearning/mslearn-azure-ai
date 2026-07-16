# Azure Managed Redis Deployment Script (PowerShell)

# Change the values of these variables as needed

# $rg = "<your-resource-group-name>"  # Resource Group name
# $location = "<your-azure-region>"   # Azure region for the resources

$rg = "rg-exercises"        # Resource Group name
$location = "westus2"       # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from Azure user object ID (based on az login account)
$user_object_id = az ad signed-in-user show --query "id" -o tsv 2>$null
if ([string]::IsNullOrWhiteSpace($user_object_id)) {
    Write-Host "Error: Not authenticated with Azure. Please run: az login"
    exit 1
}
$bytes = [System.Text.Encoding]::UTF8.GetBytes($user_object_id)
$sha1 = [System.Security.Cryptography.SHA1]::Create()
$hashBytes = $sha1.ComputeHash($bytes)
$user_hash = [System.BitConverter]::ToString($hashBytes).Replace("-", "").Substring(0, 8).ToLower()
$cache_name = "amr-exercise-$user_hash"

# Run a command quietly, but surface its exit code and output if it fails. This
# keeps the console clean on success while still reporting the error details
# when a command fails, instead of silently discarding them. Use for action
# commands (create/update/delete), not for commands whose output you need to
# capture.
# Usage: Invoke-Quiet "Description of the step" { az ... }
function Invoke-Quiet {
    param(
        [string]$Description,
        [scriptblock]$Command
    )
    $output = & $Command 2>&1
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        Write-Host "Error: $Description failed (exit code $rc)."
        if ($output) {
            Write-Host ($output | Out-String)
        }
        return $false
    }
    return $true
}

# Function to create resource group if it doesn't exist
function Create-ResourceGroup {
    Write-Host "Checking resource group '$rg'..."
    $exists = az group exists --name $rg
    if ($exists -eq "false") {
        if (-not (Invoke-Quiet "Create resource group" { az group create --name $rg --location $location })) { return }
        Write-Host "Resource group created: $rg"
    } else {
        Write-Host "Resource group already exists: $rg"
    }
}

# Function to create Azure Managed Redis resource
function Create-RedisResource {
    Create-ResourceGroup
    Write-Host ""

    # Check the current state of the cluster before deciding what to do.
    $cluster_state = az redisenterprise show --resource-group $rg --name $cache_name --query "provisioningState" -o tsv 2>$null
    switch ($cluster_state) {
        "Succeeded" {
            Write-Host "Azure Managed Redis resource already exists: $cache_name (State: $cluster_state)"
            return
        }
        { $_ -eq "Failed" -or $_ -eq "Canceled" } {
            Write-Host "A previous deployment of '$cache_name' is in a $cluster_state state."
            Write-Host "Deleting the failed resource before trying again..."
            $deleted = Invoke-Quiet "Delete failed Azure Managed Redis resource" {
                az redisenterprise delete `
                    --resource-group $rg `
                    --name $cache_name `
                    --yes `
                    --only-show-errors
            }
            if (-not $deleted) { return }
            Write-Host "Failed resource deleted."
            Write-Host ""
        }
        "" {
            # No existing cluster; continue to create it below.
        }
        $null {
            # No existing cluster; continue to create it below.
        }
        default {
            Write-Host "Azure Managed Redis resource '$cache_name' is still provisioning (State: $cluster_state)."
            Write-Host "Please wait for it to finish, then check the deployment status from the menu."
            return
        }
    }

    Write-Host "Creating Azure Managed Redis resource '$cache_name' in '$location'..."
    Write-Host "This takes 5-10 minutes to complete. Please wait..."

    $created = Invoke-Quiet "Create Azure Managed Redis resource" {
        az redisenterprise create `
            --resource-group $rg `
            --name $cache_name `
            --location $location `
            --sku "Balanced_B0" `
            --public-network-access "Enabled" `
            --no-database `
            --only-show-errors
    }
    if (-not $created) {
        Write-Host ""
        Write-Host "The deployment failed. This is most often caused by a temporary"
        Write-Host "lack of capacity for this SKU in the '$location' region."
        Write-Host ""
        Write-Host "To resolve this:"
        Write-Host "  1. Choose option 4 to exit the script."
        Write-Host "  2. Near the top of this script, change the 'location' variable to a"
        Write-Host "     different region, such as eastus2, australiaeast, or canadacentral."
        Write-Host "  3. Run the script again and choose option 1. The failed resource is"
        Write-Host "     deleted automatically before the next attempt."
        return
    }

    Write-Host ""
    Write-Host "Azure Managed Redis resource created successfully: $cache_name"
}

# Function to check deployment status
function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    Write-Host ""

    Write-Host "Cluster ($cache_name):"
    $cluster_state = az redisenterprise show --resource-group $rg --name $cache_name --query "provisioningState" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($cluster_state)) {
        Write-Host "  Provisioning state: $cluster_state"
    } else {
        Write-Host "  Status: Not created"
    }

    Write-Host ""
    Write-Host "Database:"
    $db_state = az redisenterprise database show --resource-group $rg --cluster-name $cache_name --query "provisioningState" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($db_state)) {
        Write-Host "  Provisioning state: $db_state"
    } else {
        Write-Host "  Status: Not created"
    }
}

# Function to create the database, grant the current user Microsoft Entra ID
# access, and write the .env file with the Redis endpoint
function Create-DatabaseAndConfigureAccess {

    # Check if cluster is provisioned
    $cluster_state = az redisenterprise show --resource-group $rg --name $cache_name --query "provisioningState" -o tsv 2>$null
    if ($cluster_state -ne "Succeeded") {
        $state_display = if ([string]::IsNullOrWhiteSpace($cluster_state)) { "Not created" } else { $cluster_state }
        Write-Host "Error: Cluster is not ready (State: $state_display)."
        Write-Host "Please check the deployment status (option 3) and wait until provisioning succeeds."
        return
    }

    # Check if database already exists
    $db_state = az redisenterprise database show --resource-group $rg --cluster-name $cache_name --query "provisioningState" -o tsv 2>$null
    if (-not [string]::IsNullOrWhiteSpace($db_state)) {
        Write-Host "Database already exists (State: $db_state)."
    } else {
        Write-Host "Creating database..."
        $created = Invoke-Quiet "Create database" {
            az redisenterprise database create `
                --resource-group $rg `
                --cluster-name $cache_name `
                --client-protocol "Encrypted" `
                --clustering-policy "NoCluster" `
                --eviction-policy "AllKeysLRU" `
                --port 10000 `
                --only-show-errors
        }
        if (-not $created) { return }
    }

    # Grant the signed-in user access to the database using Microsoft Entra ID.
    # This assigns the built-in "default" access policy to the user's object ID
    # so the app can authenticate with DefaultAzureCredential instead of a key.
    $assignment_name = "useraccess"
    $assignment_state = az redisenterprise database access-policy-assignment show `
        --resource-group $rg `
        --cluster-name $cache_name `
        --database-name default `
        --access-policy-assignment-name $assignment_name `
        --query "provisioningState" -o tsv 2>$null

    if (-not [string]::IsNullOrWhiteSpace($assignment_state)) {
        Write-Host "Microsoft Entra access is already assigned for the current user."
    } else {
        Write-Host "Assigning Microsoft Entra access for the current user..."
        $assigned = Invoke-Quiet "Assign access policy" {
            az redisenterprise database access-policy-assignment create `
                --resource-group $rg `
                --cluster-name $cache_name `
                --database-name default `
                --access-policy-assignment-name $assignment_name `
                --access-policy-name default `
                --object-id $user_object_id `
                --only-show-errors
        }
        if (-not $assigned) { return }
    }

    Write-Host "Retrieving endpoint..."

    # Get the endpoint (hostname)
    $hostname = az redisenterprise show --resource-group $rg --name $cache_name --query "hostName" -o tsv 2>$null

    # Check if the value is empty
    if ([string]::IsNullOrWhiteSpace($hostname)) {
        Write-Host ""
        Write-Host "Error: Unable to retrieve the endpoint."
        Write-Host "Please check the deployment status to ensure the resource is fully provisioned."
        return
    }

    # Write .env.ps1 file
    "`$env:REDIS_HOST = `"$hostname`"" | Set-Content ".env.ps1"

    Clear-Host
    Write-Host ""
    Write-Host "Redis Connection Information"
    Write-Host "==========================================================="
    Write-Host "Endpoint: $hostname"
    Write-Host "Authentication: Microsoft Entra ID (current user)"
    Write-Host ""
    Write-Host "The endpoint has been saved to the .env.ps1 file"
}

# Display menu
function Show-Menu {
    Clear-Host
    Write-Host "====================================================================="
    Write-Host "    Azure Managed Redis Deployment Menu"
    Write-Host "====================================================================="
    Write-Host "Resource Group: $rg"
    Write-Host "Cache Name: $cache_name"
    Write-Host "Location: $location"
    Write-Host "====================================================================="
    Write-Host "1. Create Azure Managed Redis resource"
    Write-Host "2. Create database and configure access"
    Write-Host "3. Check deployment status"
    Write-Host "4. Exit"
    Write-Host "====================================================================="
}

# Main menu loop
do {
    Show-Menu
    $choice = Read-Host "Please select an option (1-4)"

    switch ($choice) {
        "1" {
            Write-Host ""
            Create-RedisResource
            Write-Host ""
            Read-Host "Press Enter to continue..."
        }
        "2" {
            Write-Host ""
            Create-DatabaseAndConfigureAccess
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
            Write-Host "Exiting..."
            Clear-Host
            exit 0
        }
        default {
            Write-Host ""
            Write-Host "Invalid option. Please select 1-4."
            Write-Host ""
            Read-Host "Press Enter to continue..."
        }
    }

    Write-Host ""
} while ($choice -ne "4")