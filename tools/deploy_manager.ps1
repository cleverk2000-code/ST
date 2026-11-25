# Run once from the repository root. Uses authenticated SmartThings CLI.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$utf8=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=$utf8
$OutputEncoding=$utf8
function Run-ST {
  param([string[]]$CliArgs)
  & smartthings @CliArgs
  if ($LASTEXITCODE -ne 0) { throw "CLI failed: $($CliArgs[0])" }
}
$root=Split-Path -Parent $PSScriptRoot
$driver=Join-Path $root 'edge\st-local-manager'
if (-not (Test-Path (Join-Path $driver 'config.yaml'))) {throw 'Driver source missing'}
Write-Host 'Create or select your dedicated ST Local Bridge channel.'
Write-Host 'If no channel exists, create one now. Terms URL: https://github.com/cleverk2000-code/ST'
$answer=Read-Host 'Create a new channel? (y/N)'
if ($answer -eq 'y') {Run-ST @('edge:channels:create')}
Write-Host 'Enroll the TV hub in your dedicated channel (skip if already enrolled).'
$answer=Read-Host 'Enroll hub now? (y/N)'
if ($answer -eq 'y') {Run-ST @('edge:channels:enroll')}
Run-ST @('edge:drivers:package',$driver,'--install')
Write-Host 'Open SmartThings, scan nearby once, configure ST Local Manager.'
