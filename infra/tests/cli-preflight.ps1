#Requires -Version 7.2
[CmdletBinding()]
param([switch] $Live)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$SubscriptionId = 'e3825c9a-4bce-43e1-899e-1610156c9383'
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $root 'scripts\deploy.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
$helper = $ast.Find({
    param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-Azure'
}, $true)
if ($null -eq $helper) { throw 'Deployment CLI helper not found.' }
. ([scriptblock]::Create($helper.Extent.Text))

if (-not $Live) {
    function az {
        $script:arguments = @($args)
        $global:LASTEXITCODE = 0
        return ''
    }
    [void](Invoke-Azure -Arguments @('extension', 'show', '--name', 'containerapp', '--output', 'none') -LocalCommand)
    if ('--subscription' -in $script:arguments) { throw 'Local extension lookup must not receive --subscription.' }
    if ('--only-show-errors' -notin $script:arguments) { throw 'Local lookup must preserve logging flags.' }
    foreach ($operation in @(
        @('account', 'show'),
        @('group', 'exists', '--name', 'rg-mdt-observatory-demo'),
        @('deployment', 'sub', 'create'),
        @('acr', 'build'),
        @('containerapp', 'show')
    )) {
        [void](Invoke-Azure -Arguments $operation)
        $index = [Array]::IndexOf($script:arguments, '--subscription')
        if ($index -lt 0 -or $script:arguments[$index + 1] -ne $SubscriptionId) {
            throw "Subscription pin missing from $($operation -join ' ')."
        }
    }
    Write-Output 'PASS: local CLI lookup omits subscription; account and resource operations retain it.'
} else {
    $account = Invoke-Azure @('account', 'show', '--query', '{id:id,state:state}', '--output', 'json') |
        ConvertFrom-Json
    if ($account.id -ne $SubscriptionId -or $account.state -ne 'Enabled') {
        throw 'Expected subscription is not enabled and authenticated.'
    }
    $version = Invoke-Azure -Arguments @(
        'extension', 'show', '--name', 'containerapp', '--query', 'version', '--output', 'tsv'
    ) -LocalCommand
    $exists = Invoke-Azure @(
        'group', 'exists', '--name', 'rg-mdt-observatory-demo', '--output', 'json'
    ) | ConvertFrom-Json
    Write-Output "PASS: account enabled; containerapp extension $version; demo group exists=$exists."
    Write-Output 'Only account show, extension show, and group exists were executed; no provisioning.'
}
