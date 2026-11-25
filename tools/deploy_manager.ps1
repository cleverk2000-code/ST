# One-time deployment. Requires authenticated SmartThings CLI, Windows PowerShell 5.1+.
[CmdletBinding()]
param([guid]$HubId)
$ErrorActionPreference='Stop'
$utf8=[Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding=$utf8
$OutputEncoding=$utf8
function Run-ST {
  param([string[]]$CliArgs)
  & smartthings @CliArgs
  if ($LASTEXITCODE -ne 0) { throw "CLI failed: $($CliArgs[0])" }
}
function Read-ST {
  param([string[]]$CliArgs)
  $out = & smartthings @CliArgs -j
  if ($LASTEXITCODE -ne 0) { throw "CLI failed: $($CliArgs[0])" }
  $raw=($out -join "`n").Trim().TrimStart([char]0xFEFF)
  if ($raw -eq 'no items found' -or $raw -eq '[]' -or -not $raw) {return @()}
  $value=ConvertFrom-Json $raw
  if ($null -ne $value.items) {return $value.items}
  return $value
}
$root=Split-Path -Parent $PSScriptRoot
$driver=Join-Path $root 'edge\st-local-manager'
if (-not (Test-Path (Join-Path $driver 'config.yaml'))) {throw 'Driver source missing'}
$hubs=@(Read-ST @('devices','--type=HUB'))
if (-not $HubId -or $HubId -eq [guid]::Empty) {
  if ($hubs.Count -eq 1) {$HubId=[guid]$hubs[0].deviceId}
  else {
    for ($i=0;$i -lt $hubs.Count;$i++){Write-Host "$($i+1): $($hubs[$i].label) ($($hubs[$i].deviceId))"}
    $answer=Read-Host 'Select hub number'
    $index=0
    if (-not [int]::TryParse($answer,[ref]$index) -or $index -lt 1 -or $index -gt $hubs.Count){throw 'Invalid hub choice'}
    $HubId=[guid]$hubs[$index-1].deviceId
  }
}
if ("$HubId" -notin @($hubs.deviceId)){throw 'Hub ID not present in your account'}
$name='ST Local Bridge 1.0'
$description='Dedicated ST Local Bridge manager channel'
$channels=@(Read-ST @('edge:channels'))
$matches=@($channels | Where-Object {$_.name -eq $name -and $_.description -eq $description})
if ($matches.Count -gt 1){throw 'Duplicate dedicated channels; resolve before deployment'}
if ($matches.Count -eq 1){$channel=$matches[0]}
else {
  if ($name -in @($channels.name)){throw 'Channel name collision'}
  $temp=[IO.Path]::Combine([IO.Path]::GetTempPath(),[guid]::NewGuid().ToString()+'.json')
  try {
    [IO.File]::WriteAllText($temp,(@{name=$name;description=$description;termsOfServiceUrl='https://github.com/cleverk2000-code/ST';type='DRIVER'} | ConvertTo-Json),$utf8)
    $channel=Read-ST @('edge:channels:create','-i',$temp)
  } finally {Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue}
}
$id=if ($channel.channelId){$channel.channelId}else{$channel.id}
if (-not $id){throw 'Channel ID missing'}
$channelId=[guid]$id
$enrollments=@(Read-ST @('edge:channels:enrollments',"$HubId"))
$enrolled=@($enrollments | Where-Object {$_.channelId -eq "$channelId" -or $_.id -eq "$channelId"})
if (-not $enrolled.Count){Run-ST @('edge:channels:enroll',"$HubId",'-C',"$channelId")}
Run-ST @('edge:drivers:package',$driver,'--install','--channel',"$channelId",'--hub',"$HubId")
Write-Host "Deployment done. Hub=$HubId Channel=$channelId"
Write-Host 'Scan nearby once, configure ST Local Manager, then add the HACS integration.'
