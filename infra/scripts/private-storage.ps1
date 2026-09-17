function Assert-PrivateBlobInfrastructure {
    param(
        [Parameter(Mandatory)][scriptblock] $ReadAzure,
        [Parameter(Mandatory)][string] $SubscriptionId,
        [Parameter(Mandatory)][string] $ResourceGroup
    )
    $scope = "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers"
    $storageId = "$scope/Microsoft.Storage/storageAccounts/stmdtgy76frdpub6io"
    $vnetId = "$scope/Microsoft.Network/virtualNetworks/vnet-mdt-observatory"
    $zoneId = "$scope/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
    $endpointId = "$scope/Microsoft.Network/privateEndpoints/pe-mdt-observatory-blob"
    $storage = & $ReadAzure -Arguments @(
        'resource', 'show', '--ids', $storageId, '--api-version', '2023-05-01',
        '--query', '{public:properties.publicNetworkAccess,sharedKey:properties.allowSharedKeyAccess,firewall:properties.networkAcls.defaultAction,anonymousBlob:properties.allowBlobPublicAccess,httpsOnly:properties.supportsHttpsTrafficOnly}'
    )
    if ($storage.public -ne 'Disabled' -or $storage.sharedKey -ne $false -or
        $storage.firewall -ne 'Deny' -or $storage.anonymousBlob -ne $false -or $storage.httpsOnly -ne $true) {
        throw 'Storage must deny public access, REST Shared Key and anonymous blobs, with HTTPS required.'
    }
    $subnet = & $ReadAzure -Arguments @(
        'resource', 'show', '--ids', "$scope/Microsoft.App/managedEnvironments/cae-mdt-observatory-vnet",
        '--api-version', '2025-01-01', '--query', 'properties.vnetConfiguration.infrastructureSubnetId'
    )
    if ($subnet -ne "$vnetId/subnets/aca") { throw 'Replacement ACA environment is not integrated with the expected subnet.' }
    $endpoint = & $ReadAzure -Arguments @(
        'resource', 'show', '--ids', $endpointId, '--api-version', '2024-05-01',
        '--query', '{subnet:properties.subnet.id,connections:properties.privateLinkServiceConnections}'
    )
    if ($endpoint.subnet -ne "$vnetId/subnets/private-endpoints" -or $endpoint.connections.Count -ne 1) {
        throw 'Blob private endpoint must use the dedicated private-endpoint subnet and one storage connection.'
    }
    $connection = $endpoint.connections[0].properties
    if ($connection.privateLinkServiceId -ne $storageId -or $connection.groupIds.Count -ne 1 -or
        $connection.groupIds[0] -ne 'blob' -or $connection.privateLinkServiceConnectionState.status -ne 'Approved') {
        throw 'Blob private endpoint must be approved for the existing storage account blob subresource.'
    }
    $zones = @(& $ReadAzure -Arguments @(
        'resource', 'show', '--ids', "$endpointId/privateDnsZoneGroups/default",
        '--api-version', '2024-05-01', '--query', 'properties.privateDnsZoneConfigs[].properties.privateDnsZoneId'
    ))
    if ($zones.Count -ne 1 -or $zones[0] -ne $zoneId) { throw 'Blob private endpoint DNS zone group is not configured correctly.' }
    $link = & $ReadAzure -Arguments @(
        'resource', 'show', '--ids', "$zoneId/virtualNetworkLinks/mdt-vnet",
        '--api-version', '2020-06-01',
        '--query', '{vnet:properties.virtualNetwork.id,registration:properties.registrationEnabled,state:properties.virtualNetworkLinkState}'
    )
    if ($link.vnet -ne $vnetId -or $link.registration -ne $false -or $link.state -ne 'Completed') {
        throw 'Blob private DNS zone must have a completed, non-registering link to the application VNet.'
    }
    $publicAccess = & $ReadAzure -Arguments @(
        'resource', 'show', '--ids', "$storageId/blobServices/default/containers/mdt-state",
        '--api-version', '2023-05-01', '--query', 'properties.publicAccess'
    )
    if ($publicAccess -ne 'None') { throw 'The mdt-state Blob container must exist without anonymous access.' }
}
