#Requires -Version 7.2
[CmdletBinding()]
param([switch] $LiveStorageCheck)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
. (Join-Path $root 'infra\scripts\private-storage.ps1')
$SubscriptionId = 'e3825c9a-4bce-43e1-899e-1610156c9383'
$resourceGroup = 'rg-mdt-observatory-demo'
$appName = 'mdt-observatory-vnet'
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $root 'scripts\deploy.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($name in @('Invoke-Azure', 'Assert-StorageReady', 'Set-ManualRevisionMode', 'Complete-Release')) {
    $helper = $ast.Find({
        param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name
    }, $true)
    if ($null -eq $helper) { throw "Missing helper: $name" }
    . ([scriptblock]::Create($helper.Extent.Text))
}
if ($LiveStorageCheck) {
    # This path only reads storage, VNet integration, endpoint and DNS metadata.
    Assert-StorageReady
    Write-Output 'Private Blob metadata is valid; live managed-identity data access is still required.'
    return
}

function Expect-Failure([scriptblock] $Action, [string] $Message) {
    try { & $Action; throw 'Expected failure was not raised.' }
    catch {
        if ($_.Exception.Message -notlike "*$Message*") { throw }
    }
}
function Reset-State {
    $script:state = @{
        Mode = 'Multiple'
        OldActive = $false; OldReplicas = 0; TargetActive = $true
        Stopped = $false; Activated = $false; Traffic = $false
        Calls = [Collections.Generic.List[string]]::new()
    }
}
function Invoke-Azure([string[]] $Arguments) {
    $command = $Arguments -join ' '
    $script:state.Calls.Add($command)
    if ($command.StartsWith('containerapp revision set-mode')) { return '' }
    if ($command.StartsWith('containerapp show')) { return $script:state.Mode }
    if ($command.StartsWith('containerapp revision list')) {
        return (@(
            @{ name = 'mdt-observatory-vnet--target'; active = $script:state.TargetActive }
            @{ name = 'mdt-observatory-vnet--old'; active = $script:state.OldActive }
        ) | ConvertTo-Json)
    }
    if ($command.StartsWith('containerapp replica list')) {
        if ($script:state.OldReplicas) { return '[{"name":"old-writer"}]' }
        return '[]'
    }
    if ($command.StartsWith('containerapp revision activate')) {
        $script:state.Activated = $true
        return ''
    }
    if ($command.StartsWith('containerapp ingress traffic set')) {
        if ('mdt-observatory-vnet--target=100' -notin $Arguments) { throw 'Traffic must use the explicit target revision.' }
        $script:state.Traffic = $true
        return ''
    }
    throw "Unexpected mocked operation: $command"
}
function Stop-AppRevisions { $script:state.Stopped = $true }

Reset-State
Set-ManualRevisionMode
if ($script:state.Calls[0] -notmatch '--mode multiple') { throw 'Must explicitly set Multiple mode.' }
$script:state.Mode = 'Single'
Expect-Failure { Set-ManualRevisionMode } 'Manual revision mode was not applied'

foreach ($active in @($true, $false)) {
    Reset-State
    $script:state.TargetActive = $active
    Complete-Release -RevisionName 'mdt-observatory-vnet--target'
    if (-not $script:state.Traffic -or $script:state.Activated -eq $active) {
        throw 'Exclusive target must receive traffic and only be activated when needed.'
    }
}
foreach ($conflict in @('OldActive', 'OldReplicas')) {
    Reset-State
    $script:state[$conflict] = 1
    Expect-Failure { Complete-Release -RevisionName 'mdt-observatory-vnet--target' } 'All revisions stopped'
    if (-not $script:state.Stopped -or $script:state.Traffic -or $script:state.Activated) {
        throw 'Unexpected old writers must stop all revisions and block activation/traffic.'
    }
}
Write-Output 'PASS: manual mode, explicit traffic, activation and revived-writer safety checks; no Azure calls.'
