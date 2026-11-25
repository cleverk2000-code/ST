package.path="edge/st-local-manager/src/?.lua;"..package.path
local c=require"contract"
local w=require"wire"
local t=require"transport"
assert(c.command("shade","CLOSE",{shade=true})=="commandOff")
assert(c.command("shade","STOP",{shade=true})==nil)
assert(c.command("shade","STOP",{shade=true,stop=true})=="commandStop")
assert(c.command("switch","on",{switch=true})=="commandOn")
assert(c.command("switch","ON",{shade=true})==nil)
local comp,v=c.command("position","42",{shade=true,position=true})
assert(comp=="commandLevel" and v==42)
assert(c.command("position","101",{position=true})==nil)
assert(c.command("position","1.5",{position=true})==nil)
local f,s=c.report("reportA","switchLevel",0,{shade=true})
assert(f=="shade" and s=="closed")
f,s=c.report("reportA","thermostatHeatingSetpoint",-12.5,{temperature=true})
assert(f=="temperature" and tonumber(s)==-12.5)
f,s=c.report("reportA","thermostatCoolingSetpoint",47.5,{humidity=true})
assert(f=="humidity" and tonumber(s)==47.5)
assert(c.report("reportA","switchLevel",2,{switch=true})==nil)
assert(c.report("reportD","switchLevel",101,{shade=true,position=true})==nil)
assert(c.report("reportA","audioVolume",25,{})==nil)
assert(w.pop(w.frame(0xD0,""))==0xD0)
print("Manager contract tests passed")
