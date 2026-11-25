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
# Windows PowerShell 5.1 emits a JSON array as one pipeline object.
# Assign the deserialized array directly, then explicitly iterate its entries.
$decoded=ConvertFrom-Json -InputObject (Get-Content -LiteralPath (Join-Path $root 'manifest.json') -Raw -Encoding UTF8)
$families=@()
foreach($entry in $decoded){
 if($null -eq $entry -or $entry.family -isnot [string] -or $entry.family -notmatch '^[a-z0-9][a-z0-9-]{0,62}$'){throw 'Invalid manifest family'}
 $family=[string]$entry.family
 if($families -contains $family){throw "Duplicate manifest family: $family"}
 if(-not (Test-Path -LiteralPath (Join-Path -Path $root -ChildPath $family) -PathType Container)){throw "Missing package: $family"}
 $families+= $family
}
if($families.Count -eq 0){throw 'Missing manifest'}
$zipDir=Join-Path $root ('cli-preflight-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $zipDir -Force | Out-Null
foreach($family in $families){
 $pkg=Join-Path $root $family
 $zip=Join-Path $zipDir ($family+'.zip')
 Write-Host "Checking CLI package: $family" -ForegroundColor Cyan
 & smartthings edge:drivers:package $pkg --build-only $zip
 if($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $zip)){throw "CLI package check failed: $family; nothing uploaded."}
}
$ok=@()
foreach($family in $families){
 Write-Host "Installing: $family" -ForegroundColor Cyan
 & smartthings edge:drivers:package --upload (Join-Path $zipDir ($family+'.zip')) --channel "$ChannelId" --hub "$HubId"
 if($LASTEXITCODE -ne 0){throw "Server upload/install failed: $family. Installed in this run: $($ok -join ', ')"}
 $ok+=@($family)
}
& smartthings edge:drivers:installed -H "$HubId"
if($LASTEXITCODE -ne 0){throw 'Driver list verification failed'}
Write-Host "SUCCESS: $($ok.Count) of $($families.Count) drivers installed" -ForegroundColor Green
