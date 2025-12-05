param location string
param environmentName string
param resourceToken string
param tags object

// Variables for naming
var foundryHubName = 'hub-${environmentName}-${resourceToken}'
var keyVaultName = 'kv-${resourceToken}'
var storageAccountName = 'st${resourceToken}'
var appInsightsName = 'appi-${environmentName}-${resourceToken}'
var containerRegistryName = 'cr${resourceToken}'

// Create Key Vault for storing Foundry API keys
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
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
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  tags: tags
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
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    RetentionInDays: 30
  }
}

// Create Container Registry
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: containerRegistryName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
    publicNetworkAccess: 'Enabled'
  }
}

// Create AI Hub resource for Foundry
resource aiHub 'Microsoft.MachineLearningServices/workspaces@2023-10-01' = {
  name: foundryHubName
  location: location
  kind: 'Default'
  tags: tags
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

// Outputs
output foundryEndpoint string = aiHub.properties.discoveryUrl
output foundryKey string = ''
output foundryHubName string = aiHub.name
