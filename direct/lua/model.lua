-- MQTT contract; no SmartThings SDK dependencies. All commands are allowlisted.
local M={}
M.sensors={
 temperature={"temperatureMeasurement","temperature","temperature","°C","measurement"},
 humidity={"relativeHumidityMeasurement","humidity","humidity","%","measurement"},
 battery={"battery","battery","battery","%","measurement"},
 power={"powerMeter","power","power","W","measurement"},
 energy={"energyMeter","energy","energy","kWh","total_increasing"},
 voltage={"voltageMeasurement","voltage","voltage","V","measurement"},
 current={"currentMeasurement","current","current","A","measurement"},
 illuminance={"illuminanceMeasurement","illuminance","illuminance","lx","measurement"},
}
M.binary={
 motion={"motionSensor","motion","motion","active","inactive"},
 contact={"contactSensor","contact","door","open","closed"},
 presence={"presenceSensor","presence","presence","present","not present"},
 water={"waterSensor","water","moisture","wet","dry"},
}
M.button_types={"pushed","held","double","pushed_2x","pushed_3x","pushed_4x","pushed_5x","pushed_6x","down","up","held_down","held_up"}
local button_set={}
for _,v in ipairs(M.button_types) do button_set[v]=true end
local unsafe={lock=true,doorControl=true,garageDoorControl=true,valve=true,thermostatMode=true,thermostatHeatingSetpoint=true,thermostatCoolingSetpoint=true,alarm=true,ovenMode=true,securitySystem=true,gasDetector=true,smokeDetector=true}
function M.safe_token(s) return type(s)=="string" and #s>0 and #s<=128 and s:match("^[%w_-]+$")~=nil end
function M.num(v,lo,hi)
 if type(v)~="number" or v~=v or v==math.huge or v==-math.huge or v<lo or v>hi then return nil end
 return v
end
local function integer(v,lo,hi)
 v=tonumber(v)
 if not M.num(v,lo,hi) or v%1~=0 then return nil end
 return v
end
function M.numeric(field,v,unit)
 if not M.num(v,-1e12,1e12) then return nil end
 if field=="temperature" then
  if unit=="F" or unit=="°F" then v=(v-32)*5/9
  elseif unit~=nil and unit~="C" and unit~="°C" then return nil end
  return M.num(v,-273.15,1000)
 end
 local spec=M.sensors[field]
 if not spec then return nil end
 local target=spec[4]
 if unit and unit~=target then
  if field=="energy" and unit=="Wh" then v=v/1000
  elseif field=="power" and unit=="kW" then v=v*1000
  elseif field=="current" and unit=="mA" then v=v/1000
  elseif field=="voltage" and unit=="mV" then v=v/1000
  elseif field=="illuminance" and (unit=="lux" or unit=="LUX") then -- same SI unit as lx
  else return nil end
 end
 return M.num(v,(field=="power" or field=="current") and -1e9 or 0,(field=="humidity" or field=="battery") and 100 or 1e12)
end
function M.command(caps,handlers,field,payload)
 if type(payload)~="string" or #payload>64 then return nil end
 for cap in pairs(unsafe) do if caps[cap] then return nil end end
 local cap,cmd,args,pos
 if field=="switch" and not caps.windowShade then
  cap="switch";cmd=({ON="on",OFF="off"})[payload]
 elseif field=="shade" then
  cap="windowShade";cmd=({OPEN="open",CLOSE="close",STOP="pause"})[payload]
 elseif field=="position" then
  local v=integer(payload,0,100);if not v then return nil end
  cap="windowShadeLevel";cmd="setShadeLevel";args={shadeLevel=v};pos={v}
 elseif field=="brightness" and not caps.windowShade then
  local v=integer(payload,0,100);if not v then return nil end
  cap="switchLevel";cmd="setLevel";args={level=v,rate=0};pos={v,0}
 elseif field=="color_temp" and caps.switch and not caps.windowShade then
  local v=integer(payload,2000,6500);if not v then return nil end
  cap="colorTemperature";cmd="setColorTemperature";args={temperature=v};pos={v}
 elseif field=="hs" and caps.switch and not caps.windowShade then
  local h,s=payload:match("^([%d%.]+),([%d%.]+)$")
  h,s=tonumber(h),tonumber(s)
  if not M.num(h,0,360) or not M.num(s,0,100) then return nil end
  local color={hue=h/3.6,saturation=s}
  cap="colorControl";cmd="setColor";args={color=color};pos={color}
 end
 if not cap or not cmd or not caps[cap] or not handlers[cap] or type(handlers[cap][cmd])~="function" then return nil end
 return {capability=cap,command=cmd,args=args or {},positional_args=pos or {}}
end
function M.state(field,value,unit)
 if M.sensors[field] then local v=M.numeric(field,value,unit);return v and tostring(v) or nil end
 local b=M.binary[field]
 if b then if value==b[4] then return "ON" elseif value==b[5] then return "OFF" end;return nil end
 if field=="switch" then return ({on="ON",off="OFF"})[value] end
 if field=="shade" then return ({closed="closed",open="open",opening="opening",closing="closing",["partially open"]="open",paused="stopped"})[value] end
 if field=="position" or field=="brightness" then local v=M.num(value,0,100);return v and tostring(math.floor(v+0.5)) or nil end
 if field=="color_temp" then local v=M.num(value,1000,20000);return v and tostring(math.floor(v+0.5)) or nil end
 if field=="button" and button_set[value] then return value end
end
function M.describe(prefix,id,component,label,manufacturer,model,caps,handlers,hook,category)
 if not M.safe_token(id) or not M.safe_token(component) then return {} end
 local entities={}
 local base=prefix.."/"..id.."/"..component
 local stable="std_"..prefix:gsub("/","_").."_"..id.."_"..component
 local device={identifiers={"std_"..prefix:gsub("/","_").."_"..id},name=label,manufacturer=manufacturer or "SmartThings",model=model or "Zigbee"}
 local function add(field,platform,config,reads,commands,name)
  config.unique_id=stable.."_"..field
  config.name=name or (component=="main" and field or component.." "..field)
  config.device=device
  config.availability={{topic=prefix.."/availability"},{topic=prefix.."/"..id.."/available"}}
  config.availability_mode="all"
  config.qos=1
  local topic="homeassistant/"..platform.."/"..config.unique_id.."/config"
  entities[field]={topic=topic,config=config,reads=reads or {},commands=commands or {},base=base}
 end
 local function handler(c,k) return caps[c] and handlers[c] and type(handlers[c][k])=="function" end
 local safe=true
 for c in pairs(unsafe) do if caps[c] then safe=false end end
 if safe and caps.windowShade and handler("windowShade","open") and handler("windowShade","close") then
  local cfg={command_topic=base.."/cmd/shade",state_topic=base.."/state/shade",payload_open="OPEN",payload_close="CLOSE",payload_stop=handler("windowShade","pause") and "STOP" or "",state_open="open",state_closed="closed",state_opening="opening",state_closing="closing",state_stopped="stopped",optimistic=false,retain=false,device_class="window"}
  local reads={shade={"windowShade","windowShade"}};local cmds={shade=true}
  if handler("windowShadeLevel","setShadeLevel") then
   cfg.position_topic=base.."/state/position";cfg.set_position_topic=base.."/cmd/position";reads.position={"windowShadeLevel","shadeLevel"};cmds.position=true
  end
  add("shade","cover",cfg,reads,cmds,"Window")
 elseif safe and not caps.windowShade and handler("switch","on") and handler("switch","off") then
  local light=category=="Light" or category=="LightBulb" or caps.colorControl or caps.colorTemperature or (caps.switchLevel and category~="SmartPlug" and category~="Outlet")
  local cfg={command_topic=base.."/cmd/switch",state_topic=base.."/state/switch",payload_on="ON",payload_off="OFF",optimistic=false,retain=false}
  local reads={switch={"switch","switch"}};local cmds={switch=true}
  if light and handler("switchLevel","setLevel") then
   cfg.brightness_command_topic=base.."/cmd/brightness";cfg.brightness_state_topic=base.."/state/brightness";cfg.brightness_scale=100;cfg.on_command_type="first";reads.brightness={"switchLevel","level"};cmds.brightness=true
  end
  if light and handler("colorTemperature","setColorTemperature") then
   cfg.color_temp_command_topic=base.."/cmd/color_temp";cfg.color_temp_state_topic=base.."/state/color_temp";cfg.color_temp_kelvin=true;cfg.min_kelvin=2000;cfg.max_kelvin=6500;reads.color_temp={"colorTemperature","colorTemperature"};cmds.color_temp=true
  end
  if light and handler("colorControl","setColor") then
   cfg.hs_command_topic=base.."/cmd/hs";cfg.hs_state_topic=base.."/state/hs";reads.hue={"colorControl","hue"};reads.saturation={"colorControl","saturation"};cmds.hs=true
  end
  add("switch",light and "light" or "switch",cfg,reads,cmds,light and "Light" or "Switch")
 end
 for field,s in pairs(M.sensors) do
  if caps[s[1]] then add(field,"sensor",{state_topic=base.."/state/"..field,device_class=s[3],unit_of_measurement=s[4],state_class=s[5],entity_category=field=="battery" and "diagnostic" or nil},{[field]={s[1],s[2]}},nil,field) end
 end
 for field,b in pairs(M.binary) do
  if caps[b[1]] then add(field,"binary_sensor",{state_topic=base.."/state/"..field,device_class=b[3],payload_on="ON",payload_off="OFF"},{[field]={b[1],b[2]}},nil,field) end
 end
 if caps.stRadarDiagnostic then
  add("radar_dp","sensor",{state_topic=base.."/state/radar_dp",json_attributes_topic=base.."/state/radar_dp_attributes",entity_category="diagnostic",icon="mdi:radar"},nil,nil,"Radar DP report")
 end
 if caps.stRadarQuery then
  add("radar_query","button",{command_topic=base.."/cmd/radar_query",payload_press="PRESS",retain=false,entity_category="diagnostic",icon="mdi:refresh"},nil,{radar_query=true},"Radar query all DP")
 end
 if caps.button and hook then
  add("button","event",{state_topic=base.."/state/button",event_types=M.button_types,device_class="button"},nil,nil,"Button")
 end
 return entities
end
return M
