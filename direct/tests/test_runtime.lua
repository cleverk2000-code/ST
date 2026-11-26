-- Independent deterministic mock of device threads and a fragmented MQTT broker.
-- No Samsung SDK is claimed here; tests exercise the exact bridge module.
local now,workers,devices,sent,connections=0,{},{},{},{}
local wire=dofile("direct/lua/wire.lua")
for _,m in ipairs({"wire","transport","model","bridge"}) do
 package.preload["st_mqtt."..m]=function() return dofile("direct/lua/"..m..".lua") end
end
local function json_value(v)
 local t=type(v)
 if t=="string" then return string.format("%q",v) end
 if t=="number" or t=="boolean" then return tostring(v) end
 if t~="table" then return "null" end
 local parts={}
 for k,x in pairs(v) do parts[#parts+1]=tostring(k)..":"..json_value(x) end
 table.sort(parts);return "{"..table.concat(parts,",").."}"
end
package.preload["st.json"]=function() return {encode=json_value} end
package.preload["log"]=function() return {warn=function()end,info=function()end} end
local function push(sock,data) sock.rx=sock.rx..data end
local socket={}
function socket.gettime()return now end
function socket.sleep(n)now=now+n;coroutine.yield()end
function socket.tcp()
 local s={rx="",closed=false}
 connections[#connections+1]=s
 function s:settimeout()end
 function s:connect(host,port) assert(host=="192.168.0.19" and port==1883);return true end
 function s:send(data)
  local h,b,r=wire.pop(data);assert(h and r=="")
  local kind=math.floor(h/16)
  if kind==1 then push(self,string.char(0x20,2,0,0))
  elseif kind==8 then push(self,string.char(0x90,4,0,1,1,1))
  elseif kind==12 then push(self,string.char(0xD0,0))
  elseif kind==3 then
   local t,v,_,retain=wire.decode_publish(h,b)
   sent[#sent+1]={topic=t,payload=v,retain=retain}
  end
  return #data
 end
 function s:receive(n)
  assert(n==1)
  if self.closed then return nil,"closed" end
  if #self.rx>0 then local b=self.rx:sub(1,1);self.rx=self.rx:sub(2);return b end
  now=now+0.05;coroutine.yield()
  if self.closed then return nil,"closed" end
  return nil,"timeout"
 end
 function s:close()self.closed=true end
 return s
end
package.preload["cosock"]=function()return {socket=socket,spawn=function(fn)workers[#workers+1]=coroutine.create(fn)end}end
local function pump(n)
 for _=1,n or 1 do
  for _,co in ipairs(workers) do
   if coroutine.status(co)~="dead" then local ok,err=coroutine.resume(co);assert(ok,err) end
  end
 end
end
local function drain(d)
 while #d.jobs>0 do local fn=table.remove(d.jobs,1);fn()end
end
local function event(cap,attr,v,unit)
 return {capability_id=cap,attribute_id=attr,state={value=v,unit=unit}}
end
local function device(id,master,components)
 local d={id=id,label=id,preferences={stMqttMaster=master,stMqttExport=true,stMqttHost="192.168.0.19",stMqttPort=1883,stMqttUser="test",stMqttPass="test",stMqttSite="home"},profile={components=components},jobs={},store={},states={},original_events=0}
 d.thread={queue_event=function(_,fn)d.jobs[#d.jobs+1]=fn end}
 function d:get_field(k)return self.store[k]end
 function d:set_field(k,v)self.store[k]=v end
 function d:get_manufacturer()return "Test" end
 function d:get_model()return "TS" end
 function d:get_latest_state(c,cap,a)local st=self.states[c.."/"..cap.."/"..a];return st and st.value,st end
 function d:emit_component_event(c,e)
  self.original_events=self.original_events+1
  self.states[c.id.."/"..e.capability_id.."/"..e.attribute_id]=e.state
  e.component_id=c.id
  return e
 end
 function d:emit_event(e)return self:emit_component_event(self.profile.components.main,e)end
 return d
end
local function component(id,caps)
 local list={};for _,cap in ipairs(caps)do list[#list+1]={id=cap}end
 return {id=id,capabilities=list}
end
local d1=device("dev-one",true,{main=component("main",{"switch","powerMeter","energyMeter","button"}),switch2=component("switch2",{"switch"})})
local d2=device("dev-two",false,{main=component("main",{"windowShade","windowShadeLevel","battery"})})
d1:emit_event(event("switch","switch","off"))
d1:emit_component_event(d1.profile.components.switch2,event("switch","switch","off"))
d1:emit_event(event("powerMeter","power",12,"W"))
d2:emit_event(event("windowShade","windowShade","open"))
d2:emit_event(event("windowShadeLevel","shadeLevel",100,"%"))
local calls,original_inits,original_removed={},0,0
local function command(_,d,c)
 calls[#calls+1]={id=d.id,component=c.component,command=c.command}
end
local template={lifecycle_handlers={init=function()original_inits=original_inits+1 end,removed=function()original_removed=original_removed+1 end},capability_handlers={switch={on=command,off=command},windowShade={open=command,close=command,pause=command},windowShadeLevel={setShadeLevel=command}}}
local bridge=require"st_mqtt.bridge"
local runtime=bridge.wrap(template,"test")
local drv={}
template.lifecycle_handlers.init(drv,d1)
template.lifecycle_handlers.init(drv,d2)
assert(original_inits==2)
local root="st-direct/home/test"
local function count(t,v)
 local n=0;for _,x in ipairs(sent)do if x.topic==t and (v==nil or x.payload==v)then n=n+1 end end;return n
end
local function flush()drain(d1);drain(d2);pump(8)end
pump(6);flush()
assert(runtime.session and runtime.session.ready)
assert(#connections==1,"one connection for both devices")
assert(count(root.."/dev-one/main/state/switch","OFF")>0)
assert(count(root.."/dev-two/main/state/shade","open")>0)
assert(count(root.."/dev-one/main/state/power","12")>0)
local function cmd(topic,payload,header,id)
 local sock=connections[#connections]
 push(sock,wire.frame(header or 0x30,wire.str(topic)..(id and wire.u16(id) or "")..payload))
 pump(6)
end
local target=root.."/dev-one/switch2/cmd/switch"
cmd(target,"ON",0x31);flush();assert(#calls==0,"retained command refused")
cmd(target,"toggle");flush();assert(#calls==0,"invalid command refused")
cmd(target,"ON",0x32,1);flush()
assert(#calls==1 and calls[1].id=="dev-one" and calls[1].component=="switch2" and calls[1].command=="on")
cmd(target,"ON",0x3A,1);flush();assert(#calls==1,"DUP packet refused")
cmd(target,"OFF",0x32,1);flush();assert(#calls==2,"new packet ID reuse accepted")
cmd(root.."/dev-two/main/cmd/shade","CLOSE");flush()
assert(#calls==3 and calls[3].id=="dev-two" and calls[3].command=="close")
-- Same button event twice must be delivered twice, not coalesced or duplicated by nested emit wrappers.
local before=count(root.."/dev-one/main/state/button")
d1:emit_event(event("button","button","pushed"))
d1:emit_event(event("button","button","pushed"))
pump(8);assert(count(root.."/dev-one/main/state/button")==before+2)
-- Delay queued physical action past the permitted deadline.
cmd(target,"ON");now=now+3;flush();assert(#calls==3,"stale queued command refused")
-- Disconnect after accepting a command but before the device thread executes it.
cmd(target,"ON")
local first=connections[#connections];first.closed=true
pump(20);assert(#connections>=2,"reconnect")
flush();assert(#calls==3,"previous MQTT session command refused")
-- Existing device removal deletes only its own discovery configurations.
local removed_topic
for _,x in ipairs(sent)do if x.topic:find("dev%-two") and x.topic:match("^homeassistant/")then removed_topic=x.topic;break end end
assert(removed_topic)
template.lifecycle_handlers.removed(drv,d2);pump(10)
assert(original_removed==1 and count(removed_topic,"")>=1)
cmd(root.."/dev-two/main/cmd/shade","CLOSE");flush();assert(#calls==3)
-- The original device handler remains callable independently of MQTT.
d1.preferences.stMqttMaster=false
template.lifecycle_handlers.infoChanged(drv,d1);pump(15)
assert(count(root.."/availability","offline")>0)
template.capability_handlers.switch.on(drv,d1,{component="main"})
assert(#calls==4)
print("direct runtime simulation passed")

-- Official SDK adapter: polling does not replace lifecycle, command goes through SDK injector.
local sdkdev=device("sdk-device",true,{main=component("main",{"switch","powerMeter"})})
sdkdev:emit_event(event("switch","switch","off"))
local sdklist={sdkdev}
local scheduled
local injected={}
local sdk={}
function sdk:get_devices()return sdklist end
function sdk:call_on_schedule(interval,cb)assert(interval==3);scheduled=cb end
function sdk:inject_capability_command(d,c)injected[#injected+1]={id=d.id,command=c.command,component=c.component,args=c.named_args}end
local sdkstate=bridge.attach(sdk,"st-test")
assert(scheduled and next(sdkstate.devices)==nil)
scheduled();pump(8);drain(sdkdev);pump(8)
assert(sdkstate.session.ready)
local sdkroot="st-direct/home/st-test"
assert(count(sdkroot.."/sdk-device/main/state/switch","OFF")>0)
cmd(sdkroot.."/sdk-device/main/cmd/switch","ON");drain(sdkdev);pump(8)
assert(#injected==1 and injected[1].command=="on" and injected[1].id=="sdk-device")
-- Changing a profile adds a new capability on the existing device.
sdkdev.profile.components.main.capabilities[#sdkdev.profile.components.main.capabilities+1]={id="energyMeter"}
sdkdev:emit_event(event("energyMeter","energy",1.5,"kWh"))
scheduled();drain(sdkdev);pump(8)
assert(count(sdkroot.."/sdk-device/main/state/energy","1.5")>0)
-- A single incomplete inventory scan does not delete the device; confirmed absence does.
sdklist={};scheduled();assert(sdkstate.devices["sdk-device"]~=nil)
cmd(sdkroot.."/sdk-device/main/cmd/switch","OFF");drain(sdkdev);assert(#injected==1)
scheduled();assert(sdkstate.devices["sdk-device"]==nil)
pump(15)
print("official SDK adapter simulation passed")

-- A gang represented as an Edge child owns its own main switch and MQTT identity.
local gang=device("gang-two",false,{main=component("main",{"switch"})})
gang.parent_assigned_child_key="02"
gang.get_model=nil
gang.get_manufacturer=nil
gang:emit_event(event("switch","switch","off"))
sdklist={sdkdev,gang}
local childstate=bridge.attach(sdk,"st-zigbee-switch")
scheduled();pump(8);drain(gang);drain(sdkdev);pump(8)
assert(childstate.devices[gang.id])
local discovery="homeassistant/switch/std_st-direct_home_st-zigbee-switch_gang-two_main_switch/config"
assert(count(discovery)>0)
local gangbase="st-direct/home/st-zigbee-switch/gang-two/main"
assert(count(gangbase.."/state/switch","OFF")>0)
cmd(gangbase.."/cmd/switch","ON");drain(gang);pump(8)
assert(injected[#injected].id==gang.id and injected[#injected].command=="on")
gang.preferences.stMqttExport=false
scheduled();drain(gang);pump(8)
assert(count(discovery,"")>0)
print("switch child discovery and command routing passed")
