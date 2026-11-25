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
local function child(d) return type(d.parent_assigned_child_key)=="string" end
local function caps_of(comp)
 local caps={}
 for k,v in pairs(comp.capabilities or {}) do
  if type(v)=="table" and v.id then caps[v.id]=true elseif type(k)=="string" then caps[k]=true end
 end
 return caps
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
local function describe(s,c,d,rec)
 local out={}
 for key,comp in pairs(d.profile.components or {}) do
  local id=comp.id or key
  if model.safe_token(id) then
   local caps=caps_of(comp)
   local entities=model.describe(c.prefix,d.id,id,d.label or d.name or d.id,d:get_manufacturer(),d:get_model(),caps,s.handlers,rec.hook,category(comp))
   for _,e in pairs(entities) do out[e.topic]=e;e.component=id;e.caps=caps end
  end
 end
 return out
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
   if type(t)=="string" and t:match("^homeassistant/[%w_]+/std_") then rec.previous=rec.previous or {};rec.previous[t]=true end
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
 if not current(s,c) or rec.snapshot_pending==c.epoch then return end
 local epoch=c.epoch
 rec.snapshot_pending=epoch
 local ok=pcall(function() d.thread:queue_event(function()
  if rec.snapshot_pending==epoch then rec.snapshot_pending=nil end
  if not current(s,c) or c.epoch~=epoch or s.devices[d.id]~=rec then return end
  protected(function()
   if rebuild then register(s,c,d,rec) end
   snapshot(s,c,d,rec)
   if exported(d) and next(rec.entities) then put(c,c.prefix.."/"..d.id.."/available","online") end
  end)
 end) end)
 if not ok and rec.snapshot_pending==epoch then rec.snapshot_pending=nil end
end
local function hook_device(s,d,rec)
 -- Hook only this device instance; preserve original results/errors. Nested emit_event -> emit_component_event is counted once.
 local old_main,old_component=d.emit_event,d.emit_component_event
 if type(old_main)~="function" or type(old_component)~="function" then return false end
 local depth=0
 local function wrap(original,component_form)
  return function(self,...)
   local argv=table.pack(...)
   depth=depth+1
   local result=table.pack(pcall(original,self,table.unpack(argv,1,argv.n)))
   depth=depth-1
   if not result[1] then error(result[2],0) end
   if depth==0 then protected(function()
    local c=s.session
    if not c or not current(s,c) then return end
    local fallback=component_form and argv[2] or argv[1]
    local ev=type(result[2])=="table" and result[2] or fallback
    if type(ev)~="table" then return end
    local comp=ev.component_id or (component_form and type(argv[1])=="table" and argv[1].id) or "main"
    local state=ev.state
    if type(state)~="table" or state.value==nil then return end
    update_state(s,c,d,rec,comp,ev.capability_id,ev.attribute_id,state.value,state.unit)
   end) end
   return table.unpack(result,2,result.n)
  end
 end
 local ok=pcall(function()
  d.emit_component_event=wrap(old_component,true);d.emit_event=wrap(old_main,false)
 end)
 if not ok then pcall(function() d.emit_component_event=old_component;d.emit_event=old_main end) end
 return ok
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
   s.handlers[cmd.capability][cmd.command](s.driver,d,cmd)
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
    if id then transport.send(sock,wire.puback(id)) end
    protected(incoming,s,c,t,v,retained)
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
  c.ready=false;c.was_ready=false;c.pending={};c.events={};c.epoch={}
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
 if child(d) or not model.safe_token(d.id) then return end
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
  if type(old)=="table" and old.prefix==c.prefix then for _,t in ipairs(old.topics or {}) do if type(t)=="string" and t:match("^homeassistant/[%w_]+/std_") then tomb[t]=true;put(c,t,"") end end end
  put(c,c.prefix.."/"..d.id.."/available","offline")
  for i=#c.events,1,-1 do if c.events[i].id==d.id then table.remove(c.events,i) end end
 end
 s.devices[d.id]=nil;reconfigure(s)
end
function M.wrap(template,family)
 assert(model.safe_token(family))
 local s={family=family,handlers=template.capability_handlers,devices={},tombstones={},generation=0}
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
return M
