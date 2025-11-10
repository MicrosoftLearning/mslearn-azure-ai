#!/usr/bin/env bash

# Variables
RESOURCE_GROUP="rg-exercises"
CACHE_NAME="amr2-exercise"
POLICY_NAME="dataContributorPolicy"
IDENTITY_ID=$(az ad signed-in-user show --query id -o tsv)

# Assign access policy to your identity
# Note: "default" may have minimal permissions - consider using Azure portal instead
echo "Assigning default access policy to identity ID '$IDENTITY_ID'..."

az redisenterprise database access-policy-assignment create \
    --resource-group $RESOURCE_GROUP \
    --cluster-name $CACHE_NAME \
    --database-name "default" \
    --name "userAssignment" \
    --object-id $IDENTITY_ID \
    --access-policy-name "default"