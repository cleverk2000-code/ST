local M = {}
M.manager_dni = "stlb1-manager"
M.proxy_prefix = "stlb1-"
M.buttons = {on="commandOn",off="commandOff",stop="commandStop",sync="sync"}
M.levels = {brightness="commandLevel",position="commandLevel"}
M.fields = {}
for _,v in ipairs({"switch","shade","motion","contact","presence","water","brightness","position","temperature","humidity","battery","button"}) do M.fields[v]=true end
local binary={[0]="off",[1]="on"}
local shade={[0]="closed",[1]="open",[2]="opening",[3]="closing",[4]="open",[5]="stopped",[6]="unknown"}
local events={[0]="pushed",[1]="held",[2]="double"}
function M.report(component, capability, value, spec)
  if type(value)~="number" or value~=value then return nil end
  local key=component.."/"..capability
  local field,values,min,max
  if key=="reportA/switchLevel" then
    if spec.shade then field,values="shade",shade else field,values="switch",binary end
  elseif key=="reportA/thermostatHeatingSetpoint" then field,min,max="temperature",-460,10000
  elseif key=="reportA/thermostatCoolingSetpoint" then field,min,max="humidity",0,100
  elseif key=="reportA/audioVolume" then field,min,max="battery",0,100
  elseif key=="reportB/switchLevel" then field,values="motion",binary
  elseif key=="reportB/audioVolume" then field,values="contact",binary
  elseif key=="reportB/thermostatHeatingSetpoint" then field,values="presence",binary
  elseif key=="reportC/switchLevel" then field,values="water",binary
  elseif key=="reportC/audioVolume" then field,values="button",events
  elseif key=="reportD/switchLevel" then
    field,min,max=spec.shade and "position" or "brightness",0,100
  else return nil end
  if not spec[field] then return nil end
  if values then
    if not values[value] then return nil end
    return field,values[value]
  end
  if value<min or value>max then return nil end
  return field,tostring(value)
end
function M.command(field,value,spec)
  if field=="switch" and spec.switch then
    if value=="ON" or value=="on" then return "commandOn"
    elseif value=="OFF" or value=="off" then return "commandOff" end
  elseif field=="shade" and spec.shade then
    if value=="OPEN" then return "commandOn"
    elseif value=="CLOSE" then return "commandOff"
    elseif value=="STOP" and spec.stop then return "commandStop" end
  elseif M.levels[field] and spec[field] then
    local v=tonumber(value)
    if v and v>=0 and v<=100 and v%1==0 then return M.levels[field],v end
  end
end
return M
