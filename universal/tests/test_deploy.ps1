$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
foreach($p in @('universal/deploy.ps1','direct/deploy.ps1')){
 $ast=[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $p).Path,[ref]$tokens,[ref]$errors)
 if($errors.Count){throw ($errors | Out-String)}
}
function global:smartthings {
 $global:LASTEXITCODE=0
 if($args[0] -eq 'devices'){ '[null,{"type":"ZIGBEE","deviceId":"test","zigbee":{"hubId":"4bea0363-9f70-41fc-873e-79abc1a614b7","driverId":"unknown"}}]' }
 elseif($args[0] -eq 'edge:drivers:installed'){ '[null]' }
 else { throw "Unexpected CLI mutation: $args" }
}
& ./universal/deploy.ps1 -PlanOnly -HubId 4bea0363-9f70-41fc-873e-79abc1a614b7
$latest=Get-ChildItem ./universal/build-*-plan.json | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$plan=@(Get-Content $latest.FullName -Raw | ConvertFrom-Json)
if($plan.Count -ne 1 -or $plan[0].method -ne 'rules_or_review'){throw 'Invalid null inventory plan'}
Write-Host 'PowerShell null inventory regression passed'
