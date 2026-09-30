#Requires -Version 7.2
[CmdletBinding()]
param(
    [ValidateSet('e3825c9a-4bce-43e1-899e-1610156c9383')]
    [string] $SubscriptionId = 'e3825c9a-4bce-43e1-899e-1610156c9383',
    [ValidateRange(10, 1800)]
    [int] $TimeoutSeconds = 300
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$resourceGroup = 'rg-mdt-observatory-demo'
$appName = 'mdt-observatory-vnet'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'infra\scripts\private-storage.ps1')

function Read-Azure {
    param([string[]] $Arguments)
    $result = & az @Arguments --subscription $SubscriptionId --only-show-errors --output json 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Azure read '$($Arguments[0]) $($Arguments[1])' failed (exit $LASTEXITCODE)."
    }
    return (($result -join "`n") | ConvertFrom-Json)
}

$app = Read-Azure @('containerapp', 'show', '--name', $appName, '--resource-group', $resourceGroup)
Assert-PrivateBlobInfrastructure -SubscriptionId $SubscriptionId -ResourceGroup $resourceGroup -ReadAzure {
    param([string[]] $Arguments)
    Read-Azure -Arguments $Arguments
}
if ($app.properties.environmentId -notlike '*/managedEnvironments/cae-mdt-observatory-vnet') {
    throw 'The replacement app must run in the VNet-integrated environment.'
}
$config = $app.properties.configuration
$template = $app.properties.template
if ($config.activeRevisionsMode -ne 'Multiple' -or $template.scale.minReplicas -ne 1 -or
    $template.scale.maxReplicas -ne 1 -or $template.containers.Count -ne 1) {
    throw 'Expected one container with manual Multiple revision mode and min=max=1 replicas.'
}
if (-not $config.ingress.external -or $config.ingress.allowInsecure -or $config.ingress.targetPort -ne 8000) {
    throw 'Expected external TLS-only ingress on target port 8000.'
}
$traffic = @($config.ingress.traffic | Where-Object weight -GT 0)
if ($traffic.Count -ne 1 -or $traffic[0].weight -ne 100 -or
    ('latestRevision' -in $traffic[0].PSObject.Properties.Name -and $traffic[0].latestRevision -eq $true) -or
    'revisionName' -notin $traffic[0].PSObject.Properties.Name -or
    $traffic[0].revisionName -ne $app.properties.latestRevisionName) {
    throw 'All traffic must explicitly target the latest named release, without automatic latest-revision fallback.'
}
if ($app.identity.type -ne 'SystemAssigned' -or $config.registries.Count -ne 1 -or
    $config.registries[0].identity -ne 'system') {
    throw 'Expected system-managed identity for private registry pulls.'
}
$container = $template.containers[0]
foreach ($probe in @(@('Liveness', '/healthz'), @('Readiness', '/readyz'), @('Startup', '/healthz'))) {
    $found = @($container.probes | Where-Object { $_.type -eq $probe[0] -and $_.httpGet.path -eq $probe[1] })
    if ($found.Count -ne 1) { throw "Missing $($probe[0]) health probe." }
}
$environment = @{}
foreach ($entry in $container.env) { $environment[$entry.name] = $entry }
if ($environment['MDT_STORAGE_BACKEND'].value -ne 'azure_blob' -or
    $environment['MDT_BLOB_ACCOUNT_URL'].value -ne 'https://stmdtgy76frdpub6io.blob.core.windows.net' -or
    $environment['MDT_BLOB_CONTAINER'].value -ne 'mdt-state' -or
    $environment['MDT_SECURE_COOKIE'].value -ne 'true' -or
    $environment['MDT_PRESENTER_TOKEN'].secretRef -ne 'presenter-token' -or
    $environment['APPLICATIONINSIGHTS_CONNECTION_STRING'].secretRef -ne 'applicationinsights-connection-string') {
    throw 'Missing managed-identity Blob backend, secure cookie or secret-reference configuration.'
}
foreach ($property in @($container.PSObject.Properties['volumeMounts'], $template.PSObject.Properties['volumes'])) {
    if ($null -ne $property -and $null -ne $property.Value -and @($property.Value).Count -gt 0) {
        throw 'The Blob-backed cloud app must not mount file storage.'
    }
}
if (@($config.secrets | Where-Object name -NotIn @('presenter-token', 'applicationinsights-connection-string')).Count -ne 0) {
    throw 'Unexpected app secret; storage account keys must not be configured.'
}
$fqdn = $config.ingress.fqdn
if ($fqdn -notmatch '^[a-z0-9.-]+\.azurecontainerapps\.io$') {
    throw 'Refusing HTTP checks against an unexpected Container Apps hostname.'
}
$baseUrl = "https://$fqdn"
$handler = [Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $false
$client = [Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds(15)
try {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $ready = $true
        foreach ($path in @('/healthz', '/readyz')) {
            try {
                $response = $client.GetAsync("$baseUrl$path").GetAwaiter().GetResult()
                try { $ready = $ready -and [int]$response.StatusCode -eq 200 }
                finally { $response.Dispose() }
            } catch [Net.Http.HttpRequestException] {
                Write-Warning "Waiting for HTTPS connectivity at $path."
                $ready = $false
            } catch [OperationCanceledException] {
                Write-Warning "Health request timed out at $path."
                $ready = $false
            }
        }
        if ($ready) { break }
        if ([DateTime]::UtcNow -ge $deadline) { throw 'TLS health/readiness did not return HTTP 200 before timeout.' }
        Start-Sleep -Seconds 5
    } while ($true)
    $response = $client.GetAsync("$baseUrl/").GetAwaiter().GetResult()
    try {
        if ([int]$response.StatusCode -ne 200 -or
            $response.Content.Headers.ContentType.MediaType -ne 'text/html') {
            throw 'The compiled frontend did not return HTML at /.'
        }
    } finally { $response.Dispose() }

    $response = $client.GetAsync("$baseUrl/api/config").GetAwaiter().GetResult()
    try {
        if ([int]$response.StatusCode -ne 200) { throw 'Public configuration endpoint failed.' }
        $publicConfig = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
        if (-not $publicConfig.auth_required -or 'azure' -notin $publicConfig.modes -or $publicConfig.presenter) {
            throw 'Cloud configuration must require presenter authentication, offer Azure mode and not treat anonymous clients as presenters.'
        }
    } finally { $response.Dispose() }
    # Participants follow the room anonymously; case selection, orchestration and exports stay presenter-only.
    $response = $client.GetAsync("$baseUrl/api/meeting").GetAwaiter().GetResult()
    try {
        if ([int]$response.StatusCode -ne 200) { throw 'Anonymous participants could not read the shared meeting room.' }
    } finally { $response.Dispose() }
    foreach ($path in @('/api/cases', '/api/meetings/verification-missing/export')) {
        $response = $client.GetAsync("$baseUrl$path").GetAwaiter().GetResult()
        try {
            if ([int]$response.StatusCode -ne 401) { throw "Anonymous presenter-only access was not rejected at $path." }
        } finally { $response.Dispose() }
    }
    if (-not [string]::IsNullOrWhiteSpace($env:MDT_PRESENTER_TOKEN)) {
        $payload = @{ token = $env:MDT_PRESENTER_TOKEN } | ConvertTo-Json -Compress
        $body = [Net.Http.StringContent]::new($payload, [Text.Encoding]::UTF8, 'application/json')
        try {
            $response = $client.PostAsync("$baseUrl/api/auth", $body).GetAwaiter().GetResult()
            try {
                if ([int]$response.StatusCode -ne 200) { throw 'Presenter authentication failed.' }
                $cookies = $response.Headers.GetValues('Set-Cookie') -join ';'
                if ($cookies -notmatch 'mdt_presenter=' -or $cookies -notmatch '(?i);\s*httponly' -or
                    $cookies -notmatch '(?i);\s*secure' -or $cookies -notmatch '(?i)samesite=strict') {
                    throw 'Presenter cookie must be HttpOnly, Secure and SameSite=Strict.'
                }
            } finally { $response.Dispose() }
        } finally { $body.Dispose() }
        $response = $client.GetAsync("$baseUrl/api/meeting").GetAwaiter().GetResult()
        try {
            if ([int]$response.StatusCode -ne 200) { throw 'Authenticated read failed.' }
        } finally { $response.Dispose() }
    } else {
        Write-Warning 'MDT_PRESENTER_TOKEN not provided: authenticated cookie/read checks were skipped.'
    }
} finally {
    $client.Dispose()
    $handler.Dispose()
}

$allRevisions = @(Read-Azure @(
    'containerapp', 'revision', 'list', '--name', $appName, '--resource-group', $resourceGroup,
    '--query', '[].{name:name,properties:{active:properties.active,healthState:properties.healthState}}'
))
$revisions = @($allRevisions | Where-Object { $_.properties.active })
if ($revisions.Count -ne 1 -or $revisions[0].properties.healthState -ne 'Healthy') {
    throw 'Expected exactly one healthy active revision.'
}
if ($revisions[0].name -ne $app.properties.latestRevisionName) {
    throw 'The healthy active revision is not the latest release.'
}
foreach ($old in $allRevisions | Where-Object { -not $_.properties.active }) {
    $oldReplicas = @(Read-Azure @(
        'containerapp', 'replica', 'list', '--name', $appName,
        '--resource-group', $resourceGroup, '--revision', $old.name
    ))
    if ($oldReplicas.Count -ne 0) { throw 'An inactive revision still has replicas; exclusive state access is not verified.' }
}
$replicas = @(Read-Azure @(
    'containerapp', 'replica', 'list', '--name', $appName,
    '--resource-group', $resourceGroup, '--revision', $revisions[0].name
))
if ($replicas.Count -ne 1) { throw 'Expected exactly one running replica.' }
$legacy = @(Read-Azure @(
    'resource', 'list', '--resource-group', $resourceGroup, '--resource-type', 'Microsoft.App/containerApps',
    '--query', "[?name=='mdt-observatory'].name"
))
if ($legacy.Count -eq 1) {
    $legacyRevisions = @(Read-Azure @(
        'containerapp', 'revision', 'list', '--name', 'mdt-observatory', '--resource-group', $resourceGroup,
        '--query', '[].{name:name,active:properties.active}'
    ))
    foreach ($old in $legacyRevisions) {
        if ($old.active) { throw 'The legacy app must remain drained after migration.' }
        $oldReplicas = @(Read-Azure @(
            'containerapp', 'replica', 'list', '--name', 'mdt-observatory', '--resource-group', $resourceGroup,
            '--revision', $old.name
        ))
        if ($oldReplicas.Count -ne 0) { throw 'The legacy app still has replicas after migration.' }
    }
}
Write-Output "Verified $baseUrl (TLS, health, readiness, frontend, protected API, private Blob metadata, no file mounts, one active replica, legacy app drained)."
Write-Output 'Application workflow, restart persistence and telemetry ingestion require the separate acceptance walkthrough.'
