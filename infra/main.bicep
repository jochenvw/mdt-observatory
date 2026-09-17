targetScope = 'subscription'

param environmentName string = 'mdt-observatory-demo'
param resourceGroupName string = 'rg-mdt-observatory-demo'
@allowed([
  'westeurope'
  'swedencentral'
])
param location string = 'westeurope'
@secure()
@minLength(32)
@maxLength(512)
param demoToken string
param bootstrap bool = true
param containerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
param revisionSuffix string = 'bootstrap'
param openAiSubscriptionId string = subscription().subscriptionId
param openAiResourceGroup string = 'nl-stu-jvw-foundry-rg'
param openAiAccountName string = 'nl-stu-jvw-ai-saoyr2'
param openAiEndpoint string = 'https://nl-stu-jvw-ai-saoyr2.openai.azure.com'
param openAiDeployment string = 'nl-stu-jvw-gpt-6-astra'
@description('Maximum overlapping live role loops within the single app replica.')
@minValue(1)
@maxValue(7)
param azureMaxConcurrentRoles int = 3
@description('Shared minimum seconds between model request starts, including retries.')
@minValue(0)
@maxValue(60)
param azureRequestIntervalSeconds int = 20

var tags = {
  'azd-env-name': environmentName
  application: 'mdt-observatory'
  dataClassification: 'synthetic-only'
}

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module resources 'modules/resources.bicep' = {
  name: 'mdt-resources'
  scope: rg
  params: {
    name: 'mdt-observatory'
    location: location
    tags: tags
    demoToken: demoToken
    bootstrap: bootstrap
    containerImage: containerImage
    revisionSuffix: revisionSuffix
    openAiEndpoint: openAiEndpoint
    openAiDeployment: openAiDeployment
    azureMaxConcurrentRoles: azureMaxConcurrentRoles
    azureRequestIntervalSeconds: azureRequestIntervalSeconds
  }
}

module acrPull 'modules/acr-pull-role.bicep' = {
  name: 'mdt-acr-pull'
  scope: rg
  params: {
    registryName: resources.outputs.registryName
    principalId: resources.outputs.principalId
  }
}

module openAiRole 'modules/openai-role.bicep' = {
  name: 'mdt-openai-user'
  scope: resourceGroup(openAiSubscriptionId, openAiResourceGroup)
  params: {
    accountName: openAiAccountName
    principalId: resources.outputs.principalId
  }
}

module blobRole 'modules/blob-role.bicep' = {
  name: 'mdt-blob-data-contributor'
  scope: rg
  params: {
    storageAccountName: resources.outputs.storageName
    containerName: resources.outputs.blobContainerName
    principalId: resources.outputs.principalId
  }
}

output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_LOCATION string = location
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.registryName
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryEndpoint
output AZURE_CONTAINER_APP_NAME string = resources.outputs.appName
output AZURE_CONTAINER_APP_IDENTITY_PRINCIPAL_ID string = resources.outputs.principalId
output AZURE_CONTAINER_APP_FQDN string = resources.outputs.fqdn
output AZURE_CONTAINER_APPS_ENVIRONMENT_ID string = resources.outputs.environmentId
output AZURE_LOG_ANALYTICS_WORKSPACE_ID string = resources.outputs.workspaceId
output AZURE_APPLICATION_INSIGHTS_NAME string = resources.outputs.insightsName
output AZURE_STORAGE_ACCOUNT_NAME string = resources.outputs.storageName
output AZURE_STORAGE_BLOB_CONTAINER_NAME string = resources.outputs.blobContainerName
output AZURE_STORAGE_BLOB_ACCOUNT_URL string = resources.outputs.blobAccountUrl
output AZURE_VNET_ID string = resources.outputs.vnetId
output AZURE_BLOB_PRIVATE_ENDPOINT_ID string = resources.outputs.blobPrivateEndpointId
output WEB_URL string = 'https://${resources.outputs.fqdn}'
