# Azure Managed Redis Deployment Script (PowerShell)

# Change the values of these variables as needed
$rg = "rg-exercises"        # Resource Group name
$location = "westus2"       # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from username (always produces valid Azure resource name)
$bytes = [System.Text.Encoding]::UTF8.GetBytes($env:USERNAME)
$sha1 = [System.Security.Cryptography.SHA1]::Create()
$hashBytes = $sha1.ComputeHash($bytes)
$user_hash = [System.BitConverter]::ToString($hashBytes).Replace("-", "").Substring(0, 8).ToLower()
$cache_name = "amr-exercise-$user_hash"

# Function to create Azure Managed Redis resource
function Create-RedisResource {
    Write-Host "Creating Azure Managed Redis Enterprise cluster '$cache_name'..."

    # Create the Redis Enterprise cluster (E10 is the cheapest SKU that supports modules)
    az redisenterprise create `
        --resource-group $rg `
        --name $cache_name `
        --location $location `
        --sku Enterprise_E10 `
        --public-network-access "Enabled" `
        --clustering-policy "EnterpriseCluster" `
        --eviction-policy "NoEviction" `
        --modules "name=RediSearch" `
        --no-wait

    Write-Host "The Azure Managed Redis Enterprise cluster is being created and takes 5-10 minutes to complete."
    Write-Host "You can check the deployment status from the menu later in the exercise."
}

# Function to check deployment status
function Check-DeploymentStatus {
    Write-Host "Checking deployment status..."
    az redisenterprise show --resource-group $rg --name $cache_name --query "provisioningState"
}

# Function to retrieve endpoint and access key
function Get-EndpointAndKey {
    Write-Host "Enabling access key authentication to trigger key generation..."

    # Enable access key authentication on the cluster to trigger key generation
    az redisenterprise database update `
        --resource-group $rg `
        --cluster-name $cache_name `
        --access-keys-auth "Enabled" `
        2>$null | Out-Null

    Write-Host "Retrieving endpoint and access key..."

    # Get the endpoint (hostname and port)
    $hostname = az redisenterprise show --resource-group $rg --name $cache_name --query "hostName" -o tsv 2>$null

    # Get the primary access key
    $primaryKey = az redisenterprise database list-keys --cluster-name $cache_name -g $rg --query "primaryKey" -o tsv 2>$null

    # Check if values are empty
    if ([string]::IsNullOrWhiteSpace($hostname) -or [string]::IsNullOrWhiteSpace($primaryKey)) {
        Write-Host ""
        Write-Host "Unable to retrieve endpoint or access key."
        Write-Host "Please check the deployment status to ensure the resource is fully provisioned."
        Write-Host "Use menu option 2 to check deployment status."
        return
    }

    # Create or update .env file
    $envFilePath = ".env"
    if (Test-Path $envFilePath) {
        # Read existing content
        $envContent = Get-Content $envFilePath -Raw

        # Update or add REDIS_HOST
        if ($envContent -match "REDIS_HOST=") {
            $envContent = $envContent -replace "REDIS_HOST=.*", "REDIS_HOST=$hostname"
        } else {
            $envContent += "`nREDIS_HOST=$hostname"
        }

        # Update or add REDIS_KEY
        if ($envContent -match "REDIS_KEY=") {
            $envContent = $envContent -replace "REDIS_KEY=.*", "REDIS_KEY=$primaryKey"
        } else {
            $envContent += "`nREDIS_KEY=$primaryKey"
        }

        # Write back to file
        $envContent | Set-Content $envFilePath -NoNewline
        Write-Host "Updated existing .env file"
    } else {
        # Create new .env file
        @"
REDIS_HOST=$hostname
REDIS_KEY=$primaryKey
"@ | Set-Content $envFilePath -NoNewline
        Write-Host "Created new .env file"
    }

    Clear-Host
    Write-Host ""
    Write-Host "Redis Connection Information"
    Write-Host "==========================================================="
    Write-Host "Endpoint: $hostname"
    Write-Host "Primary Key: $primaryKey"
    Write-Host ""
    Write-Host "Values have been saved to .env file"
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
    Write-Host "2. Check deployment status"
    Write-Host "3. Configure for search and retrieve endpoint and access key"
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
            Check-DeploymentStatus
            Write-Host ""
            Read-Host "Press Enter to continue..."
        }
        "3" {
            Write-Host ""
            Get-EndpointAndKey
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