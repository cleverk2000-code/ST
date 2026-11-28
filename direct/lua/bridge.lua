-- Separate MQTT task; original upstream lifecycle and Zigbee command handlers remain authoritative.
local cosock=require "cosock"
local socket=cosock.socket
local log=require "log"
local json=require "st.json"
local wire=require "st_mqtt.wire"
local transport=require "st_mqtt.transport"
local model=require "st_mqtt.model"
local M={}
local function protected(fn,...)
 local ok,result=pcall(fn,...)
 if not ok then log.warn("ST Direct: bridge operation failed; original Zigbee operation retained") end
 return ok,result
end
local function config(d)
 local p=d.preferences or {}
 if p.stMqttMaster~=true then return nil end
 local port=tonumber(p.stMqttPort)
 if not wire.private_ipv4(p.stMqttHost) or not port or port<1 or port>65535 or port%1~=0 or type(p.stMqttUser)~="string" or p.stMqttUser=="" or type(p.stMqttPass)~="string" or p.stMqttPass=="" or not model.safe_token(p.stMqttSite) then return false end
 return {host=p.stMqttHost,port=port,user=p.stMqttUser,password=p.stMqttPass,site=p.stMqttSite}
end
local function same(a,b)
 if not a or not b then return a==b end
 return a.host==b.host and a.port==b.port and a.user==b.user and a.password==b.password and a.site==b.site
end
local function exported(d) return (d.preferences or {}).stMqttExport~=false end
local function caps_of(comp)
 local caps={}
 for k,v in pairs(comp.capabilities or {}) do
  if type(v)=="table" and v.id then caps[v.id]=true elseif type(k)=="string" then caps[k]=true end
 end
 return caps
end
local function trackable(s,d)
 if not model.safe_token(d.id) then return false end
 if type(d.parent_assigned_child_key)~="string" then return true end
 -- Official switch subdrivers can expose a separate child device for each gang.
 local main=d.profile and d.profile.components and d.profile.components.main
 return s.inject and s.family=="st-zigbee-switch" and main and caps_of(main).switch
end
local function category(comp)
 for _,c in pairs(comp.categories or {}) do if type(c)=="table" and c.name then return c.name elseif type(c)=="string" then return c end end
end
local function client_id(prefix)
 local h=7
 for i=1,#prefix do h=(h*131+prefix:byte(i))%2147483647 end
 return string.format("std-%08x",h)
end
local function put(c,t,v,retain)
 if c and c.ready then c.pending[t]={value=v,retain=retain~=false} end
end
local function current(s,c) return s.session==c and c.ready and not c.cancel and not c.stopping end
-- Read-only diagnostics for the two exact HOBEIAN TS0601 fingerprints.
-- These models have no documented measured-distance DP. Never label raw data as metres.
local radar_known={
 ["_TZE200_rhgsbacq"]={[1]=true,[2]=true,[101]=true,[102]=true,[104]=true,[105]=true,[106]=true,[107]=true,[108]=true,[109]=true,[110]=true,[111]=true},
 ["_TZE200_y8jijhba"]={[1]=true,[2]=true,[102]=true,[106]=true,[107]=true,[108]=true,[110]=true},
}
local radar_commands={[1]=true,[2]=true,[5]=true,[6]=true}
local function radar_mapping(d)
 if type(d.get_model)~="function" or type(d.get_manufacturer)~="function" or d:get_model()~="TS0601" then return nil end
 return radar_known[d:get_manufacturer()]
end
local function radar_report(s,d,rx)
 local known=radar_mapping(d)
 if not known then return end
 local body=rx and rx.body
 local cmd=body and body.zcl_header and body.zcl_header.cmd
 if not cmd or not radar_commands[cmd.value] then return end
 local raw=body.zcl_body and body.zcl_body.body_bytes
 -- Tuya report: two status/transaction bytes, then ID/type/big-endian length/value.
 if type(raw)~="string" or #raw<6 or #raw>1024 then return end
 local entries={}
 local i=3
 while i<=#raw do
  if i+3>#raw then return end
  local dp,dt,hi,lo=raw:byte(i,i+3)
  local len=hi*256+lo
  if i+3+len>#raw then return end
  local hex=raw:sub(i+4,i+3+len):gsub(".",function(x)return string.format("%02X",x:byte())end)
  entries[#entries+1]=string.format("DP%d/type%d=%s%s",dp,dt,hex,known[dp] and "" or " (unknown)")
  i=i+4+len
 end
 if #entries==0 then return end
 local report=table.concat(entries,"; ")
 log.info("ST Direct radar DP "..d.id..": "..report)
 local rec=s.devices[d.id]
 if not rec or rec.device~=d or not exported(d) then return end
 rec.radar_state=#report<=255 and report or report:sub(1,252).."..."
 local c=s.session
 if c and current(s,c) then
  for _,e in pairs(rec.entities or {}) do
   if e.component=="main" and e.config.state_topic==e.base.."/state/radar_dp" then
    put(c,e.config.state_topic,rec.radar_state)
   end
  end
 end
end
local function describe(s,c,d,rec)
 local out={}
 for key,comp in pairs(d.profile.components or {}) do
  local id=comp.id or key
  if model.safe_token(id) then
   local caps=caps_of(comp)
   if id=="main" and s.radar_capture and radar_mapping(d) then caps.stRadarDiagnostic=true end
   local entities=model.describe(c.prefix,d.id,id,d.label or d.name or d.id,type(d.get_manufacturer)=="function" and d:get_manufacturer() or nil,type(d.get_model)=="function" and d:get_model() or nil,caps,s.handlers,rec.hook,category(comp) or (s.family:find("lights",1,true) and "Light" or s.family:find("plugs",1,true) and "SmartPlug" or nil))
   if entities.shade then
    local allowed=d:get_latest_state(id,"windowShade","supportedWindowShadeCommands")
    if type(allowed)=="table" and #allowed>0 then
     local pause=false;for _,v in ipairs(allowed) do if v=="pause" then pause=true end end
     if not pause then entities.shade.config.payload_stop="" end
    end
   end
   for _,e in pairs(entities) do out[e.topic]=e;e.component=id;e.caps=caps end
  end
 end
 return out
end
local function owned_topic(c,d,t)
 local token="std_"..c.prefix:gsub("/","_").."_"..d.id.."_"
 if type(t)~="string" then return false end
 local id=t:match("^homeassistant/[%w_]+/([^/]+)/config$")
 return id~=nil and id:sub(1,#token)==token
end
local function remove_topics(c,topics)
 for topic,_ in pairs(topics or {}) do put(c,topic,"",true) end
end
local function register(s,c,d,rec)
 if not current(s,c) then return end
 if rec.prefix~=c.prefix then rec.entities={};rec.colors={};rec.prefix=c.prefix end
 local old=d:get_field("st_direct_discovery")
 if type(old)=="table" and old.prefix==c.prefix and type(old.topics)=="table" then
  for _,t in ipairs(old.topics) do
   if owned_topic(c,d,t) then rec.previous=rec.previous or {};rec.previous[t]=true end
  end
 end
 if not exported(d) then
  put(c,c.prefix.."/"..d.id.."/available","offline")
  remove_topics(c,rec.entities);remove_topics(c,rec.previous);rec.entities={};rec.previous=nil;d:set_field("st_direct_discovery",{prefix=c.prefix,topics={}},{persist=true});return
 end
 local next_entities=describe(s,c,d,rec)
 for t in pairs(rec.entities or {}) do if not next_entities[t] then put(c,t,"") end end
 for t in pairs(rec.previous or {}) do if not next_entities[t] then put(c,t,"") end end
 rec.previous=nil;rec.entities=next_entities
 for t,e in pairs(next_entities) do
  if s.tombstones[c.prefix] then s.tombstones[c.prefix][t]=nil end
  put(c,t,json.encode(e.config))
  if e.config.state_topic==e.base.."/state/radar_dp" then
   put(c,e.config.state_topic,rec.radar_state or "No report received")
  end
 end
 local topics={};for t in pairs(next_entities) do topics[#topics+1]=t end;table.sort(topics)
 local prior=d:get_field("st_direct_discovery")
 if type(prior)~="table" or prior.prefix~=c.prefix or table.concat(prior.topics or {},"|")~=table.concat(topics,"|") then d:set_field("st_direct_discovery",{prefix=c.prefix,topics=topics},{persist=true}) end
end
local function update_state(s,c,d,rec,component,cap,attr,value,unit)
 if not current(s,c) or not exported(d) or s.devices[d.id]~=rec then return end
 for _,e in pairs(rec.entities or {}) do
  if e.component==component then
   if cap=="button" and attr=="button" and e.config.state_topic and e.config.device_class=="button" then
    local v=model.state("button",value)
    if v and #c.events<128 then c.events[#c.events+1]={topic=e.base.."/state/button",value=json.encode({event_type=v}),id=d.id} end
   end
   for field,spec in pairs(e.reads) do
    if spec[1]==cap and spec[2]==attr then
     if field=="hue" or field=="saturation" then
      rec.colors[component]=rec.colors[component] or {}
      local color=rec.colors[component];color[field]=model.num(value,0,100)
      if color.hue and color.saturation then put(c,e.base.."/state/hs",string.format("%.3f,%.3f",color.hue*3.6,color.saturation)) end
     else
      local v=model.state(field,value,unit)
      if v~=nil then put(c,e.base.."/state/"..field,v)
      elseif field=="shade" and value=="unknown" then put(c,e.base.."/state/shade","None") end
     end
    end
   end
  end
 end
end
local function snapshot(s,c,d,rec)
 if not current(s,c) or s.devices[d.id]~=rec or not exported(d) then return end
 for _,e in pairs(rec.entities or {}) do
  for _,spec in pairs(e.reads) do
   local v,state=d:get_latest_state(e.component,spec[1],spec[2])
   if v~=nil then update_state(s,c,d,rec,e.component,spec[1],spec[2],v,type(state)=="table" and state.unit or nil) end
  end
 end
end
local function refresh(s,c,d,rec,rebuild)
 if not current(s,c) then return end
 if rebuild then rec.rebuild_epoch=c.epoch end
 if rec.snapshot_pending==c.epoch then return end
 local epoch=c.epoch
 rec.snapshot_pending=epoch
 local ok=pcall(function() d.thread:queue_event(function()
  if rec.snapshot_pending==epoch then rec.snapshot_pending=nil end
  if not current(s,c) or c.epoch~=epoch or s.devices[d.id]~=rec then return end
  protected(function()
   if rec.rebuild_epoch==epoch then
    register(s,c,d,rec)
    rec.rebuild_epoch=nil
   end
   snapshot(s,c,d,rec)
   if exported(d) and next(rec.entities) then put(c,c.prefix.."/"..d.id.."/available","online") end
  end)
 end) end)
 if not ok and rec.snapshot_pending==epoch then rec.snapshot_pending=nil end
end
local function hook_device(s,d,rec)
 -- The SDK routes main and component events through this method. Device objects
 -- are read-only; extend_device installs the override on this instance.
 local original=d.emit_component_event
 if type(original)~="function" or type(d.extend_device)~="function" then return false end
 local function emit(self,...)
  local result=table.pack(original(self,...))
  local event=result[1]
  if type(event)=="table" and type(event.state)=="table" then
   protected(function()
    local c=s.session
    if c and current(s,c) then
     update_state(s,c,d,rec,event.component_id,event.capability_id,event.attribute_id,event.state.value,event.state.unit)
    end
   end)
  end
  return table.unpack(result,1,result.n)
 end
 return pcall(d.extend_device,d,"emit_component_event",emit)
end
local function incoming(s,c,t,payload,retained)
 if retained or not current(s,c) then return end
 if t=="homeassistant/status" then
  if payload=="online" then for _,rec in pairs(s.devices) do refresh(s,c,rec.device,rec,true) end end
  return
 end
 if t:sub(1,#c.prefix+1)~=c.prefix.."/" then return end
 local id,component,field=t:sub(#c.prefix+2):match("^([^/]+)/([^/]+)/cmd/([^/]+)$")
 if not id or not model.safe_token(component) then return end
 local rec=s.devices[id];local d=rec and rec.device
 if not d or not exported(d) then return end
 local supported=false
 for _,e in pairs(rec.entities or {}) do if e.component==component and e.commands[field] then supported=true;break end end
 if not supported then return end
 local expires=socket.gettime()+2;local epoch=c.epoch
 d.thread:queue_event(function()
  if socket.gettime()>expires or not current(s,c) or c.epoch~=epoch or s.devices[id]~=rec or not exported(d) then return end
  protected(function()
   local comp=d.profile.components[component]
   if not comp then return end
   local cmd=model.command(caps_of(comp),s.handlers,field,payload)
   if not cmd then return end
   if cmd.command=="pause" then
    local allowed=d:get_latest_state(component,"windowShade","supportedWindowShadeCommands")
    if type(allowed)=="table" and #allowed>0 then
     local found=false;for _,v in ipairs(allowed) do if v=="pause" then found=true end end
     if not found then return end
    end
   end
   cmd.component=component
   if s.inject then
    -- The SDK resolves the actual matching subdriver and translates named_args.
    local owned=false
    for _,known in ipairs(s.driver:get_devices()) do if known.id==d.id then owned=true;break end end
    if not owned then return end
    local dispatch=s.driver.capability_dispatcher
    if dispatch and type(dispatch.can_handle)=="function" then
     local can=dispatch:can_handle(s.driver,d,cmd)
     if not can then return end
    end
    s.driver:inject_capability_command(d,{capability=cmd.capability,command=cmd.command,component=component,named_args=cmd.args})
   else s.handlers[cmd.capability][cmd.command](s.driver,d,cmd) end
  end)
 end)
end
local function send_pending(c,sock)
 local n=0
 -- Publish discovery and state before per-device online. Offline flags are highest priority.
 for priority=1,3 do
  for t,m in pairs(c.pending) do
   local is_avail=t:sub(-10)=="/available"
   local p=is_avail and (m.value=="offline" and 1 or 3) or 2
   if p==priority and n<24 then
    transport.send(sock,wire.publish(t,m.value,m.retain))
    if c.pending[t]==m then c.pending[t]=nil end
    n=n+1
   end
  end
 end
 for _=1,math.min(#c.events,16) do
  local ev=table.remove(c.events,1);transport.send(sock,wire.publish(ev.topic,ev.value,false))
 end
end
local function run_session(s,c,sock)
 sock:settimeout(5);assert(sock:connect(c.config.host,c.config.port))
 if c.cancel then return end
 transport.send(sock,wire.connect(client_id(c.prefix),c.config.user,c.config.password,c.prefix.."/availability"))
 sock:settimeout(1)
 local buf,phase,deadline="",1,socket.gettime()+10
 local ping,pong,heartbeat,next_snapshot=0,nil,0,0
 while not c.cancel do
  if c.stopping then
   send_pending(c,sock)
   if not next(c.pending) or socket.gettime()>c.stop_deadline then c.cancel=true;break end
  end
  local data=transport.read(sock)
  if #data>0 then buf=buf..data else socket.sleep(0.02) end
  while true do
   local h,b,rest=wire.pop(buf)
   if not h then break end
   buf=rest
   if phase==1 then
    assert(h==0x20 and #b==2 and b:byte(1)==0 and b:byte(2)==0,"CONNACK")
    transport.send(sock,wire.subscribe(c.prefix.."/+/+/cmd/+","homeassistant/status"));phase=2;deadline=socket.gettime()+10
   elseif phase==2 then
    assert(h==0x90 and #b==4 and b:sub(1,2)==wire.u16(1) and b:byte(3)<=1 and b:byte(4)<=1,"SUBACK")
    phase=3;c.ready=true;c.was_ready=true
    -- Clear online flag before any snapshots and discovery. LWT covers sudden disconnects.
    transport.send(sock,wire.publish(c.prefix.."/availability","offline",true))
    for _,rec in pairs(s.devices) do
     transport.send(sock,wire.publish(c.prefix.."/"..rec.device.id.."/available","offline",true))
     refresh(s,c,rec.device,rec,true)
    end
    for t in pairs(s.tombstones[c.prefix] or {}) do put(c,t,"") end
    transport.send(sock,wire.publish(c.prefix.."/availability","online",true))
    ping=socket.gettime()+10;heartbeat=0;next_snapshot=socket.gettime()+30
    log.info("ST Direct MQTT connected")
   elseif math.floor(h/16)==3 then
    local t,v,id,retained=wire.decode_publish(h,b)
    local duplicate=false
    if id then
     local previous=c.received[id]
     duplicate=math.floor(h/8)%2==1 and previous and previous.topic==t and previous.payload==v
     if not duplicate then
      c.received[id]={topic=t,payload=v}
      c.received_order[#c.received_order+1]={id=id,value=c.received[id]}
      if #c.received_order>128 then local old=table.remove(c.received_order,1);if c.received[old.id]==old.value then c.received[old.id]=nil end end
     end
     transport.send(sock,wire.puback(id))
    end
    if not duplicate then protected(incoming,s,c,t,v,retained) end
   elseif h==0xD0 and #b==0 then pong=nil
   else error("unexpected packet") end
  end
  local now=socket.gettime()
  if phase~=3 then assert(now<deadline,"handshake timeout")
  else
   if now>=heartbeat then transport.send(sock,wire.publish(c.prefix.."/heartbeat",tostring(os.time()),false));heartbeat=now+15 end
   if pong and now>=pong then error("PINGRESP timeout") end
   if not pong and now>=ping then transport.send(sock,wire.frame(0xC0,""));pong=now+8;ping=now+10 end
   send_pending(c,sock)
   if now>=next_snapshot then
    for _,rec in pairs(s.devices) do refresh(s,c,rec.device,rec,false) end
    next_snapshot=now+30
   end
  end
 end
 if c.ready then transport.send(sock,wire.publish(c.prefix.."/availability","offline",true));transport.send(sock,wire.frame(0xE0,"")) end
end
local function run(s,c)
 local delay=1
 while not c.cancel and not c.stopping do
  c.ready=false;c.was_ready=false;c.pending={};c.events={};c.epoch={};c.received={};c.received_order={}
  local sock=socket.tcp()
  if sock then
   local ok=pcall(run_session,s,c,sock)
   pcall(function() sock:close() end)
   if not ok and not c.cancel then log.warn("ST Direct MQTT disconnected; reconnecting") end
   if c.stopping then c.cancel=true end
  end
  c.ready=false
  if c.was_ready then delay=1 end
  local until_time=socket.gettime()+delay
  while not c.cancel and socket.gettime()<until_time do socket.sleep(0.25) end
  delay=math.min(30,delay*2)
 end
end
local function reconfigure(s)
 local chosen,invalid=nil,false
 for _,rec in pairs(s.devices) do
  local p=config(rec.device)
  if p==false or (p and chosen and not same(p,chosen)) then invalid=true
  elseif p then chosen=p end
 end
 if invalid then chosen=nil;log.warn("ST Direct: invalid or conflicting MQTT settings; MQTT disabled") end
 if same(chosen,s.config) then return end
 s.config=chosen;s.generation=s.generation+1;local generation=s.generation
 if s.session then
  local old=s.session
  if old.ready then old.stopping=true;old.stop_deadline=socket.gettime()+3;old.events={} else old.cancel=true end
 end
 if not chosen then return end
 cosock.spawn(function()
  while s.worker do socket.sleep(0.25) end
  if generation~=s.generation then return end
  local c={config=chosen,prefix="st-direct/"..chosen.site.."/"..s.family,ready=false,pending={},events={}}
  s.worker=c;s.session=c
  local ok=pcall(run,s,c)
  if s.session==c then s.session=nil end
  s.worker=nil
  if not ok then log.warn("ST Direct worker ended") end
 end,"st-direct-mqtt")
end
local function track(s,driver,d)
 if not trackable(s,d) then return end
 s.driver=driver
 local rec=s.devices[d.id]
 if not rec or rec.device~=d then
  rec={device=d,entities={},colors={}}
  s.devices[d.id]=rec;rec.hook=hook_device(s,d,rec)
  if not rec.hook then log.warn("ST Direct: event hook unavailable; using cached-state snapshots (buttons disabled)") end
 end
 reconfigure(s)
 local c=s.session
 if c and current(s,c) then refresh(s,c,d,rec,true) end
end
local function removed(s,d)
 local rec=s.devices[d.id]
 if not rec then return end
 local c=s.session
 if c then
  local tomb=s.tombstones[c.prefix] or {};s.tombstones[c.prefix]=tomb
  if rec.prefix==c.prefix then for t in pairs(rec.entities) do tomb[t]=true;put(c,t,"") end end
  local old=d:get_field("st_direct_discovery")
  if type(old)=="table" and old.prefix==c.prefix then for _,t in ipairs(old.topics or {}) do if owned_topic(c,d,t) then tomb[t]=true;put(c,t,"") end end end
  put(c,c.prefix.."/"..d.id.."/available","offline")
  for i=#c.events,1,-1 do if c.events[i].id==d.id then table.remove(c.events,i) end end
 end
 s.devices[d.id]=nil;reconfigure(s)
end
function M.wrap(template,family)
 assert(model.safe_token(family))
 local s={family=family,handlers=template.capability_handlers,devices={},tombstones={},generation=0}
 -- Existing EF00 handlers remain authoritative; only inspect incoming reports.
 local cluster=template.zigbee_handlers and template.zigbee_handlers.cluster
 local ef00=cluster and cluster[0xEF00]
 if type(ef00)=="table" then
  for cmd in pairs(radar_commands) do
   local original=ef00[cmd]
   if type(original)=="function" then
    ef00[cmd]=function(driver,d,rx,...)
     protected(radar_report,s,d,rx)
     return original(driver,d,rx,...)
    end
    s.radar_capture=true
   end
  end
 end
 local life=template.lifecycle_handlers or {};template.lifecycle_handlers=life
 for _,name in ipairs({"init","added","driverSwitched","infoChanged"}) do
  local original=life[name]
  life[name]=function(driver,d,...)
   local result
   if original then result=table.pack(original(driver,d,...)) else result={n=0} end
   protected(track,s,driver,d)
   return table.unpack(result,1,result.n)
  end
 end
 local original=life.removed
 life.removed=function(driver,d,...)
  protected(removed,s,d)
  if original then return original(driver,d,...) end
 end
 return s
end
-- TS011F polling variant: cached snapshots cannot replace a physical ZCL read.
-- Keep this narrow: other TS011F variants and sleeping sensors may report normally.
local function poll_power(s,d,rec)
 if s.family~="st-zigbee-switch" or not rec or rec.power_pending or s.missing[d.id] then return end
 if type(d.parent_assigned_child_key)=="string" or type(d.get_manufacturer)~="function" or type(d.get_model)~="function" then return end
 if d:get_model()~="TS011F" or d:get_manufacturer()~="_TZ3000_5f43h46b" then return end
 local main=d.profile and d.profile.components and d.profile.components.main
 if not main or not caps_of(main).powerMeter then return end
 rec.power_pending=true
 local ok=pcall(function()
  d.thread:queue_event(function()
   rec.power_pending=nil
   if s.devices[d.id]~=rec or s.missing[d.id] then return end
   protected(function()
    local em=require("st.zigbee.zcl.clusters").ElectricalMeasurement
    if d:supports_server_cluster(em.ID) then
     d:send_to_component("main",em.attributes.ActivePower:read(d))
    end
   end)
  end)
 end)
 if not ok then rec.power_pending=nil end
end
-- SDK adapter deliberately does not replace lifecycle handlers or default/subdriver dispatch.
-- Poll only the local driver inventory; no cloud API. Missing devices are removed after two complete scans.
function M.attach(driver,family)
 assert(model.safe_token(family))
 assert(type(driver.inject_capability_command)=="function","SDK command injection unavailable")
 local supported={}
 local noop=function() end
 for cap,names in pairs({
  switch={"on","off"},switchLevel={"setLevel"},windowShade={"open","close","pause"},
  windowShadeLevel={"setShadeLevel"},colorControl={"setColor"},colorTemperature={"setColorTemperature"}
 }) do
  supported[cap]={};for _,name in ipairs(names) do supported[cap][name]=noop end
 end
 local s={family=family,handlers=supported,devices={},tombstones={},generation=0,inject=true,driver=driver,missing={},scan_busy=false}
 -- The SDK adapter may expose a dispatcher before run(). If it does not,
 -- keep the existing driver untouched and do not advertise the diagnostic.
 local dispatcher=driver.zigbee_message_dispatcher
 if dispatcher and type(dispatcher.dispatch)=="function" then
  local original=dispatcher.dispatch
  s.radar_capture=pcall(function()
   dispatcher.dispatch=function(self,drv,d,rx,...)
    protected(function()
     local cluster=rx and rx.address_header and rx.address_header.cluster
     if cluster and cluster.value==0xEF00 then radar_report(s,d,rx) end
    end)
    return original(self,drv,d,rx,...)
   end
  end)
 end
 local function signature(d)
  local p=d.preferences or {};local keys={}
  for k,comp in pairs(d.profile.components or {}) do
   local c=caps_of(comp);local names={};for name in pairs(c) do names[#names+1]=name end;table.sort(names)
   keys[#keys+1]=tostring(k)..":"..table.concat(names,",")
  end
  table.sort(keys)
  return table.concat(keys,";").."|"..tostring(d.profile.id).."|"..tostring(d.label).."|"..tostring(p.stMqttExport)
 end
 local function scan()
  local list=driver:get_devices()
  if type(list)~="table" then return end
  local seen={}
  for _,d in ipairs(list) do
   if trackable(s,d) then
    seen[d.id]=true;s.missing[d.id]=nil
    local rec=s.devices[d.id];local sig=signature(d)
    if not rec or rec.device~=d or rec.signature~=sig then
     local first=not rec or rec.device~=d
     track(s,driver,d)
     if s.devices[d.id] then
      s.devices[d.id].signature=sig
      if first then protected(poll_power,s,d,s.devices[d.id]) end
     end
    end
   end
  end
  local absent={}
  for id,rec in pairs(s.devices) do
   if not seen[id] then
    s.missing[id]=(s.missing[id] or 0)+1
    if s.missing[id]>=2 then absent[#absent+1]=rec.device end
   end
  end
  for _,d in ipairs(absent) do removed(s,d);s.missing[d.id]=nil end
  reconfigure(s)
 end
 driver:call_on_schedule(3,function() protected(scan) end,"st-direct-inventory")
 if family=="st-zigbee-switch" then
  driver:call_on_schedule(10,function()
   for _,rec in pairs(s.devices) do protected(poll_power,s,rec.device,rec) end
  end,"st-direct-ts011f-power")
 end
 return s
end
return M
