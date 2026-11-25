package.path="edge/st-local-manager/src/?.lua;"..package.path
local c=require"contract"
local w=require"wire"
local t=require"transport"
local a,b=c.command("shade","CLOSE",{shade=true})
assert(a=="commandOff" and b==nil)
assert(c.command("shade","STOP",{shade=true})==nil)
assert(c.command("shade","STOP",{shade=true,stop=true})=="commandStop")
assert(c.command("switch","ON",{shade=true})==nil)
local comp,v=c.command("position","42",{position=true})
assert(comp=="commandPosition" and v==42)
assert(c.command("position","101",{position=true})==nil)
assert(c.command("position","1.5",{position=true})==nil)
local f,s=c.report("shadeReport",0)
assert(f=="shade" and s=="closed")
f,s=c.report("temperatureReport",-12.5)
assert(f=="temperature" and tonumber(s)==-12.5)
assert(c.report("switchReport",2)=="switch")
assert(select(2,c.report("switchReport",2))==nil)
assert(c.report("positionReport",101)==nil)
assert(w.pop(w.frame(0xD0,""))==0xD0)
print("Manager contract tests passed")
