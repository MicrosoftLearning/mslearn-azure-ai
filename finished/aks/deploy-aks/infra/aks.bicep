param location string = 'westus2'
param resourceGroupName string = 'rg-exercises'
param aksClusterName string = 'aks-cluster'
param acrName string = 'acr'

// Variables for naming
var deploymentNameHash = uniqueString(resourceGroup().id)
var finalAksName = '${aksClusterName}-${deploymentNameHash}'
var finalAcrName = '${acrName}${deploymentNameHash}'

// Create AKS Cluster
resource aksCluster 'Microsoft.ContainerService/managedClusters@2023-10-01' = {
  name: finalAksName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    kubernetesVersion: '1.27'
    enableRBAC: true
    dnsPrefix: finalAksName
    agentPoolProfiles: [
      {
        name: 'nodepool1'
        count: 1
        vmSize: 'Standard_B2s'
        osType: 'Linux'
        mode: 'System'
      }
    ]
    networkProfile: {
      networkPlugin: 'azure'
      loadBalancerSku: 'standard'
    }
  }
}

// Create Container Registry
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: finalAcrName
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
output aksClusterName string = aksCluster.name
output aksClusterId string = aksCluster.id
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
