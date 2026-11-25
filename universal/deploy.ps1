# Build and deploy chosen packages, never changes drivers of existing devices.
[CmdletBinding()]
param(
 [guid]$HubId,
 [guid]$ChannelId,
 [switch]$Install,
 [switch]$AllOfficial,
 [string]$Custom,
 [switch]$PlanOnly,
 [switch]$Bootstrap
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Console]::OutputEncoding
$python=Get-Command py -ErrorAction SilentlyContinue
if ($python) {$exe='py';$pyArgs=@('-3')} else {$exe='python';$pyArgs=@()}
& $exe @pyArgs -c 'import yaml'
if ($LASTEXITCODE -ne 0){throw 'Install PyYAML first: py -3 -m pip install PyYAML'}
$out=Join-Path $PSScriptRoot ('build-'+[DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff'))
# Select an existing owned channel/hub, or create a dedicated channel. Never delete anything.
function Read-ST {
 param([string[]]$CliArgs)
 $raw=(& smartthings @CliArgs -j | Out-String).Trim().TrimStart([char]0xFEFF)
 if ($LASTEXITCODE -ne 0){throw "CLI failed: $($CliArgs[0])"}
 if (-not $raw -or $raw -in @('no items found','no items found.','null','[]')){return}
 $parsed=$raw | ConvertFrom-Json
 if ($null -eq $parsed){return}
 if ($parsed.PSObject.Properties['items']){$parsed=$parsed.items}
 @($parsed) | Where-Object {$null -ne $_ -and $_ -is [pscustomobject]}
}
function Pick-Item {
 param($Items,$Title)
 for($i=0;$i -lt $Items.Count;$i++){Write-Host "$($i+1). $($Items[$i].label) $($Items[$i].name)"}
 $answer=0
 if (-not [int]::TryParse((Read-Host $Title),[ref]$answer) -or $answer -lt 1 -or $answer -gt $Items.Count){throw 'Invalid selection'}
 return $Items[$answer-1]
}
if ($HubId -eq [guid]::Empty){
 $hubs=@(Read-ST @('devices') | Where-Object {$_.type -eq 'HUB'})
 if ($hubs.Count -eq 0){throw 'No SmartThings hub found. Specify -HubId.'}
 $hub=if ($hubs.Count -eq 1){$hubs[0]}else{Pick-Item $hubs 'Select hub'}
 $HubId=[guid]$hub.deviceId
}
# Inventory is read-only; save it beside the output, never upload it.
$ds=@(Read-ST @('devices') | Where-Object {$null -ne $_})
$dr=@(Read-ST @('edge:drivers:installed','-H',"$HubId") | Where-Object {$null -ne $_})
$ds=@($ds | Where-Object {$_.type -eq 'ZIGBEE' -and ($_.zigbee.hubId -eq "$HubId" -or $_.parentDeviceId -eq "$HubId" -or (-not $_.zigbee.hubId -and -not $_.parentDeviceId -and $_.zigbee.driverId -in @($dr.driverId)))})
$deviceFile=$out+'-devices.json';$driverFile=$out+'-drivers.json';$planFile=$out+'-plan.json'
$utf8=[Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($deviceFile,(ConvertTo-Json -InputObject @($ds) -Depth 40),$utf8)
[IO.File]::WriteAllText($driverFile,(ConvertTo-Json -InputObject @($dr) -Depth 40),$utf8)
$customArgs=@()
if (-not $Custom -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot "custom.local.json"))){$Custom=Join-Path $PSScriptRoot "custom.local.json"}
if ($Custom){$customArgs=@('--custom',(Resolve-Path -LiteralPath $Custom).Path)}
& $exe @pyArgs (Join-Path $PSScriptRoot 'inventory.py') --devices $deviceFile --drivers $driverFile --out $planFile @customArgs
if ($LASTEXITCODE -ne 0){throw 'Inventory classification failed'}
$plan=@(Get-Content -LiteralPath $planFile -Encoding UTF8 -Raw | ConvertFrom-Json)
$plan | Format-Table label,driver,method,package -AutoSize
Write-Host "Plan: $planFile"
if ($PlanOnly){return}
$buildArgs=if($AllOfficial){@('--all-official')}else{@('--plan',$planFile)}
$knownCount=@($plan | Where-Object {$_.method -in @('official','wonjj','custom')}).Count
$existingCount=@($plan | Where-Object {$_.method -eq 'already_mqtt'}).Count
if (-not $AllOfficial -and ($Bootstrap -or ($knownCount -eq 0 -and $existingCount -eq 0))){
 Write-Host 'Including baseline switch, motion, window and plug packages.'
 $buildArgs+=@('--bootstrap')
}
if (-not $AllOfficial -and -not $Bootstrap -and $knownCount -eq 0 -and $existingCount -gt 0){
 Write-Host 'No additional recognized drivers to install. Review the inventory plan.'
 return
}
& $exe @pyArgs (Join-Path $PSScriptRoot 'build.py') --out $out @buildArgs @customArgs
if ($LASTEXITCODE -ne 0){throw 'Build failed; no driver uploaded'}
& $exe @pyArgs (Join-Path $PSScriptRoot 'repair_profiles.py') $out --check
if ($LASTEXITCODE -ne 0){throw 'Profile validation failed; no upload'}
if (-not $Install){Write-Host "Build only: $out";return}
$manifest=@(Get-Content -LiteralPath (Join-Path $out 'manifest.json') -Raw | ConvertFrom-Json)
$manifest | Format-Table family,adapter -AutoSize
if ((Read-Host 'Install these packages without changing existing device drivers? (y/N)') -ne 'y'){return}
if ($ChannelId -eq [guid]::Empty){
 $channels=@(Read-ST @('edge:channels'))
 $mine=@($channels | Where-Object {$_.name -eq 'ST Universal MQTT'})
 if ($mine.Count -gt 1){throw 'Duplicate ST Universal MQTT channels. Specify -ChannelId.'}
 if ($mine.Count -eq 1){$channel=$mine[0]}
 else {
  $tmp=Join-Path ([IO.Path]::GetTempPath()) ('st-channel-'+[guid]::NewGuid().ToString()+'.json')
  try{
   $payload=@{name='ST Universal MQTT';description='Dedicated universal Zigbee MQTT channel';termsOfServiceUrl='https://github.com/cleverk2000-code/ST';type='DRIVER'}
   [IO.File]::WriteAllText($tmp,($payload | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
   $channel=Read-ST @('edge:channels:create','-i',$tmp)
  }finally{Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue}
 }
 $id=if($channel.channelId){$channel.channelId}else{$channel.id}
 if (-not $id){throw 'Channel ID missing'}
 $ChannelId=[guid]$id
}
$enrolled=@(Read-ST @('edge:channels:enrollments',"$HubId") | Where-Object {$_.channelId -eq "$ChannelId" -or $_.id -eq "$ChannelId"})
if (-not $enrolled.Count){
 & smartthings edge:channels:enroll "$HubId" -C "$ChannelId"
 if ($LASTEXITCODE -ne 0){throw 'Channel enrollment failed; no driver uploaded'}
}
Write-Host "Hub=$HubId Channel=$ChannelId"
foreach ($entry in $manifest){
 $p=$entry.family
 & smartthings edge:drivers:package (Join-Path $out $p) --channel "$ChannelId" --hub "$HubId"
 if ($LASTEXITCODE -ne 0){throw "Deployment failed at $p; earlier packages may already be installed."}
}
Write-Host 'Drivers installed. Switch only compatible devices manually; configure MQTT on one device per family.'
