targetScope = 'subscription'

@minLength(1)
@description('Name of the environment used to derive resource names.')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Name of the resource group')
param resourceGroupName string = 'rg-exercises'

// Tags to apply to all resources
var tags = {
  'azd-env-name': environmentName
}

// Generate unique suffix for resource names
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

// Create resource group
resource resourceGroup 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

// Deploy Foundry resources
module foundryResources 'foundry.bicep' = {
  name: 'foundry-resources'
  scope: resourceGroup
  params: {
    location: location
    environmentName: environmentName
    resourceToken: resourceToken
    tags: tags
  }
}

// Outputs for azd environment variables
output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = resourceGroup.name

// Foundry outputs
output FOUNDRY_ENDPOINT string = foundryResources.outputs.foundryEndpoint
output FOUNDRY_KEY string = foundryResources.outputs.foundryKey
output FOUNDRY_HUB_NAME string = foundryResources.outputs.foundryHubName
