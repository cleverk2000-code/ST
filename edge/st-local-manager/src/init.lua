local Driver = require "st.driver"
local cap = require "st.capabilities"
local cosock = require "cosock"
local socket = cosock.socket
local log = require "log"
local json = require "st.json"
local wire = require "wire"
local transport = require "transport"
local C = require "contract"
local ctx, worker, generation = nil, nil, 0
local pending_create, pending_discovery = {}, 0
local driver

local function physical(d)
  local dni = d.device_network_id or ""
  return wire.uuid(dni:match("^stlb1%-(.+)$"))
end
local function proxies()
  local result={}
  for _,d in ipairs(driver:get_devices()) do
    local id=physical(d)
    if id then result[id]=d end
  end
  return result
end
local function active(d)
  local value=d:get_field("stlb1_active")
  return type(value)=="table" and value or nil
end
local function base(c,id)
  return c.prefix .. "/" .. id
end
local function queue(c, topic, value, retain)
  -- State messages are coalesced; never queue physical commands.
  c.queue[topic]={value=tostring(value),retain=retain==true}
end
local function button(d, component)
  local comp=d.profile.components[component]
  if comp then d:emit_component_event(comp,cap.button.button.pushed({state_change=true})) end
end
local function invalidate(c,id,spec)
  for field,v in pairs(spec) do
    if C.fields[field] and v then queue(c,base(c,id).."/"..field.."/available","offline",true) end
  end
end
local function request_sync(c,id,d)
  if active(d) then button(d,"sync") end
end
local function inventory()
  local result={}
  for id,d in pairs(proxies()) do
    result[id]={proxy=d.id,active=active(d)~=nil}
  end
  return result
end
local function create_proxy(id)
  if proxies()[id] then return end
  local now=socket.gettime()
  if pending_create[id] and now-pending_create[id]<25 then return end
  local n=0
  for _ in pairs(proxies()) do n=n+1 end
  for key,t in pairs(pending_create) do
    if now-t<25 then n=n+1 else pending_create[key]=nil end
  end
  if n>=64 then error("proxy limit") end
  pending_create[id]=now
  driver:try_create_device({type="LAN",device_network_id=C.proxy_prefix..id,
    label="ST Bridge "..id:sub(1,8),profile="proxy",manufacturer="ST Local Bridge",model="1.0"})
end
local function normalize_fields(fields)
  if type(fields)~="table" then error("fields missing") end
  local spec={}
  for _,field in ipairs(fields) do
    if not C.fields[field] and field~="stop" then error("invalid field") end
    spec[field]=true
  end
  if not next(spec) or (spec.stop and not spec.shade) or (spec.switch and spec.shade) or (spec.position and not spec.shade) or (spec.brightness and not spec.switch) then error("invalid fields") end
  return spec
end
local function control(c,payload)
  if #payload>8192 then return end
  local ok,msg=pcall(json.decode,payload)
  if not ok or type(msg)~="table" or not wire.uuid(msg.request) then return end
  local reply={request=msg.request,ok=false}
  local good,err=pcall(function()
    local id=wire.uuid(msg.physical)
    if msg.op=="inventory" then
      reply.devices=inventory()
    elseif msg.op=="create" and id then
      create_proxy(id)
    elseif msg.op=="activate" and id then
      local d=assert(proxies()[id],"proxy missing")
      local spec=normalize_fields(msg.fields)
      d:set_field("stlb1_active",spec,{persist=true})
      invalidate(c,id,spec)
      request_sync(c,id,d)
    elseif msg.op=="deactivate" and id then
      local d=proxies()[id]
      if d then
        local spec=active(d)
        if spec then
          for t in pairs(c.queue) do if t:sub(1,#base(c,id)+1)==base(c,id).."/" then c.queue[t]=nil end end
          invalidate(c,id,spec)
        end
        d:set_field("stlb1_active",nil,{persist=true})
      end
    elseif msg.op=="sync" and id then
      local d=assert(proxies()[id],"proxy missing")
      request_sync(c,id,d)
    else error("unknown operation") end
  end)
  reply.ok=good
  if not good then reply.error="operation rejected";log.warn("Manager control operation rejected") end
  queue(c,c.prefix.."/reply/"..msg.request,json.encode(reply),false)
end
local function incoming(c,topic,payload,retained)
  if retained then return end
  if topic==c.prefix.."/control" then control(c,payload);return end
  local relative=topic:sub(#c.prefix+2)
  if topic:sub(1,#c.prefix+1)~=c.prefix.."/" then return end
  local id,field=relative:match("^([^/]+)/cmd/([^/]+)$")
  id=wire.uuid(id)
  if not id or #payload>16 then return end
  local d=proxies()[id]
  local spec=d and active(d)
  if not spec then return end
  local component,v=C.command(field,payload,spec)
  if not component then return end
  if v then
    d:emit_component_event(d.profile.components[component],cap.switchLevel.level(v,{state_change=true}))
  else button(d,component) end
end
local function report(capability,d,command)
  local id=physical(d)
  local spec=id and active(d)
  if not spec or not ctx then return end
  local raw=command.args and (command.args.level or command.args.setpoint or command.args.volume)
  local field,value=C.report(command.component,capability,tonumber(raw),spec)
  if not field or not spec[field] or value==nil then return end
  if field=="button" then
    -- Event payload is never retained. Drop offline events instead of replaying.
    if ctx.ready and #ctx.events<64 then ctx.events[#ctx.events+1]={topic=base(ctx,id).."/button/state",value=json.encode({event_type=value})} end
    return
  end
  queue(ctx,base(ctx,id).."/"..field.."/state",value,true)
  queue(ctx,base(ctx,id).."/"..field.."/available",value=="unknown" and "offline" or "online",true)
end
local function config(d)
  local p=d.preferences or {}
  if not p.enabled or not wire.private_ipv4(p.brokerIp) or not p.mqttUser or p.mqttUser=="" or not p.mqttPassword or p.mqttPassword=="" then return nil end
  local port=tonumber(p.brokerPort)
  if not port or port<1 or port>65535 or port%1~=0 then return nil end
  return {host=p.brokerIp,port=port,user=p.mqttUser,password=p.mqttPassword}
end
local function current(c) return ctx==c and not c.cancel end
local function session(c,s)
  local p=c.config
  s:settimeout(5);assert(s:connect(p.host,p.port))
  if not current(c) then return end
  local raw=c.device.id:gsub("-","")
  transport.send(s,wire.connect("stlm-"..raw:sub(1,9)..raw:sub(-9),p.user,p.password,c.prefix.."/availability"))
  s:settimeout(1)
  local buf,phase,deadline="",1,socket.gettime()+10
  local ping,pong,heartbeat=0,nil,0
  while current(c) do
    local chunk=transport.read(s)
    if #chunk>0 then buf=buf..chunk else socket.sleep(0.02) end
    while true do
      local h,b,rest=wire.pop(buf)
      if not h then break end
      buf=rest
      if phase==1 then
        assert(h==0x20 and #b==2 and b:byte(1)==0 and b:byte(2)==0,"connack")
        transport.send(s,wire.subscribe(c.prefix.."/control",c.prefix.."/+/cmd/+"))
        phase=2;deadline=socket.gettime()+10
      elseif phase==2 then
        assert(h==0x90 and #b==4 and b:sub(1,2)==wire.u16(1) and b:byte(3)<=1 and b:byte(4)<=1,"suback")
        phase=3
        c.queue={};c.events={}
        -- Publish offline field flags before declaring manager online, preventing stale state.
        local ps=proxies()
        for id,d in pairs(ps) do local spec=active(d);if spec then invalidate(c,id,spec) end end
        for t,m in pairs(c.queue) do transport.send(s,wire.publish(t,m.value,m.retain)) end
        c.queue={}
        transport.send(s,wire.publish(c.prefix.."/availability","online",true))
        c.ready=true;c.was_ready=true
        for id,d in pairs(ps) do request_sync(c,id,d) end
        ping=socket.gettime()+10;heartbeat=0
        log.info("ST Local Manager MQTT ready")
      elseif math.floor(h/16)==3 then
        local t,v,id,retained=wire.decode_publish(h,b)
        -- ACK first: QoS1 commands may duplicate, all physical commands are absolute except pause.
        if id then transport.send(s,wire.puback(id)) end
        local ok=pcall(incoming,c,t,v,retained)
        if not ok then log.warn("Manager ignored invalid command") end
      elseif h==0xD0 and #b==0 then pong=nil
      else error("unexpected packet") end
    end
    local now=socket.gettime()
    if phase~=3 then assert(now<deadline,"handshake timeout")
    else
      -- Send retained state before online flag for each field; replies and events last.
      for _,suffix in ipairs({"/state","/available","other"}) do
        for t,m in pairs(c.queue) do
          local match=t:sub(-#suffix)==suffix
          if suffix=="other" then match=t:sub(-6)~="/state" and t:sub(-10)~="/available" end
          if match then
            transport.send(s,wire.publish(t,m.value,m.retain))
            if c.queue[t]==m then c.queue[t]=nil end
          end
        end
      end
      while #c.events>0 do
        local event=table.remove(c.events,1);transport.send(s,wire.publish(event.topic,event.value,false))
      end
      if now>=heartbeat then
        transport.send(s,wire.publish(c.prefix.."/heartbeat",tostring(os.time()),false));heartbeat=now+15
      end
      if pong and now>=pong then error("ping timeout") end
      if not pong and now>=ping then
        transport.send(s,wire.frame(0xC0,""));pong=now+8;ping=now+10
      end
    end
  end
  if c.ready then
    transport.send(s,wire.publish(c.prefix.."/availability","offline",true))
    transport.send(s,wire.frame(0xE0,""))
  end
end
local function loop(c)
  local delay=1
  while current(c) do
    c.ready=false;c.was_ready=false
    local s=socket.tcp()
    if s then
      local ok=pcall(session,c,s);pcall(function() s:close() end)
      if not ok and current(c) then log.warn("ST Local Manager session ended; reconnecting") end
    end
    c.ready=false;c.queue={};c.events={}
    if c.was_ready then delay=1 end
    local until_time=socket.gettime()+delay
    while current(c) and socket.gettime()<until_time do socket.sleep(0.25) end
    delay=math.min(delay*2,30)
  end
end
local function restart(d)
  if d.device_network_id~=C.manager_dni then return end
  generation=generation+1
  local g=generation
  if ctx then ctx.cancel=true end
  ctx=nil
  local p=config(d)
  if not p then return end
  cosock.spawn(function()
    while worker do socket.sleep(0.25) end
    if g~=generation then return end
    local c={device=d,config=p,prefix="stbridge/v1/"..d.id,queue={},events={}}
    ctx=c;worker=c
    local ok=pcall(loop,c)
    if worker==c then worker=nil end
    if ctx==c then ctx=nil end
    if not ok then log.warn("ST Local Manager worker ended") end
  end,"stlb-manager")
end
local function discovery(drv,_,should_continue)
  for _,d in ipairs(drv:get_devices()) do if d.device_network_id==C.manager_dni then return end end
  local now=socket.gettime()
  if now<pending_discovery then return end
  pending_discovery=now+30
  drv:try_create_device({type="LAN",device_network_id=C.manager_dni,label="ST Local Manager",
    profile="manager",manufacturer="ST Local Bridge",model="1.0"})
end
local function added(_,d)
  local id=physical(d)
  if id then
    pending_create[id]=nil
    for _,comp in pairs(C.buttons) do
      local c=d.profile.components[comp]
      d:emit_component_event(c,cap.button.supportedButtonValues({"pushed"}))
      d:emit_component_event(c,cap.button.numberOfButtons(1))
    end
  end
end
local function info_changed(_,d,_,args)
  if d.device_network_id~=C.manager_dni then return end
  local before=args and args.old_st_store and args.old_st_store.preferences or {}
  local after=d.preferences or {}
  for _,k in ipairs({"brokerIp","brokerPort","mqttUser","mqttPassword","enabled"}) do if before[k]~=after[k] then restart(d);return end end
end
local function removed(_,d)
  if d.device_network_id==C.manager_dni then
    generation=generation+1;if ctx then ctx.cancel=true end;ctx=nil
  else
    local id=physical(d);local spec=active(d)
    if id and spec and ctx then invalidate(ctx,id,spec) end
  end
end
driver=Driver("st-local-manager",{
  discovery=discovery,
  lifecycle_handlers={added=added,init=function(_,d) restart(d) end,infoChanged=info_changed,removed=removed},
  capability_handlers={
    [cap.refresh.ID]={[cap.refresh.commands.refresh.NAME]=function(_,d) if physical(d) and ctx then request_sync(ctx,physical(d),d) else restart(d) end end},
    [cap.switchLevel.ID]={[cap.switchLevel.commands.setLevel.NAME]=function(_,d,c) report("switchLevel",d,c) end},
    [cap.audioVolume.ID]={[cap.audioVolume.commands.setVolume.NAME]=function(_,d,c) report("audioVolume",d,c) end},
    [cap.thermostatHeatingSetpoint.ID]={[cap.thermostatHeatingSetpoint.commands.setHeatingSetpoint.NAME]=function(_,d,c) report("thermostatHeatingSetpoint",d,c) end},
    [cap.thermostatCoolingSetpoint.ID]={[cap.thermostatCoolingSetpoint.commands.setCoolingSetpoint.NAME]=function(_,d,c) report("thermostatCoolingSetpoint",d,c) end}
  }
})
driver:run()
