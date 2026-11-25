# Register local Rules using the already authenticated SmartThings CLI.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][guid]$Physical,
    [Parameter(Mandatory=$true)][guid]$Proxy,
    [Parameter(Mandatory=$true)][guid]$Location,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
if ($Physical -eq $Proxy) { throw 'Physical and proxy IDs must differ.' }
function Invoke-STJson {
    param([string[]]$Arguments)
    $output = & smartthings @Arguments -j
    if ($LASTEXITCODE -ne 0) { throw "SmartThings CLI failed: $($Arguments[0])" }
    return ($output -join "`n" | ConvertFrom-Json)
}
$physicalDevice = Invoke-STJson -Arguments @('devices',"$Physical")
$proxyDevice = Invoke-STJson -Arguments @('devices',"$Proxy")
if ($physicalDevice.locationId -ne "$Location" -or $proxyDevice.locationId -ne "$Location") { throw 'Device location mismatch.' }
$main = $physicalDevice.components | Where-Object { $_.id -eq 'main' }
if ('windowShade' -notin @($main.capabilities.id)) { throw 'Physical device lacks windowShade.' }
if ($physicalDevice.parentDeviceId -ne $proxyDevice.parentDeviceId -or -not $physicalDevice.parentDeviceId) { throw 'Devices must share the same hub.' }
foreach ($c in @('commandOn','commandOff','commandStop','shadeReport')) {
    if ($c -notin @($proxyDevice.components.id)) { throw "Proxy missing component $c. Create a new bridge-v3 proxy." }
}
function New-Rule {
    param($Name,$From,$Component,$Capability,$Attribute,$Value,$To,$TargetComponent,$TargetCapability,$Command,$Code)
    $cmd = @{component=$TargetComponent;capability=$TargetCapability;command=$Command}
    if ($null -ne $Code) { $cmd.arguments=@(@{integer=[int]$Code}) }
    return @{name=$Name;actions=@(@{if=@{equals=@{
        left=@{device=@{devices=@("$From");component=$Component;capability=$Capability;attribute=$Attribute;trigger='Always'}}
        right=@{string=$Value}
    };then=@(@{command=@{devices=@("$To");commands=@($cmd)}})}})}
}
$prefix="ST Edge $Physical"
$states=[ordered]@{'closed'=0;'open'=1;'opening'=2;'closing'=3;'partially open'=4;'paused'=5;'unknown'=6}
$rules=@()
foreach ($state in $states.Keys) {
    $rules += New-Rule -Name "$prefix shade $state" -From $Physical -Component 'main' -Capability 'windowShade' -Attribute 'windowShade' -Value $state -To $Proxy -TargetComponent 'shadeReport' -TargetCapability 'switchLevel' -Command 'setLevel' -Code $states[$state]
}
$commands=[ordered]@{'open'='commandOn';'close'='commandOff';'pause'='commandStop'}
foreach ($command in $commands.Keys) {
    $rules += New-Rule -Name "$prefix command $command" -From $Proxy -Component $commands[$command] -Capability 'button' -Attribute 'button' -Value 'pushed' -To $Physical -TargetComponent 'main' -TargetCapability 'windowShade' -Command $command
}
if (-not $Apply) {
    $rules | ConvertTo-Json -Depth 20
    Write-Host 'Dry run only. Add -Apply to create rules.'
    return
}
$existing=Invoke-STJson -Arguments @('rules','-l',"$Location")
if ($null -ne $existing.items) { $existing=$existing.items }
foreach ($rule in $rules) {
    if ($rule.name -in @($existing.name)) { throw "Rule already exists: $($rule.name)" }
}
$created=@()
$temp=[IO.Path]::GetTempFileName()
try {
    foreach ($rule in $rules) {
        [IO.File]::WriteAllText($temp,($rule | ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
        $result=Invoke-STJson -Arguments @('rules:create','-l',"$Location",'-i',$temp)
        if (-not $result.id) { throw 'Rule ID missing; inspect SmartThings before retrying.' }
        $created+=@($result.id)
        $detail=Invoke-STJson -Arguments @('rules',"$($result.id)",'-l',"$Location")
        Write-Host "$($rule.name) : $($detail.executionLocation) ($($result.id))"
        if ($detail.executionLocation -ne 'Local') { throw 'Rule local execution not confirmed.' }
    }
    Write-Host 'All ten rules report Local. Test physical behavior before enabling automations.'
} catch {
    Write-Warning ("Created IDs; review/delete these rules before retry: " + ($created -join ', '))
    throw
} finally {
    Remove-Item -LiteralPath $temp -Force
}
