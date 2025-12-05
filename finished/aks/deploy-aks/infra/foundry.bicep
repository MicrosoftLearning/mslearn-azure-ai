param location string = 'westus2'
param resourceGroupName string = 'rg-exercises'
param foundryDeploymentName string = 'gpt4o-deployment'

// Variables for naming
var deploymentNameHash = uniqueString(resourceGroup().id)
var foundryProjectName = '${foundryDeploymentName}-${deploymentNameHash}'

// Create AI Hub resource for Foundry
resource aiHub 'Microsoft.MachineLearningServices/workspaces@2023-10-01' = {
  name: foundryProjectName
  location: location
  kind: 'Default'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: 'AI Hub for gpt-4o-mini model deployment'
    friendlyName: 'Foundry Model Hub'
    keyVault: keyVault.id
    applicationInsights: appInsights.id
    containerRegistry: containerRegistry.id
    storageAccount: storageAccount.id
  }
}

// Create Key Vault for storing Foundry API keys
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${deploymentNameHash}'
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    accessPolicies: []
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

// Create Storage Account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'st${deploymentNameHash}'
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
  }
}

// Create Application Insights for monitoring
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${deploymentNameHash}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    RetentionInDays: 30
  }
}

// Create Container Registry
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'cr${deploymentNameHash}'
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
    publicNetworkAccess: 'Enabled'
  }
}

// Outputs
output foundryEndpoint string = aiHub.properties.discoveryUrl
output foundryKey string = 'PLACEHOLDER_SET_MANUALLY'
output aiHubName string = aiHub.name
