# Build and deploy chosen packages, never changes drivers of existing devices.
[CmdletBinding()]
param(
 [string[]]$Packages=@('ef00-covers-2-wonjj6768','zcl-plugs-wonjj6768'),
 [guid]$HubId,
 [guid]$ChannelId,
 [switch]$Install
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$python=Get-Command py -ErrorAction SilentlyContinue
if ($python) {$exe='py';$pyArgs=@('-3')} else {$exe='python';$pyArgs=@()}
& $exe @pyArgs -c 'import yaml'
if ($LASTEXITCODE -ne 0){throw 'Install PyYAML first: py -3 -m pip install PyYAML'}
$out=Join-Path $PSScriptRoot ('build-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff'))
& $exe @pyArgs (Join-Path $PSScriptRoot 'build.py') --out $out --packages @Packages
if ($LASTEXITCODE -ne 0){throw 'Build failed; no driver uploaded.'}
if (-not $Install){Write-Host "Build only: $out";return}
if ($HubId -eq [guid]::Empty -or $ChannelId -eq [guid]::Empty){throw 'Specify your own enrolled HubId and ChannelId. No driver uploaded.'}
foreach ($p in $Packages){
 & smartthings edge:drivers:package (Join-Path $out $p) --channel "$ChannelId" --hub "$HubId"
 if ($LASTEXITCODE -ne 0){throw "Deployment failed at $p; earlier packages may already be installed."}
}
Write-Host 'Drivers installed. Switch only compatible devices manually; configure MQTT on one device per family.'
