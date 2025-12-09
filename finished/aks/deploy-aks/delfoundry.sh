#!/usr/bin/env bash

# Delete and purge Foundry resource

# Configuration
rg="rg-exercises"           # Resource Group name
location="eastus2"          # Azure region (change if needed)

# Generate consistent hash from username (same as azdeploy.sh)
user_hash=$(echo -n "$USER" | sha1sum | cut -c1-8)
foundry_resource="foundry-resource-${user_hash}"

echo "Deleting and purging Foundry resource: $foundry_resource"
echo "Resource Group: $rg"
echo "Location: $location"
echo ""

# Delete the Foundry resource
echo "Deleting resource..."
az cognitiveservices account delete \
    --name "$foundry_resource" \
    --resource-group "$rg"

if [ $? -ne 0 ]; then
    echo "Error: Failed to delete resource."
    exit 1
fi

echo "✓ Resource deleted"
echo ""

# Purge the Foundry resource to free up the name
echo "Purging resource to free up the name..."
az cognitiveservices account purge \
    --name "$foundry_resource" \
    --resource-group "$rg" \
    --location "$location"

if [ $? -ne 0 ]; then
    echo "Error: Failed to purge resource."
    exit 1
fi

echo "✓ Resource purged"
echo ""
echo "The Foundry resource has been deleted and purged. You can now create a new one in a different region."
