#!/usr/bin/env bash

# Change the values of these variables as needed

# rg="<your-resource-group-name>"  # Resource Group name
# location="<your-azure-region>"   # Azure region for the resources

rg="rg-exercise"        # Resource Group name
location="eastus"       # Azure region for the resources

# ============================================================================
# DON'T CHANGE ANYTHING BELOW THIS LINE.
# ============================================================================

# Generate consistent hash from Azure user object ID (based on az login account)
user_object_id=$(az ad signed-in-user show --query "id" -o tsv 2>/dev/null)
if [ -z "$user_object_id" ]; then
    echo "Error: Not authenticated with Azure. Please run: az login"
    exit 1
fi
user_hash=$(echo -n "$user_object_id" | sha1sum | cut -c1-8)

# Resource name with hash for uniqueness
acr_name="acr${user_hash}"

echo "====================================================================="
echo "    Azure Container Registry Exercise - Deployment Script"
echo "====================================================================="
echo "Resource Group: $rg"
echo "Location: $location"
echo "ACR Name: $acr_name"
echo "====================================================================="
echo ""

# Create resource group if it doesn't exist
echo "Creating resource group '$rg'..."
if az group exists --name $rg | grep -q "true"; then
    echo "✓ Resource group already exists: $rg"
else
    az group create --name $rg --location $location --output none
    echo "✓ Resource group created: $rg"
fi
echo ""

# Create Azure Container Registry
echo "Creating Azure Container Registry '$acr_name'..."
az acr create \
    --resource-group $rg \
    --name $acr_name \
    --sku Basic \
    --output none

if [ $? -eq 0 ]; then
    echo "✓ ACR created: $acr_name"
    echo "  Login server: $acr_name.azurecr.io"
else
    echo "Error: Failed to create ACR"
    exit 1
fi
echo ""

# Export environment variables for exercise commands
export RESOURCE_GROUP="$rg"
export ACR_NAME="$acr_name"
export LOCATION="$location"

echo "====================================================================="
echo "  Deployment Complete!"
echo "====================================================================="
echo ""
echo "The following environment variables have been exported for the exercise:"
echo ""
echo "  RESOURCE_GROUP=$RESOURCE_GROUP"
echo "  ACR_NAME=$ACR_NAME"
echo "  LOCATION=$LOCATION"
echo ""
echo "You can now run the Azure CLI commands from the exercise."
echo ""
echo "To verify, run: az acr show --name \$ACR_NAME --query loginServer --output tsv"
echo ""
echo "====================================================================="
