param name string
param location string
param tags object
@secure()
param demoToken string
param bootstrap bool
param containerImage string
param revisionSuffix string
param openAiEndpoint string
param openAiDeployment string
@minValue(1)
@maxValue(7)
param azureMaxConcurrentRoles int = 3
@minValue(0)
@maxValue(60)
param azureRequestIntervalSeconds int = 20

var suffix = uniqueString(subscription().subscriptionId, resourceGroup().name)
var appName = '${name}-vnet'

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acrmdt${suffix}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${name}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${name}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    IngestionMode: 'LogAnalytics'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stmdt${suffix}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'None'
    }
  }
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource stateContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobs
  name: 'mdt-state'
  properties: {
    publicAccess: 'None'
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-${name}'
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.64.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'aca'
        properties: {
          addressPrefix: '10.64.0.0/23'
          delegations: [
            {
              name: 'container-apps'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'private-endpoints'
        properties: {
          addressPrefix: '10.64.2.0/27'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

resource blobDns 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.blob.${az.environment().suffixes.storage}'
  location: 'global'
  tags: tags
}

resource blobDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: blobDns
  name: 'mdt-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource blobEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-${name}-blob'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/private-endpoints'
    }
    privateLinkServiceConnections: [
      {
        name: 'blob'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: [
            'blob'
          ]
        }
      }
    ]
  }
}

resource blobDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: blobEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob'
        properties: {
          privateDnsZoneId: blobDns.id
        }
      }
    ]
  }
}

resource environment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: 'cae-${name}-vnet'
  location: location
  tags: tags
  properties: {
    vnetConfiguration: {
      infrastructureSubnetId: '${vnet.id}/subnets/aca'
      internal: false
    }
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

resource app 'Microsoft.App/containerApps@2025-01-01' = {
  name: appName
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Multiple'
      maxInactiveRevisions: 5
      ingress: {
        external: !bootstrap
        allowInsecure: false
        targetPort: bootstrap ? 80 : 8000
        transport: 'auto'
        traffic: [
          {
            revisionName: '${appName}--${revisionSuffix}'
            weight: 100
          }
        ]
        stickySessions: {
          affinity: 'none'
        }
      }
      registries: bootstrap ? [] : [
        {
          server: registry.properties.loginServer
          identity: 'system'
        }
      ]
      secrets: bootstrap ? [] : [
        {
          name: 'presenter-token'
          value: demoToken
        }
        {
          name: 'applicationinsights-connection-string'
          value: insights.properties.ConnectionString
        }
      ]
    }
    template: {
      revisionSuffix: revisionSuffix
      terminationGracePeriodSeconds: 60
      containers: [
        {
          name: 'web'
          image: containerImage
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: bootstrap ? [] : [
            { name: 'MDT_STORAGE_BACKEND', value: 'azure_blob' }
            { name: 'MDT_BLOB_ACCOUNT_URL', value: 'https://${storage.name}.blob.${az.environment().suffixes.storage}' }
            { name: 'MDT_BLOB_CONTAINER', value: stateContainer.name }
            { name: 'MDT_PRESENTER_TOKEN', secretRef: 'presenter-token' }
            { name: 'MDT_SECURE_COOKIE', value: 'true' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: openAiEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: openAiDeployment }
            { name: 'MDT_AZURE_MAX_CONCURRENT_ROLES', value: string(azureMaxConcurrentRoles) }
            { name: 'MDT_AZURE_REQUEST_INTERVAL_SECONDS', value: string(azureRequestIntervalSeconds) }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'applicationinsights-connection-string' }
            { name: 'OTEL_SERVICE_NAME', value: 'mdt-observatory' }
          ]
          probes: bootstrap ? [] : [
            {
              type: 'Startup'
              httpGet: { path: '/healthz', port: 8000 }
              initialDelaySeconds: 1
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 10
            }
            {
              type: 'Liveness'
              httpGet: { path: '/healthz', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/readyz', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    blobDnsLink
    blobDnsGroup
  ]
}

output registryName string = registry.name
output registryEndpoint string = registry.properties.loginServer
output appName string = app.name
output principalId string = app.identity.principalId
output fqdn string = app.properties.configuration.ingress.fqdn
output environmentId string = environment.id
output workspaceId string = workspace.properties.customerId
output insightsName string = insights.name
output storageName string = storage.name
output blobContainerName string = stateContainer.name
output blobAccountUrl string = 'https://${storage.name}.blob.${az.environment().suffixes.storage}'
output vnetId string = vnet.id
output blobPrivateEndpointId string = blobEndpoint.id
