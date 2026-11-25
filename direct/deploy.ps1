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
# Select an existing owned channel/hub, or create a dedicated channel. Never delete anything.
function Read-ST {
 param([string[]]$CliArgs)
 $raw=(& smartthings @CliArgs -j | Out-String).Trim().TrimStart([char]0xFEFF)
 if ($LASTEXITCODE -ne 0){throw "CLI failed: $($CliArgs[0])"}
 if (-not $raw -or $raw -eq 'no items found' -or $raw -eq '[]'){return @()}
 $parsed=$raw | ConvertFrom-Json
 if ($null -ne $parsed.items){return $parsed.items}
 return $parsed
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
if ($ChannelId -eq [guid]::Empty){
 $channels=@(Read-ST @('edge:channels'))
 $mine=@($channels | Where-Object {$_.name -eq 'ST Direct MQTT'})
 if ($mine.Count -gt 1){throw 'Duplicate ST Direct MQTT channels. Specify -ChannelId.'}
 if ($mine.Count -eq 1){$channel=$mine[0]}
 else {
  $tmp=[IO.Path]::GetTempFileName()
  try{
   $payload=@{name='ST Direct MQTT';description='Dedicated direct Zigbee MQTT channel';termsOfServiceUrl='https://github.com/cleverk2000-code/ST'}
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
foreach ($p in $Packages){
 & smartthings edge:drivers:package (Join-Path $out $p) --channel "$ChannelId" --hub "$HubId"
 if ($LASTEXITCODE -ne 0){throw "Deployment failed at $p; earlier packages may already be installed."}
}
Write-Host 'Drivers installed. Switch only compatible devices manually; configure MQTT on one device per family.'
