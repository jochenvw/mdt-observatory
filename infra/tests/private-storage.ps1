#Requires -Version 7.2
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. (Join-Path $root 'infra/scripts/private-storage.ps1')
$subscription = 'e3825c9a-4bce-43e1-899e-1610156c9383'
$group = 'rg-mdt-observatory-demo'
$scope = "/subscriptions/$subscription/resourceGroups/$group/providers"
$storageId = "$scope/Microsoft.Storage/storageAccounts/stmdtgy76frdpub6io"
$vnetId = "$scope/Microsoft.Network/virtualNetworks/vnet-mdt-observatory"
$zoneId = "$scope/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
$endpointId = "$scope/Microsoft.Network/privateEndpoints/pe-mdt-observatory-blob"
$environmentId = "$scope/Microsoft.App/managedEnvironments/cae-mdt-observatory-vnet"
$zoneGroupId = "$endpointId/privateDnsZoneGroups/default"
$linkId = "$zoneId/virtualNetworkLinks/mdt-vnet"
$containerId = "$storageId/blobServices/default/containers/mdt-state"

function Reset-Fixture {
    $script:responses = @{
        $storageId = @{ public = 'Disabled'; sharedKey = $false; firewall = 'Deny'; anonymousBlob = $false; httpsOnly = $true }
        $environmentId = "$vnetId/subnets/aca"
        $endpointId = @{
            subnet = "$vnetId/subnets/private-endpoints"
            connections = @(@{ properties = @{
                privateLinkServiceId = $storageId
                groupIds = @('blob')
                privateLinkServiceConnectionState = @{ status = 'Approved' }
            } })
        }
        $zoneGroupId = @($zoneId)
        $linkId = @{ vnet = $vnetId; registration = $false; state = 'Completed' }
        $containerId = 'None'
    }
    $script:readCount = 0
}
$reader = {
    param([string[]] $Arguments)
    if (($Arguments[0..1] -join ' ') -ne 'resource show') { throw 'Guard must use read-only metadata calls.' }
    $id = $Arguments[[Array]::IndexOf($Arguments, '--ids') + 1]
    if (-not $script:responses.ContainsKey($id)) { throw "Unexpected resource read: $id" }
    $script:readCount++
    return $script:responses[$id]
}
Reset-Fixture
Assert-PrivateBlobInfrastructure -ReadAzure $reader -SubscriptionId $subscription -ResourceGroup $group
if ($script:readCount -ne 6) { throw 'Expected all six private-storage configuration checks.' }

$cases = @(
    @{ Change = { $script:responses[$storageId].public = 'Enabled' }; Error = 'Storage must deny' }
    @{ Change = { $script:responses[$storageId].sharedKey = $true }; Error = 'Storage must deny' }
    @{ Change = { $script:responses[$storageId].firewall = 'Allow' }; Error = 'Storage must deny' }
    @{ Change = { $script:responses[$storageId].anonymousBlob = $true }; Error = 'Storage must deny' }
    @{ Change = { $script:responses[$storageId].httpsOnly = $false }; Error = 'Storage must deny' }
    @{ Change = { $script:responses[$environmentId] = 'wrong-subnet' }; Error = 'not integrated' }
    @{ Change = { $script:responses[$endpointId].subnet = 'wrong-subnet' }; Error = 'dedicated private-endpoint subnet' }
    @{ Change = { $script:responses[$endpointId].connections[0].properties.privateLinkServiceConnectionState.status = 'Pending' }; Error = 'must be approved' }
    @{ Change = { $script:responses[$endpointId].connections[0].properties.groupIds = @('file') }; Error = 'must be approved' }
    @{ Change = { $script:responses[$endpointId].connections[0].properties.privateLinkServiceId = 'wrong-storage' }; Error = 'must be approved' }
    @{ Change = { $script:responses[$zoneGroupId] = @('wrong-zone') }; Error = 'DNS zone group' }
    @{ Change = { $script:responses[$linkId].vnet = 'wrong-vnet' }; Error = 'completed, non-registering link' }
    @{ Change = { $script:responses[$linkId].registration = $true }; Error = 'completed, non-registering link' }
    @{ Change = { $script:responses[$linkId].state = 'InProgress' }; Error = 'completed, non-registering link' }
    @{ Change = { $script:responses[$containerId] = 'Blob' }; Error = 'without anonymous access' }
)
foreach ($case in $cases) {
    Reset-Fixture
    & $case.Change
    try {
        Assert-PrivateBlobInfrastructure -ReadAzure $reader -SubscriptionId $subscription -ResourceGroup $group
        throw 'Expected invalid private-storage configuration to fail.'
    } catch {
        if ($_.Exception.Message -notlike "*$($case.Error)*") { throw }
    }
}
Write-Output 'PASS: private Blob topology and 15 unsafe/incomplete configurations checked without Azure calls.'
