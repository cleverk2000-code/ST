$ErrorActionPreference='Stop'
$hub='4bea0363-9f70-41fc-873e-79abc1a614b7'
$channel='0a5fa625-b1aa-4046-a5fa-8bf46aeb8331'
$root=Join-Path ([IO.Path]::GetTempPath()) ('st-resume-'+[guid]::NewGuid().ToString('N'))
$global:preflight=0
$global:uploads=0
$global:expected=7
$global:failAt=0
function global:smartthings {
 $global:LASTEXITCODE=0
 if($args[0] -eq 'edge:drivers:installed'){
  if($global:uploads -ne $global:expected){throw 'Premature verification'}
  return
 }
 if($args[0] -ne 'edge:drivers:package'){throw "Unexpected CLI command"}
 if($args[2] -eq '--build-only'){
  if($global:uploads -ne 0){throw 'Upload before all preflight checks'}
  if($args[1] -isnot [string] -or -not (Test-Path -LiteralPath $args[1] -PathType Container)){throw 'Invalid scalar path'}
  $global:preflight++
  if($global:failAt -eq $global:preflight){$global:LASTEXITCODE=1;return}
  [IO.File]::WriteAllText([string]$args[3],'mock zip')
 }elseif($args[1] -eq '--upload'){
  if($global:preflight -ne $global:expected){throw 'Incomplete preflight'}
  if(-not (Test-Path -LiteralPath $args[2])){throw 'Missing package ZIP'}
  $global:uploads++
 }else{throw 'Unknown package mode'}
}
try {
 foreach($n in @(7,1)){
  $fixture=Join-Path $root "fixture-$n"
  python ./universal/tests/make_resume_fixture.py $fixture $n
  if($LASTEXITCODE -ne 0){throw 'Fixture build failed'}
  $global:expected=$n;$global:preflight=0;$global:uploads=0
  & ./universal/resume_install.ps1 -Build $fixture -ChannelId $channel -HubId $hub
  if($global:uploads -ne $n){throw "Expected $n uploads"}
 }
 $global:expected=7;$global:preflight=0;$global:uploads=0;$global:failAt=2
 $failed=$false
 try {& ./universal/resume_install.ps1 -Build (Join-Path $root 'fixture-7') -ChannelId $channel -HubId $hub}
 catch {if($_.Exception.Message -notlike 'CLI package check failed:*'){throw};$failed=$true}
 if(-not $failed -or $global:uploads -ne 0){throw 'Failure guard did not stop uploads'}
 Write-Host "Resume regression passed on PowerShell $($PSVersionTable.PSVersion)"
} finally {
 Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
 Remove-Item Function:\smartthings -ErrorAction SilentlyContinue
}

# Expected mock failure must not leak into GitHub Actions' shell exit wrapper.
$global:LASTEXITCODE=0
