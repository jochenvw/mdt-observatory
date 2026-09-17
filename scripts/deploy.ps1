#Requires -Version 7.2
[CmdletBinding()]
param(
    [ValidateSet('All', 'Bootstrap', 'Build', 'Release', 'Drain')]
    [string] $Stage = 'All',
    [switch] $ValidationApproved,
    [ValidateSet('westeurope', 'swedencentral')]
    [string] $Location = 'westeurope',
    [ValidateSet('e3825c9a-4bce-43e1-899e-1610156c9383')]
    [string] $SubscriptionId = 'e3825c9a-4bce-43e1-899e-1610156c9383',
    [string] $Image,
    # Validate before casting to ARM integers: PowerShell [int] binding rounds fractions.
    [ValidateRange(1, 7)]
    [ValidateScript({ [double]::IsFinite($_) -and $_ -eq [math]::Truncate($_) },
        ErrorMessage = 'AzureMaxConcurrentRoles must be a whole number from 1 to 7.')]
    [double] $AzureMaxConcurrentRoles = 3,
    [ValidateRange(0, 60)]
    [ValidateScript({ [double]::IsFinite($_) -and $_ -eq [math]::Truncate($_) },
        ErrorMessage = 'AzureRequestIntervalSeconds must be a whole number from 0 to 60.')]
    [double] $AzureRequestIntervalSeconds = 20
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$resourceGroup = 'rg-mdt-observatory-demo'
$appName = 'mdt-observatory-vnet'
$legacyAppName = 'mdt-observatory'
$environmentName = 'mdt-observatory-demo'
$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $root 'infra\scripts\private-storage.ps1')
$placeholder = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
$token = $env:MDT_PRESENTER_TOKEN

if (-not $ValidationApproved) {
    throw 'Run azure-validate, then azure-deploy. Pass -ValidationApproved only after those gates.'
}
if ($Stage -notin @('Build', 'Drain') -and ([string]::IsNullOrWhiteSpace($token) -or $token.Length -lt 32 -or $token.Length -gt 512)) {
    throw 'Set MDT_PRESENTER_TOKEN in this process to a random secret of 32 to 512 characters.'
}
if ($Stage -eq 'Release' -and [string]::IsNullOrWhiteSpace($Image)) {
    throw 'Release requires -Image with the immutable ACR digest returned by Build.'
}
if ($Stage -ne 'Release' -and $Image) {
    throw '-Image is accepted only with -Stage Release.'
}
if ($Stage -in @('All', 'Build')) {
    foreach ($file in @('uv.lock', 'README.md', 'frontend\package-lock.json', 'src\mdt\app.py')) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $file) -PathType Leaf)) {
            throw "Build input missing: $file"
        }
    }
}
foreach ($command in @('az')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Required command is missing: $command"
    }
}

function Invoke-Azure {
    param(
        [Parameter(Mandatory)][string[]] $Arguments,
        [switch] $LocalCommand
    )
    if (-not $LocalCommand) { $Arguments += @('--subscription', $SubscriptionId) }
    $result = & az @Arguments --only-show-errors 2>&1
    if ($LASTEXITCODE -ne 0) {
        # ARM errors can contain resource properties. Do not emit raw output or secrets.
        throw "Azure CLI '$($Arguments[0]) $($Arguments[1])' failed (exit $LASTEXITCODE). Inspect the operation in Azure; do not enable debug logging with secrets."
    }
    return ($result -join "`n")
}

function Invoke-Infrastructure {
    param([bool] $Bootstrap, [string] $ContainerImage, [string] $Revision)
    $directory = Join-Path ([IO.Path]::GetTempPath()) ("mdt-deploy-" + [guid]::NewGuid().ToString('N'))
    $parameterFile = Join-Path $directory 'parameters.json'
    [void][IO.Directory]::CreateDirectory($directory)
    try {
        if ($IsWindows) {
            $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
            $acl = [Security.AccessControl.DirectorySecurity]::new()
            $acl.SetAccessRuleProtection($true, $false)
            $acl.SetOwner($sid)
            $rule = [Security.AccessControl.FileSystemAccessRule]::new(
                $sid, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow'
            )
            $acl.AddAccessRule($rule)
            Set-Acl -LiteralPath $directory -AclObject $acl
        } else {
            [IO.File]::SetUnixFileMode($directory, [IO.UnixFileMode]::UserRead -bor
                [IO.UnixFileMode]::UserWrite -bor [IO.UnixFileMode]::UserExecute)
        }
        $parameters = @{
            '$schema' = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'
            contentVersion = '1.0.0.0'
            parameters = @{
                environmentName = @{ value = $environmentName }
                resourceGroupName = @{ value = $resourceGroup }
                location = @{ value = $Location }
                demoToken = @{ value = $token }
                bootstrap = @{ value = $Bootstrap }
                containerImage = @{ value = $ContainerImage }
                revisionSuffix = @{ value = $Revision }
                azureMaxConcurrentRoles = @{ value = [int]$AzureMaxConcurrentRoles }
                azureRequestIntervalSeconds = @{ value = [int]$AzureRequestIntervalSeconds }
            }
        }
        [IO.File]::WriteAllText($parameterFile, ($parameters | ConvertTo-Json -Depth 8))
        $deploymentName = "mdt-$Revision"
        $result = Invoke-Azure @(
            'deployment', 'sub', 'create', '--name', $deploymentName, '--location', $Location,
            '--template-file', (Join-Path $root 'infra\main.bicep'),
            '--parameters', "@$parameterFile", '--query', 'properties.outputs', '--output', 'json'
        )
        return ($result | ConvertFrom-Json)
    } finally {
        if (Test-Path -LiteralPath $parameterFile) { Remove-Item -LiteralPath $parameterFile -Force }
        Remove-Item -LiteralPath $directory -Force
    }
}

function Assert-StorageReady {
    Assert-PrivateBlobInfrastructure -SubscriptionId $SubscriptionId -ResourceGroup $resourceGroup -ReadAzure {
        param([string[]] $Arguments)
        Invoke-Azure -Arguments ($Arguments + @('--output', 'json')) | ConvertFrom-Json
    }
}

function Set-ManualRevisionMode {
    param([string] $TargetAppName = $appName)
    [void](Invoke-Azure @(
        'containerapp', 'revision', 'set-mode', '--name', $TargetAppName,
        '--resource-group', $resourceGroup, '--mode', 'multiple', '--output', 'none'
    ))
    $mode = Invoke-Azure @(
        'containerapp', 'show', '--name', $TargetAppName, '--resource-group', $resourceGroup,
        '--query', 'properties.configuration.activeRevisionsMode', '--output', 'tsv'
    )
    if ($mode -ne 'Multiple') { throw 'Manual revision mode was not applied. Refusing to drain or deploy.' }
}

function Stop-AppRevisions {
    param([string] $TargetAppName = $appName)
    $revisions = @(Invoke-Azure @(
        'containerapp', 'revision', 'list', '--name', $TargetAppName, '--resource-group', $resourceGroup,
        '--query', '[].{name:name,active:properties.active}', '--output', 'json'
    ) | ConvertFrom-Json)
    foreach ($revision in $revisions) {
        if ($revision.active) {
            [void](Invoke-Azure @(
                'containerapp', 'revision', 'deactivate', '--name', $TargetAppName,
                '--resource-group', $resourceGroup, '--revision', $revision.name, '--output', 'none'
            ))
        }
    }
    # Multiple mode prevents Single mode from reviving the previous ready revision.
    $deadline = [DateTime]::UtcNow.AddMinutes(5)
    do {
        $remaining = 0
        foreach ($revision in $revisions) {
            $replicas = @(Invoke-Azure @(
                'containerapp', 'replica', 'list', '--name', $TargetAppName,
                '--resource-group', $resourceGroup, '--revision', $revision.name, '--output', 'json'
            ) | ConvertFrom-Json)
            $remaining += $replicas.Count
        }
        if ($remaining -eq 0) {
            $active = @(Invoke-Azure @(
                'containerapp', 'revision', 'list', '--name', $TargetAppName, '--resource-group', $resourceGroup,
                '--query', '[?properties.active].name', '--output', 'json'
            ) | ConvertFrom-Json)
            if ($active.Count -ne 0) { throw 'A revision reactivated during drain. Refusing to deploy another state writer.' }
            return
        }
        if ([DateTime]::UtcNow -ge $deadline) {
            throw 'Old replicas did not stop within five minutes. Release aborted to protect persisted state.'
        }
        Start-Sleep -Seconds 5
    } while ($true)
}

function Complete-Release {
    param([string] $RevisionName)
    $revisions = @(Invoke-Azure @(
        'containerapp', 'revision', 'list', '--name', $appName, '--resource-group', $resourceGroup,
        '--query', '[].{name:name,active:properties.active}', '--output', 'json'
    ) | ConvertFrom-Json)
    $target = @($revisions | Where-Object name -EQ $RevisionName)
    if ($target.Count -ne 1) { throw 'Expected release revision was not created.' }
    foreach ($old in $revisions | Where-Object name -NE $RevisionName) {
        $replicas = @(Invoke-Azure @(
            'containerapp', 'replica', 'list', '--name', $appName,
            '--resource-group', $resourceGroup, '--revision', $old.name, '--output', 'json'
        ) | ConvertFrom-Json)
        if ($old.active -or $replicas.Count -ne 0) {
            Stop-AppRevisions
            throw 'An old revision returned during release. All revisions stopped; investigate before restarting the state writer.'
        }
    }
    if (-not $target[0].active) {
        [void](Invoke-Azure @(
            'containerapp', 'revision', 'activate', '--name', $appName,
            '--resource-group', $resourceGroup, '--revision', $RevisionName, '--output', 'none'
        ))
    }
    [void](Invoke-Azure @(
        'containerapp', 'ingress', 'traffic', 'set', '--name', $appName,
        '--resource-group', $resourceGroup, '--revision-weight', "$RevisionName=100", '--output', 'none'
    ))
}

Push-Location $root
try {
    [void](Invoke-Azure @('account', 'show', '--output', 'none'))
    [void](Invoke-Azure -Arguments @('extension', 'show', '--name', 'containerapp', '--output', 'none') -LocalCommand)
    $exists = (Invoke-Azure @('group', 'exists', '--name', $resourceGroup, '--output', 'json')) |
        ConvertFrom-Json
    $app = $null
    $apps = @()
    if ($exists) {
        $group = Invoke-Azure @('group', 'show', '--name', $resourceGroup, '--output', 'json') |
            ConvertFrom-Json
        if ($null -eq $group.tags -or $group.tags.'azd-env-name' -ne $environmentName) {
            throw 'The target resource group is not tagged for this demo. Refusing to modify it.'
        }
        if ($group.location -ne $Location) {
            throw "Existing demo uses $($group.location). Re-run with that -Location; do not relocate state."
        }
        $apps = @(Invoke-Azure @(
            'resource', 'list', '--resource-group', $resourceGroup,
            '--resource-type', 'Microsoft.App/containerApps', '--output', 'json'
        ) | ConvertFrom-Json)
        if (@($apps | Where-Object { $_.name -notin @($appName, $legacyAppName) }).Count -gt 0) {
            throw 'Unexpected Container Apps exist in the demo resource group. Refusing to proceed.'
        }
        if (@($apps | Where-Object name -EQ $appName).Count -eq 1) {
            $app = Invoke-Azure @(
                'containerapp', 'show', '--name', $appName, '--resource-group', $resourceGroup,
                '--output', 'json'
            ) | ConvertFrom-Json
        }
    }

    if ($Stage -eq 'Drain') {
        if ($apps.Count -eq 0) { throw 'Cannot drain applications that do not exist.' }
        foreach ($target in @($legacyAppName, $appName)) {
            if (@($apps | Where-Object name -EQ $target).Count -eq 1) {
                Set-ManualRevisionMode -TargetAppName $target
                Stop-AppRevisions -TargetAppName $target
            }
        }
        Write-Output 'Legacy and replacement apps, where present, are in manual mode with no active revisions or replicas.'
        return
    }

    $needsBootstrap = $null -eq $app -or $app.properties.template.containers[0].image -eq $placeholder
    if ($Stage -eq 'Bootstrap' -and -not $needsBootstrap) {
        throw 'A real application already exists. Bootstrap would replace it; use All or Build/Release.'
    }
    if ($needsBootstrap -and $Stage -in @('All', 'Bootstrap')) {
        if (@($apps | Where-Object name -EQ $legacyAppName).Count -eq 1) {
            Set-ManualRevisionMode -TargetAppName $legacyAppName
            Stop-AppRevisions -TargetAppName $legacyAppName
        }
        Write-Host 'Stage 1: bootstrap replacement VNet app, private Blob connectivity and new-identity roles; retain legacy resources.'
        $outputs = Invoke-Infrastructure -Bootstrap $true -ContainerImage $placeholder -Revision 'bootstrap'
        if ($Stage -eq 'Bootstrap') {
            $outputs | ConvertTo-Json -Depth 5
            return
        }
    } elseif ($null -eq $app) {
        throw 'Bootstrap infrastructure before Build or Release.'
    }

    $registries = @(Invoke-Azure @(
        'acr', 'list', '--resource-group', $resourceGroup, '--output', 'json'
    ) | ConvertFrom-Json)
    if ($registries.Count -ne 1 -or $registries[0].adminUserEnabled) {
        throw 'Expected exactly one demo registry with admin credentials disabled.'
    }
    $registry = $registries[0]
    $revision = 'r' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmss') + '-' +
        [guid]::NewGuid().ToString('N').Substring(0, 6)

    if ($Stage -in @('All', 'Build')) {
        Write-Host 'Stage 2: build the locked application remotely with ACR Tasks; no local Docker engine.'
        $tag = "mdt-observatory:$revision"
        [void](Invoke-Azure @(
            'acr', 'build', '--registry', $registry.name, '--image', $tag,
            '--file', 'Dockerfile', '--platform', 'linux/amd64', '--no-logs', '--output', 'none', '.'
        ))
        $digest = Invoke-Azure @(
            'acr', 'repository', 'show', '--name', $registry.name, '--image', $tag,
            '--query', 'digest', '--output', 'tsv'
        )
        $Image = "$($registry.loginServer)/mdt-observatory@$digest"
    }
    $imagePattern = '^' + [regex]::Escape($registry.loginServer) + '/mdt-observatory@sha256:[a-f0-9]{64}$'
    if ($Image -cnotmatch $imagePattern) {
        throw 'Only an immutable mdt-observatory image digest in this demo registry may be released.'
    }
    if ($Stage -eq 'Build') {
        Write-Output $Image
        return
    }
    # Verify the requested digest exists before taking down the current application.
    [void](Invoke-Azure @(
        'acr', 'repository', 'show', '--name', $registry.name,
        '--image', $Image.Substring($registry.loginServer.Length + 1), '--output', 'none'
    ))
    Assert-StorageReady
    Write-Host 'Stage 3: manual revision mode; drain all old writers, then release with explicit traffic.'
    if (@($apps | Where-Object name -EQ $legacyAppName).Count -eq 1) {
        Set-ManualRevisionMode -TargetAppName $legacyAppName
        Stop-AppRevisions -TargetAppName $legacyAppName
    }
    Set-ManualRevisionMode
    Stop-AppRevisions
    $outputs = Invoke-Infrastructure -Bootstrap $false -ContainerImage $Image -Revision $revision
    Complete-Release -RevisionName "$appName--$revision"
    Write-Host 'Stage 4: verify TLS, health, readiness, revision and replica configuration.'
    & (Join-Path $PSScriptRoot 'verify-azure.ps1') -SubscriptionId $SubscriptionId
    $outputs | ConvertTo-Json -Depth 5
} finally {
    Pop-Location
}
