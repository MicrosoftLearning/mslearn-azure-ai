# Change the values of these variables as needed

# $rg = "<your-resource-group-name>"  # Resource Group name
# $location = "<your-azure-region>"   # Azure region for the resources

$rg = "rg-exercise"        # Resource Group name
$location = "eastus"       # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from Azure user object ID (based on az login account)
$userObjectId = (az ad signed-in-user show --query "id" -o tsv 2>&1) | Where-Object { $_ -notmatch 'ERROR' } | Select-Object -First 1
if ([string]::IsNullOrEmpty($userObjectId)) {
    Write-Host "Error: Not authenticated with Azure. Please run: az login"
    exit 1
}

# Create hash from user object ID
$sha1 = [System.Security.Cryptography.SHA1]::Create()
$hashBytes = $sha1.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($userObjectId))
$userHash = [System.BitConverter]::ToString($hashBytes).Replace("-", "").Substring(0, 8).ToLower()

# Resource name with hash for uniqueness
$acrName = "acr$userHash"

Write-Host "====================================================================="
Write-Host "    Azure Container Registry Exercise - Deployment Script"
Write-Host "====================================================================="
Write-Host "Resource Group: $rg"
Write-Host "Location: $location"
Write-Host "ACR Name: $acrName"
Write-Host "====================================================================="
Write-Host ""

# Create resource group if it doesn't exist
Write-Host "Creating resource group '$rg'..."
$exists = az group exists --name $rg
if ($exists -eq "false") {
    az group create --name $rg --location $location --output none
    Write-Host "✓ Resource group created: $rg"
}
else {
    Write-Host "✓ Resource group already exists: $rg"
}
Write-Host ""

# Create Azure Container Registry
Write-Host "Creating Azure Container Registry '$acrName'..."
az acr create `
    --resource-group $rg `
    --name $acrName `
    --sku Basic `
    --output none

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ ACR created: $acrName"
    Write-Host "  Login server: $acrName.azurecr.io"
}
else {
    Write-Host "Error: Failed to create ACR"
    exit 1
}
Write-Host ""

# Set environment variables for exercise commands
$env:RESOURCE_GROUP = $rg
$env:ACR_NAME = $acrName
$env:LOCATION = $location

Write-Host "====================================================================="
Write-Host "  Deployment Complete!"
Write-Host "====================================================================="
Write-Host ""
Write-Host "The following environment variables have been set for the exercise:"
Write-Host ""
Write-Host "  RESOURCE_GROUP=$env:RESOURCE_GROUP"
Write-Host "  ACR_NAME=$env:ACR_NAME"
Write-Host "  LOCATION=$env:LOCATION"
Write-Host ""
Write-Host "You can now run the Azure CLI commands from the exercise."
Write-Host ""
Write-Host 'To verify, run: az acr show --name $env:ACR_NAME --query loginServer --output tsv'
Write-Host ""
Write-Host "====================================================================="
