local Driver = require "st.driver"
local cap = require "st.capabilities"
local cosock = require "cosock"
local socket = cosock.socket
local log = require "log"
local wire = require "wire"
local contexts = {}
local workers = {}
local pending_discovery = 0

local transport = require "transport"
local send = transport.send

local function discovery(driver, _, should_continue)
  local now = socket.gettime()
  if now < pending_discovery then return end
  local occupied = {}
  for _, dev in ipairs(driver:get_devices()) do
    occupied[dev.device_network_id] = true
    -- Only one unconfigured bridge at a time.
    if not wire.uuid(dev.preferences and dev.preferences.physicalId) then return end
  end
  for i = 1, 16 do
    local dni = "cleverk-st-local-" .. i
    if not occupied[dni] then
      pending_discovery = now + 30
      driver:try_create_device({
        type = "LAN", device_network_id = dni, label = "ST Local Edge " .. i,
        profile = "bridge-v3", manufacturer = "ST Local Bridge", model = "0.3.0"
      })
      return
    end
  end
end

local function config(driver, device)
  local p = device.preferences or {}
  local id = wire.uuid(p.physicalId)
  local port = tonumber(p.brokerPort)
  if not p.enabled or not id or not wire.private_ipv4(p.brokerIp)
    or not port or port < 1 or port > 65535 or port % 1 ~= 0
    or type(p.mqttUser) ~= "string" or p.mqttUser == ""
    or type(p.mqttPassword) ~= "string" or p.mqttPassword == "" then return nil end
  -- A physical UUID must never have two competing proxy connections.
  for _, other in ipairs(driver:get_devices()) do
    if other.id ~= device.id and other.preferences and other.preferences.enabled
      and wire.uuid(other.preferences.physicalId) == id then
      log.warn("Duplicate physical device UUID; disable duplicate proxy")
      return nil
    end
  end
  local cover = p.coverMode == true
  if cover and (not device.profile.components.commandStop or not device.profile.components.shadeReport) then
    log.warn("Cover mode requires bridge-v3 profile")
    return nil
  end
  return {id=id, host=p.brokerIp, port=port, user=p.mqttUser, password=p.mqttPassword, cover=cover}
end

local function current(ctx)
  return contexts[ctx.device.id] == ctx and not ctx.cancel
end

local function run_session(ctx, sock)
  local p, prefix = ctx.config, "st/local/" .. ctx.config.id
  local availability = prefix .. "/availability"
  local state_topic = prefix .. (p.cover and "/shade" or "/state")
  local subscriptions = {prefix .. "/on", prefix .. "/off"}
  if p.cover then subscriptions[#subscriptions+1] = prefix .. "/stop" end
  ctx.stage = "tcp_connect"
  sock:settimeout(5)
  assert(sock:connect(p.host, p.port), "tcp_connect_failed")
  if not current(ctx) then return end
  -- Client ID <= 23 characters, unique by proxy UUID prefix and suffix.
  local raw = ctx.device.id:gsub("-", "")
  ctx.stage = "connect_send"
  send(sock, wire.connect("stl-" .. raw:sub(1,10) .. raw:sub(-9), p.user, p.password, availability))
  ctx.stage = "connack"
  local buffer, phase, deadline = "", "connack", socket.gettime() + 8
  local next_ping, pong_deadline, next_heartbeat = 0, nil, 0
  sock:settimeout(1)
  while current(ctx) do
    local data = transport.read(sock)
    if #data > 0 then buffer = buffer .. data else socket.sleep(0.02) end
    while true do
      local h, body, remaining = wire.pop(buffer)
      if not h then break end
      buffer = remaining
      local kind = math.floor(h / 16)
      if phase == "connack" then
        assert(h == 0x20 and #body == 2 and body:byte(1) == 0 and body:byte(2) == 0, "CONNACK rejected")
        ctx.stage = "subscribe_send"
        send(sock, wire.subscribe(table.unpack(subscriptions)))
        phase, deadline = "suback", socket.gettime() + 8
        ctx.stage = "suback"
      elseif phase == "suback" then
        assert(h == 0x90 and #body == 2 + #subscriptions and body:sub(1,2) == wire.u16(1), "SUBACK rejected")
        for i=3,#body do assert(body:byte(i) <= 1, "SUBACK rejected") end
        phase = "ready"
        ctx.stage = "initial_publish"
        -- Clear retained state from a previous session; wait for a real report.
        send(sock, wire.publish(state_topic, "", true))
        send(sock, wire.publish(availability, "online", true))
        ctx.connected, ctx.ever_ready = true, true
        next_ping, next_heartbeat = socket.gettime() + 10, socket.gettime()
        ctx.stage = "ready"
        log.info("ST Local Edge 0.3.0 MQTT ready: " .. p.id)
      elseif kind == 3 then
        local topic, payload, id, retained = wire.decode_publish(h, body)
        local component = wire.command(prefix, topic, payload, retained, p.cover)
        if component and current(ctx) then
          ctx.device:emit_component_event(ctx.device.profile.components[component],
            cap.button.button.pushed({state_change=true}))
        end
        if id then send(sock, wire.puback(id)) end
      elseif h == 0xD0 and #body == 0 then
        pong_deadline = nil
      else
        error("unexpected MQTT packet")
      end
    end
    local now = socket.gettime()
    if phase ~= "ready" then
      assert(now < deadline, "MQTT handshake timeout")
    else
      if ctx.pending then
        local value = ctx.pending
        send(sock, wire.publish(state_topic, value, true))
        if ctx.pending == value then ctx.pending = nil end
      end
      if now >= next_heartbeat then
        send(sock, wire.publish(prefix .. "/heartbeat", tostring(os.time()), false))
        next_heartbeat = now + 15
      end
      if pong_deadline and now >= pong_deadline then error("PINGRESP timeout") end
      if not pong_deadline and now >= next_ping then
        send(sock, wire.frame(0xC0, ""))
        pong_deadline, next_ping = now + 8, now + 10
      end
    end
  end
  if ctx.connected then
    ctx.stage = "shutdown"
    send(sock, wire.publish(availability, "offline", true))
    send(sock, wire.frame(0xE0, ""))
  end
end

local function worker(ctx)
  local delay = 1
  while current(ctx) do
    ctx.connected, ctx.ever_ready = false, false
    ctx.stage = "socket_create"
    local sock = socket.tcp()
    if sock then
      local ok, err = pcall(run_session, ctx, sock)
      sock:close()
      if not ok and current(ctx) then
        -- Do not log credentials or raw MQTT packets.
        local reason = tostring(err)
        local known = {"short_write","send_timeout","send_closed","send_failed","invalid_read_type","receive_closed","receive_failed","tcp_connect_failed","CONNACK rejected","SUBACK rejected","MQTT handshake timeout","PINGRESP timeout","unexpected MQTT packet","packet too large","invalid remaining length"}
        local label = "runtime_error"
        for _, item in ipairs(known) do
          if reason:find(item, 1, true) then label = item; break end
        end
        local line = reason:match(":(%d+):") or "?"
        log.warn("ST Local Edge 0.3.0 MQTT failure stage=" .. tostring(ctx.stage) .. " reason=" .. label .. " line=" .. line .. "; retrying")
      end
    end
    ctx.connected = false
    if ctx.ever_ready then delay = 1 end
    if current(ctx) then
      local until_time = socket.gettime() + delay
      while current(ctx) and socket.gettime() < until_time do socket.sleep(0.25) end
      delay = math.min(delay * 2, 30)
    end
  end
  ctx.finished = true
end

local function stop(device)
  local old = contexts[device.id]
  if old then old.cancel = true; contexts[device.id] = nil end
  return workers[device.id]
end

local function start(driver, device)
  local old = stop(device)
  local p = config(driver, device)
  if not p then return end
  local ctx = {device=device, config=p, connected=false}
  contexts[device.id] = ctx
  workers[device.id] = ctx
  cosock.spawn(function()
    while old and not old.finished do socket.sleep(0.25) end
    if current(ctx) then worker(ctx) else ctx.finished = true end
    if workers[device.id] == ctx then workers[device.id] = nil end
  end, "stlocal-" .. device.id)
end

local function added(driver, device)
  for _, name in ipairs({"commandOn","commandOff","commandStop"}) do
    local comp = device.profile.components[name]
    if comp then
      device:emit_component_event(comp, cap.button.supportedButtonValues({"pushed"}))
      device:emit_component_event(comp, cap.button.numberOfButtons(1))
    end
  end
end

-- A Rule calls these commands after observing the PHYSICAL device.
-- They never emit command button events and cannot cause a command loop.
local function report(value)
  return function(_, device, command)
    if command.component ~= "main" then return end
    local ctx = contexts[device.id]
    if not ctx or ctx.config.cover then return end
    ctx.pending = value
    device:emit_event(cap.switch.switch[value]())
  end
end

local function shade_report(_, device, command)
  if command.component ~= "shadeReport" then return end
  local ctx = contexts[device.id]
  if not ctx or not ctx.config.cover then return end
  local level = tonumber(command.args.level)
  local state = wire.shade_state(level)
  if not state then return end
  ctx.pending = state
  device:emit_component_event(device.profile.components.shadeReport, cap.switchLevel.level(level))
end

local function refresh(driver, device)
  start(driver, device)
end

local function info_changed(driver, device, _, args)
  local before = args and args.old_st_store and args.old_st_store.preferences or {}
  local after = device.preferences or {}
  for _, key in ipairs({"brokerIp","brokerPort","mqttUser","mqttPassword","physicalId","enabled","coverMode"}) do
    if before[key] ~= after[key] then start(driver, device); return end
  end
end

local driver = Driver("st-local-edge", {
  discovery = discovery,
  lifecycle_handlers = {added=added, init=start, infoChanged=info_changed, removed=function(_,d) stop(d) end},
  capability_handlers = {
    [cap.switch.ID] = {[cap.switch.commands.on.NAME]=report("on"), [cap.switch.commands.off.NAME]=report("off")},
    [cap.switchLevel.ID] = {[cap.switchLevel.commands.setLevel.NAME]=shade_report},
    [cap.refresh.ID] = {[cap.refresh.commands.refresh.NAME]=refresh}
  }
})
driver:run()
