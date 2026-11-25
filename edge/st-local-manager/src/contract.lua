local M = {}
M.manager_dni = "stlb1-manager"
M.proxy_prefix = "stlb1-"
M.buttons = {on="commandOn",off="commandOff",stop="commandStop",sync="sync"}
M.levels = {brightness="commandLevel",position="commandPosition"}
M.reports = {
  switchReport={field="switch",values={[0]="off",[1]="on"}},
  shadeReport={field="shade",values={[0]="closed",[1]="open",[2]="opening",[3]="closing",[4]="open",[5]="stopped",[6]="unknown"}},
  motionReport={field="motion",values={[0]="off",[1]="on"}},
  contactReport={field="contact",values={[0]="off",[1]="on"}},
  presenceReport={field="presence",values={[0]="off",[1]="on"}},
  waterReport={field="water",values={[0]="off",[1]="on"}},
  levelReport={field="brightness",min=0,max=100},
  positionReport={field="position",min=0,max=100},
  humidityReport={field="humidity",min=0,max=100},
  batteryReport={field="battery",min=0,max=100},
  temperatureReport={field="temperature",min=-460,max=10000},
  buttonReport={field="button",values={[0]="pushed",[1]="held",[2]="double"}}
}
M.fields = {}
for _, spec in pairs(M.reports) do M.fields[spec.field] = true end
function M.report(component, value)
  local spec = M.reports[component]
  if not spec or type(value)~="number" or value~=value then return nil end
  if spec.values then return spec.field, spec.values[value] end
  if value < spec.min or value > spec.max then return nil end
  return spec.field, tostring(value)
end
function M.command(field, value, spec)
  if field=="switch" and spec.switch then
    if value=="ON" then return "commandOn" elseif value=="OFF" then return "commandOff" end
  elseif field=="shade" and spec.shade then
    if value=="OPEN" then return "commandOn" elseif value=="CLOSE" then return "commandOff" elseif value=="STOP" and spec.stop then return "commandStop" end
  elseif M.levels[field] and spec[field] then
    local v=tonumber(value)
    if v and v>=0 and v<=100 and v%1==0 then return M.levels[field],v end
  end
end
return M
