#Requires -Version 7.2
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

function Get-PollLoop([string] $File) {
    $tokens = $null
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseFile(
        (Join-Path $root $File), [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
    $loops = @($ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.DoWhileStatementAst]
    }, $true))
    if ($loops.Count -ne 1) { throw "Update loop coverage for $File; expected one polling loop." }
    return [scriptblock]::Create($loops[0].Extent.Text)
}

function Assert-Equal($Actual, $Expected, [string] $Label) {
    if ($Actual -ne $Expected) { throw "$Label expected $Expected, got $Actual." }
}

function Assert-Timeout([scriptblock] $Loop, [string] $Message) {
    try { & $Loop; throw 'Polling unexpectedly succeeded.' }
    catch {
        if ($_.Exception.Message -notlike "*$Message*") { throw }
    }
}

# Exercise the actual loop bodies with in-memory dependencies; never contact Azure.
function Start-Sleep([int] $Seconds) {
    Assert-Equal $Seconds 5 'Polling delay'
    $script:sleeps++
    if ($script:sleeps -gt 2) { throw 'Polling exceeded the test iteration bound.' }
}

function Invoke-Azure([string[]] $Arguments) {
    if (($Arguments[0..2] -join ' ') -eq 'containerapp revision list') {
        if ($script:reactivated) { return '["old-revived"]' }
        return '[]'
    }
    Assert-Equal ($Arguments[0..2] -join ' ') 'containerapp replica list' 'Drain operation'
    $script:calls++
    if ($script:calls -le $script:busyCalls) { return '[{"name":"old-writer"}]' }
    return '[]'
}

$drain = Get-PollLoop 'scripts\deploy.ps1'
$revisions = @([pscustomobject]@{ name = 'old-active' }, [pscustomobject]@{ name = 'old-inactive' })
$appName = 'test-app'
$TargetAppName = $appName
$resourceGroup = 'test-group'
foreach ($case in @('drained', 'transient', 'timeout', 'reactivated')) {
    $script:calls = 0
    $script:sleeps = 0
    $script:reactivated = $case -eq 'reactivated'
    $script:busyCalls = if ($case -in @('drained', 'reactivated')) { 0 } else { 2 }
    $deadline = if ($case -eq 'timeout') { [DateTime]::UtcNow.AddSeconds(-1) }
        else { [DateTime]::UtcNow.AddSeconds(30) }
    if ($case -eq 'timeout') {
        Assert-Timeout $drain 'Release aborted to protect persisted state'
        Assert-Equal $script:sleeps 0 'Expired drain deadline'
    } elseif ($case -eq 'reactivated') {
        Assert-Timeout $drain 'A revision reactivated during drain'
        Assert-Equal $script:sleeps 0 'Reactivated revision abort'
    } else {
        & $drain
        Assert-Equal $script:sleeps ([int]($case -eq 'transient')) 'Drain retry count'
    }
    Assert-Equal $script:calls $(if ($case -eq 'transient') { 4 } else { 2 }) 'All old revisions checked'
}

Add-Type -TypeDefinition @'
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
public sealed class MdtPollingTestHandler : HttpMessageHandler {
    public int Calls;
    public int Failures;
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token) {
        Calls++;
        return Task.FromResult(new HttpResponseMessage(
            Calls <= Failures ? HttpStatusCode.ServiceUnavailable : HttpStatusCode.OK));
    }
}
'@

$health = Get-PollLoop 'scripts\verify-azure.ps1'
$baseUrl = 'https://test.invalid'
foreach ($case in @('ready', 'transient', 'timeout')) {
    $script:sleeps = 0
    $handler = [MdtPollingTestHandler]::new()
    $handler.Failures = if ($case -eq 'ready') { 0 } else { 2 }
    $client = [Net.Http.HttpClient]::new($handler)
    $deadline = if ($case -eq 'timeout') { [DateTime]::UtcNow.AddSeconds(-1) }
        else { [DateTime]::UtcNow.AddSeconds(30) }
    try {
        if ($case -eq 'timeout') {
            Assert-Timeout $health 'did not return HTTP 200 before timeout'
            Assert-Equal $script:sleeps 0 'Expired health deadline'
        } else {
            & $health
            Assert-Equal $script:sleeps ([int]($case -eq 'transient')) 'Health retry count'
        }
        Assert-Equal $handler.Calls $(if ($case -eq 'transient') { 4 } else { 2 }) 'Both health endpoints checked'
    } finally {
        $client.Dispose()
        $handler.Dispose()
    }
}
Write-Output 'PASS: polling success/retry/timeout and reactivated-writer rejection; no network calls.'
