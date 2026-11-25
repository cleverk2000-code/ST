[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$Build,
 [Parameter(Mandatory=$true)][guid]$ChannelId,
 [Parameter(Mandatory=$true)][guid]$HubId
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $Build).Path
$py=Get-Command py -ErrorAction SilentlyContinue
if($py){$exe='py';$pa=@('-3')}else{$exe='python';$pa=@()}
& $exe @pa (Join-Path $PSScriptRoot 'repair_profiles.py') $root
if($LASTEXITCODE -ne 0){throw 'Local repair failed; nothing uploaded.'}
& $exe @pa (Join-Path $PSScriptRoot 'repair_profiles.py') $root --check
if($LASTEXITCODE -ne 0){throw 'Local validation failed; nothing uploaded.'}
$manifest=@(Get-Content -LiteralPath (Join-Path $root 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json)
if(-not $manifest.Count){throw 'Missing manifest'}
$zipDir=Join-Path $root 'cli-preflight'
New-Item -ItemType Directory -Path $zipDir -Force | Out-Null
foreach($p in $manifest){
 $family=$p.family
 $pkg=Join-Path $root $family
 $zip=Join-Path $zipDir ($family+'.zip')
 Write-Host "Checking CLI package: $family" -ForegroundColor Cyan
 & smartthings edge:drivers:package $pkg --build-only $zip
 if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $zip)){throw "CLI package check failed: $family; nothing uploaded."}
}
$ok=@()
foreach($p in $manifest){
 $family=$p.family
 Write-Host "Installing: $family" -ForegroundColor Cyan
 & smartthings edge:drivers:package --upload (Join-Path $zipDir ($family+'.zip')) --channel "$ChannelId" --hub "$HubId"
 if($LASTEXITCODE -ne 0){throw "Server upload/install failed: $family. Installed in this run: $($ok -join ', ')"}
 $ok+=@($family)
}
Write-Host "SUCCESS: $($ok.Count) of $($manifest.Count) drivers installed" -ForegroundColor Green
& smartthings edge:drivers:installed -H "$HubId"
if($LASTEXITCODE -ne 0){throw 'Driver list verification failed'}
