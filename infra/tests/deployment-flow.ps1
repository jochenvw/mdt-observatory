#Requires -Version 7.2
param([string] $CompiledTemplatePath)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$scriptPath = Join-Path $root 'scripts\deploy.ps1'
$originalToken = $env:MDT_PRESENTER_TOKEN
$global:Mock = @{}

function Reset-Mock {
    $global:Mock = @{
        Calls = [Collections.Generic.List[string]]::new()
        Exists = $true
        Live = $true
        Owned = $true
        FailBuild = $false
        FailRelease = $false
        Stopped = $false
        Manual = $false
        CurrentExists = $true
        LegacyExists = $true
        DrainedApps = [Collections.Generic.HashSet[string]]::new()
        ParameterFiles = [Collections.Generic.List[string]]::new()
        ExpectedRoles = 3
        ExpectedInterval = 20
    }
}
function Assert-True([bool] $Condition, [string] $Message) {
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}
function Expect-Failure([scriptblock] $Action, [string] $Message) {
    try { & $Action; throw 'Expected failure was not raised.' }
    catch {
        if ($_.Exception.Message -notlike "*$Message*") { throw }
    }
}
function global:az {
    $a = @($args)
    $text = $a -join ' '
    $global:Mock.Calls.Add($text)
    $global:LASTEXITCODE = 0
    if ($text.StartsWith('extension show')) {
        Assert-True (-not ($a -contains '--subscription')) 'Local extension lookup must omit subscription.'
        return
    }
    if ($text.StartsWith('account show')) { return }
    if ($text.StartsWith('group exists')) { return ($global:Mock.Exists | ConvertTo-Json) }
    if ($text.StartsWith('group show')) {
        $name = if ($global:Mock.Owned) { 'mdt-observatory-demo' } else { 'other-project' }
        return (@{ location = 'westeurope'; tags = @{ 'azd-env-name' = $name } } | ConvertTo-Json)
    }
    if ($text.StartsWith('resource list')) {
        $apps = @()
        if ($global:Mock.LegacyExists) { $apps += @{ name = 'mdt-observatory' } }
        if ($global:Mock.CurrentExists) { $apps += @{ name = 'mdt-observatory-vnet' } }
        return (ConvertTo-Json -InputObject $apps)
    }
    if ($text.StartsWith('resource show')) {
        $scope = '/subscriptions/e3825c9a-4bce-43e1-899e-1610156c9383/resourceGroups/rg-mdt-observatory-demo/providers'
        $storage = "$scope/Microsoft.Storage/storageAccounts/stmdtgy76frdpub6io"
        $vnet = "$scope/Microsoft.Network/virtualNetworks/vnet-mdt-observatory"
        $zone = "$scope/Microsoft.Network/privateDnsZones/privatelink.blob.core.windows.net"
        if ($text.Contains('/containers/mdt-state')) { return '"None"' }
        if ($text.Contains('/privateDnsZoneGroups/default')) { return (ConvertTo-Json -InputObject @($zone)) }
        if ($text.Contains('/virtualNetworkLinks/mdt-vnet')) {
            return (@{ vnet = $vnet; registration = $false; state = 'Completed' } | ConvertTo-Json)
        }
        if ($text.Contains('/privateEndpoints/')) {
            return (@{ subnet = "$vnet/subnets/private-endpoints"; connections = @(@{
                properties = @{ privateLinkServiceId = $storage; groupIds = @('blob')
                    privateLinkServiceConnectionState = @{ status = 'Approved' } }
            }) } | ConvertTo-Json -Depth 8)
        }
        if ($text.Contains('/managedEnvironments/')) { return (ConvertTo-Json -InputObject "$vnet/subnets/aca") }
        return '{"public":"Disabled","sharedKey":false,"firewall":"Deny","anonymousBlob":false,"httpsOnly":true}'
    }
    if ($text.StartsWith('containerapp revision set-mode')) {
        $global:Mock.Manual = $true
        return
    }
    if ($text.StartsWith('containerapp show')) {
        if ($text.Contains('--query properties.configuration.activeRevisionsMode')) { return 'Multiple' }
        $image = if ($global:Mock.Live) { 'acrtest.azurecr.io/mdt-observatory@sha256:old' }
        else { 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' }
        return (@{ properties = @{ template = @{ containers = @(@{ image = $image }) } } } |
            ConvertTo-Json -Depth 8)
    }
    if ($text.StartsWith('acr list')) {
        return '[{"name":"acrtest","loginServer":"acrtest.azurecr.io","adminUserEnabled":false}]'
    }
    if ($text.StartsWith('acr build')) {
        Assert-True ($text.Contains('--platform linux/amd64')) 'Build must target Linux AMD64.'
        Assert-True ($text.Contains('--no-logs')) 'Build must not stream logs.'
        if ($global:Mock.FailBuild) { $global:LASTEXITCODE = 1; return 'simulated build failure' }
        return
    }
    if ($text.StartsWith('acr repository show')) {
        if ($text.Contains('--query digest')) { return ('sha256:' + ('a' * 64)) }
        return
    }
    if ($text.StartsWith('containerapp revision list')) {
        $target = $a[[Array]::IndexOf($a, '--name') + 1]
        if ($text.Contains('[?properties.active].name')) {
            Assert-True ($global:Mock.DrainedApps.Contains($target)) 'Final drain check must follow target deactivation.'
            return '[]'
        }
        return (@(@{ name = "$target--old"; active = $true }, @{ name = "$target--inactive"; active = $false }) |
            ConvertTo-Json)
    }
    if ($text.StartsWith('containerapp revision deactivate')) {
        $global:Mock.Stopped = $true
        [void]$global:Mock.DrainedApps.Add($a[[Array]::IndexOf($a, '--name') + 1])
        return
    }
    if ($text.StartsWith('containerapp replica list')) {
        Assert-True $global:Mock.Stopped 'Replica drain must follow deactivation.'
        return '[]'
    }
    if ($text.StartsWith('deployment sub create')) {
        $index = [Array]::IndexOf($a, '--parameters')
        $file = $a[$index + 1].Substring(1)
        $global:Mock.ParameterFiles.Add($file)
        $parameters = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json
        foreach ($setting in @(
            @{ Name = 'azureMaxConcurrentRoles'; Expected = $global:Mock.ExpectedRoles },
            @{ Name = 'azureRequestIntervalSeconds'; Expected = $global:Mock.ExpectedInterval }
        )) {
            $value = $parameters.parameters.($setting.Name).value
            Assert-True ($value -is [int] -or $value -is [long]) "$($setting.Name) must serialize as an ARM integer."
            Assert-True ($value -eq $setting.Expected) "$($setting.Name) must preserve the requested value or default."
        }
        Assert-True ($parameters.parameters.demoToken.value -ceq $env:MDT_PRESENTER_TOKEN) 'Secure parameter must carry the environment token.'
        Assert-True (-not $text.Contains($env:MDT_PRESENTER_TOKEN)) 'Secret must not be a process argument.'
        if ($IsWindows) {
            $acl = Get-Acl -LiteralPath (Split-Path $file -Parent)
            Assert-True $acl.AreAccessRulesProtected 'Temporary directory must disable inherited permissions.'
            Assert-True ($acl.Access.Count -eq 1) 'Temporary directory should grant only its owner access.'
        } else {
            $mode = [IO.File]::GetUnixFileMode((Split-Path $file -Parent))
            Assert-True (([int]$mode -band 63) -eq 0) 'Temporary directory must exclude group/other permissions.'
        }
        if ($global:Mock.Exists -and $global:Mock.LegacyExists) {
            Assert-True ($global:Mock.DrainedApps.Contains('mdt-observatory')) 'Legacy app must be drained before bootstrap or release.'
        }
        if (-not $parameters.parameters.bootstrap.value) {
            Assert-True $global:Mock.Manual 'Release must switch to manual mode before draining.'
            Assert-True $global:Mock.Stopped 'Release must stop old replicas first.'
            Assert-True ($parameters.parameters.containerImage.value -match '@sha256:') 'Release requires a digest.'
            if ($global:Mock.FailRelease) {
                $global:LASTEXITCODE = 1
                return ('untrusted error containing ' + $env:MDT_PRESENTER_TOKEN)
            }
            throw 'Success release is not mocked: it would enter live HTTP verification.'
        }
        return '{"AZURE_RESOURCE_GROUP":{"value":"rg-mdt-observatory-demo"}}'
    }
    throw "Unexpected Azure command in isolated test: $text"
}

try {
    if ($CompiledTemplatePath) {
        $armJson = Get-Content -LiteralPath $CompiledTemplatePath -Raw
        $arm = $armJson | ConvertFrom-Json
        $module = $arm.resources | Where-Object name -EQ 'mdt-resources'
        $template = $module.properties.template
        $app = $template.resources | Where-Object type -EQ 'Microsoft.App/containerApps'
        $environment = $app.properties.template.containers[0].env
        foreach ($setting in @(
            @{ Name = 'azureMaxConcurrentRoles'; Env = 'MDT_AZURE_MAX_CONCURRENT_ROLES'; Default = 3; Min = 1; Max = 7 },
            @{ Name = 'azureRequestIntervalSeconds'; Env = 'MDT_AZURE_REQUEST_INTERVAL_SECONDS'; Default = 20; Min = 0; Max = 60 }
        )) {
            foreach ($parameters in @($arm.parameters, $template.parameters)) {
                $parameter = $parameters.($setting.Name)
                Assert-True ($parameter.type -eq 'int') "$($setting.Name) must be an integer at both Bicep boundaries."
                Assert-True ($parameter.defaultValue -eq $setting.Default) "$($setting.Name) must retain its reproducible default."
                Assert-True ($parameter.minValue -eq $setting.Min -and $parameter.maxValue -eq $setting.Max) "$($setting.Name) must enforce exact bounds."
            }
            Assert-True ($module.properties.parameters.($setting.Name).value -ceq "[parameters('$($setting.Name)')]") 'Root must forward each scheduling parameter unchanged.'
            Assert-True ($environment.Contains("createObject('name', '$($setting.Env)', 'value', string(parameters('$($setting.Name)')))")) 'ACA must receive each scheduling value as a string.'
        }
        Assert-True ($environment.StartsWith("[if(parameters('bootstrap'), createArray(),")) 'Bootstrap must retain an empty environment.'
        Assert-True ($app.properties.configuration.activeRevisionsMode -eq 'Multiple') 'Manual revision control must remain enabled.'
        Assert-True ($app.properties.template.scale.minReplicas -eq 1 -and $app.properties.template.scale.maxReplicas -eq 1) 'Role concurrency must not change single-replica scaling.'
        Assert-True ($app.properties.template.PSObject.Properties.Name -notcontains 'volumes') 'Blob app must not introduce storage volumes.'
        Assert-True ($app.properties.template.containers[0].PSObject.Properties.Name -notcontains 'volumeMounts') 'Blob app must not introduce mounts.'
        Assert-True ($armJson -notmatch '"type"\s*:\s*"Microsoft.CognitiveServices/accounts') 'Templates must not create or modify shared model accounts/deployments.'
        Write-Output 'PASS: compiled scheduling bounds/defaults, module/environment forwarding, and unchanged single-writer/model boundaries.'
    }

    Reset-Mock
    Expect-Failure { & $scriptPath -Stage Bootstrap } 'Run azure-validate'
    Assert-True ($global:Mock.Calls.Count -eq 0) 'Missing gate must not call Azure.'

    $env:MDT_PRESENTER_TOKEN = ''
    Expect-Failure { & $scriptPath -Stage Bootstrap -ValidationApproved } '32 to 512'
    Assert-True ($global:Mock.Calls.Count -eq 0) 'Missing secret must not call Azure.'

    $env:MDT_PRESENTER_TOKEN = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    Reset-Mock
    $global:Mock.Exists = $false
    $output = & $scriptPath -Stage Bootstrap -ValidationApproved
    Assert-True (($output | ConvertFrom-Json).AZURE_RESOURCE_GROUP.value -eq 'rg-mdt-observatory-demo') 'Bootstrap returns nonsecret outputs.'
    foreach ($file in $global:Mock.ParameterFiles) {
        Assert-True (-not (Test-Path $file)) 'Secure parameter file must be cleaned up after success.'
        Assert-True (-not (Test-Path (Split-Path $file -Parent))) 'Secure directory must be cleaned up.'
    }

    Reset-Mock
    $global:Mock.CurrentExists = $false
    $output = & $scriptPath -Stage Bootstrap -ValidationApproved
    Assert-True ($global:Mock.DrainedApps.Contains('mdt-observatory')) 'Migration bootstrap drains the legacy app.'
    Assert-True (-not ($global:Mock.Calls -match '\bdelete\b')) 'Migration must not delete resources.'

    Reset-Mock
    Expect-Failure { & $scriptPath -Stage Bootstrap -ValidationApproved } 'A real application already exists'
    Assert-True (-not ($global:Mock.Calls -match '^deployment')) 'Bootstrap cannot replace an existing app.'

    Reset-Mock
    $global:Mock.Owned = $false
    Expect-Failure { & $scriptPath -Stage All -ValidationApproved } 'not tagged for this demo'
    Assert-True (-not ($global:Mock.Calls -match '^deployment')) 'Unowned group must not be changed.'

    Reset-Mock
    $env:MDT_PRESENTER_TOKEN = ''
    $output = & $scriptPath -Stage Drain -ValidationApproved
    Assert-True $global:Mock.Manual 'Drain must switch to manual revision mode.'
    Assert-True $global:Mock.Stopped 'Drain must stop old replicas.'
    Assert-True ($global:Mock.DrainedApps.Count -eq 2) 'Drain must stop legacy and replacement apps.'
    Assert-True (-not ($global:Mock.Calls -match '^deployment|^storage account')) 'Drain must not deploy or change storage.'

    Reset-Mock
    $output = & $scriptPath -Stage Build -ValidationApproved
    Assert-True ($output -ceq ('acrtest.azurecr.io/mdt-observatory@sha256:' + ('a' * 64))) 'Build returns just one immutable image.'
    Assert-True (-not $global:Mock.Stopped) 'Build must not interrupt the live app.'

    Reset-Mock
    $global:Mock.FailBuild = $true
    Expect-Failure { & $scriptPath -Stage Build -ValidationApproved } 'failed (exit 1)'
    Assert-True (-not $global:Mock.Stopped) 'Build failure must leave the live app running.'

    $env:MDT_PRESENTER_TOKEN = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')
    Reset-Mock
    Expect-Failure { & $scriptPath -Stage Release -Image 'elsewhere.azurecr.io/a:latest' -ValidationApproved } 'Only an immutable'
    Assert-True (-not $global:Mock.Stopped) 'Invalid image must not interrupt the live app.'

    Reset-Mock
    $global:Mock.FailRelease = $true
    $image = 'acrtest.azurecr.io/mdt-observatory@sha256:' + ('a' * 64)
    Expect-Failure { & $scriptPath -Stage Release -Image $image -ValidationApproved } "Azure CLI 'deployment sub'"
    Assert-True $global:Mock.Stopped 'Release failure simulation must exercise the drain gate.'
    Assert-True (@($global:Mock.Calls -match '^containerapp replica list').Count -eq 4) 'Drain must inspect both apps and their inactive revisions.'
    foreach ($file in $global:Mock.ParameterFiles) {
        Assert-True (-not (Test-Path $file)) 'Secure parameter file must be cleaned up after failure.'
    }

    $validSettings = @(
        @{ Stage = 'Bootstrap'; Roles = 1; Interval = 0 },
        @{ Stage = 'Bootstrap'; Roles = 7; Interval = 60 },
        @{ Stage = 'Release'; Roles = 7; Interval = 2 }
    )
    foreach ($setting in $validSettings) {
        Reset-Mock
        $global:Mock.ExpectedRoles = $setting.Roles
        $global:Mock.ExpectedInterval = $setting.Interval
        $arguments = @{
            Stage = $setting.Stage
            ValidationApproved = $true
            AzureMaxConcurrentRoles = $setting.Roles
            AzureRequestIntervalSeconds = $setting.Interval
        }
        if ($setting.Stage -eq 'Bootstrap') {
            $global:Mock.Exists = $false
            $output = & $scriptPath @arguments
            Assert-True (($output | ConvertFrom-Json).AZURE_RESOURCE_GROUP.value -eq 'rg-mdt-observatory-demo') 'Configured bootstrap returns nonsecret outputs.'
        } else {
            $arguments.Image = $image
            $global:Mock.FailRelease = $true
            Expect-Failure { & $scriptPath @arguments } "Azure CLI 'deployment sub'"
            Assert-True $global:Mock.Stopped 'Configured release must still drain old writers.'
        }
        Assert-True ($global:Mock.ParameterFiles.Count -eq 1) 'Each configured invocation must pass parameters to ARM once.'
        foreach ($file in $global:Mock.ParameterFiles) {
            Assert-True (-not (Test-Path $file)) 'Configured invocation must clean up its secure parameter file.'
            Assert-True (-not (Test-Path (Split-Path $file -Parent))) 'Configured invocation must clean up its secure directory.'
        }
    }

    $invalidSettings = @(
        @{ Name = 'AzureMaxConcurrentRoles'; Values = @(0, 8, 1.5, [double]::NaN, [double]::PositiveInfinity, [double]::NegativeInfinity) },
        @{ Name = 'AzureRequestIntervalSeconds'; Values = @(-1, 61, 0.5, [double]::NaN, [double]::PositiveInfinity, [double]::NegativeInfinity) }
    )
    foreach ($setting in $invalidSettings) {
        foreach ($value in $setting.Values) {
            Reset-Mock
            $arguments = @{ Stage = 'Drain'; ValidationApproved = $true; $setting.Name = $value }
            Expect-Failure { & $scriptPath @arguments } $setting.Name
            Assert-True ($global:Mock.Calls.Count -eq 0) 'Invalid scheduling parameters must fail before any Azure call.'
        }
    }
    Write-Output 'PASS: 11 deployment safety scenarios, 3 scheduling overrides and 12 invalid inputs; no real Azure CLI calls.'
} finally {
    $env:MDT_PRESENTER_TOKEN = $originalToken
    Remove-Item Function:\az
}
