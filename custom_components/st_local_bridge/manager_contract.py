"""Pure, deterministic SmartThings rule and MQTT Discovery contract."""
from uuid import UUID
from math import isfinite

PREFIX = "stbridge/v1"
ENUMS = {
    "switch": ("switch","switch","switchReport",{"off":0,"on":1}),
    "shade": ("windowShade","windowShade","shadeReport",{"closed":0,"open":1,"opening":2,"closing":3,"partially open":4,"paused":5,"unknown":6}),
    "motion": ("motionSensor","motion","motionReport",{"inactive":0,"active":1}),
    "contact": ("contactSensor","contact","contactReport",{"closed":0,"open":1}),
    "presence": ("presenceSensor","presence","presenceReport",{"not present":0,"present":1}),
    "water": ("waterSensor","water","waterReport",{"dry":0,"wet":1}),
}
NUMBERS = {
    "brightness": ("switchLevel","level","levelReport",0,100),
    "position": ("windowShadeLevel","shadeLevel","positionReport",0,100),
    "humidity": ("relativeHumidityMeasurement","humidity","humidityReport",0,100),
    "battery": ("battery","battery","batteryReport",0,100),
    "temperature": ("temperatureMeasurement","temperature","temperatureReport",-460,10000),
}
BUTTONS = {"pushed":0,"held":1,"double":2}
# Ten components maximum; each field is distinguished by component + capability.
REPORT_TARGETS = {
    "switch":("reportA","switchLevel","setLevel"),"shade":("reportA","switchLevel","setLevel"),
    "temperature":("reportA","thermostatHeatingSetpoint","setHeatingSetpoint"),
    "humidity":("reportA","thermostatCoolingSetpoint","setCoolingSetpoint"),
    "battery":("reportA","audioVolume","setVolume"),
    "motion":("reportB","switchLevel","setLevel"),"contact":("reportB","audioVolume","setVolume"),
    "presence":("reportB","thermostatHeatingSetpoint","setHeatingSetpoint"),
    "water":("reportC","switchLevel","setLevel"),"button":("reportC","audioVolume","setVolume"),
    "brightness":("reportD","switchLevel","setLevel"),"position":("reportD","switchLevel","setLevel"),
}
REQUIRED_COMPONENTS = {"main","commandOn","commandOff","commandStop","sync","commandLevel","reportA","reportB","reportC","reportD"}

def uid(value):
    result = UUID(str(value))
    if result.int == 0:
        raise ValueError("Zero UUID")
    return str(result)

def root(manager):
    return f"{PREFIX}/{uid(manager)}"

def hub_id(d):
    return next((d.get(k,{}).get("hubId") for k in ("zigbee","zwave","matter","lan")
                 if isinstance(d.get(k),dict) and d[k].get("hubId")),None) or d.get("parentDeviceId")

def driver_id(d):
    return next((d.get(k,{}).get("driverId") for k in ("lan","zigbee","zwave","matter")
                 if isinstance(d.get(k),dict) and d[k].get("driverId")),None)

def components(d):
    return {c["id"]: {x["id"] for x in c.get("capabilities",[])} for c in d.get("components",[])}

def is_manager(d):
    lan = d.get("lan") or {}
    return d.get("type") == "LAN" and ((lan.get("deviceNetworkId") or lan.get("networkId") or d.get("deviceNetworkId")) == "stlb1-manager"
        or (d.get("name") == "ST Local Manager" and components(d)=={"main":{"refresh"}})
        or ((d.get("label") or "").startswith("ST Local Manager") and components(d)=={"main":{"refresh"}}))

def specs(d, status=None):
    """Exclude non-local/cloud/unsafe devices and unsupported secondary components."""
    if d.get("type") not in {"ZIGBEE","ZWAVE","MATTER","LAN"}:
        return []
    local = d.get("executionContext") == "LOCAL" or any(
        isinstance(d.get(k),dict) and d[k].get("executingLocally") is True for k in ("zigbee","zwave","matter","lan"))
    if not local:
        return []
    caps=components(d).get("main",set())
    if caps & {"lock","doorControl","garageDoorControl","valve","thermostatMode","alarm","smokeDetector"}:
        return []
    if "windowShade" in caps:
        fields=["shade","stop"]
        if "windowShadeLevel" in caps:
            fields.append("position")
    elif "switch" in caps:
        fields=["switch"]
        if "switchLevel" in caps:
            fields.append("brightness")
    else:
        fields=[]
    fields += [k for k,(cap,*_) in ENUMS.items() if k not in {"switch","shade"} and cap in caps]
    fields += [k for k,(cap,*_) in NUMBERS.items() if k not in {"brightness","position"} and cap in caps]
    if "button" in caps:
        fields.append("button")
    return fields

def operand(device, capability, attribute, component="main", trigger="Always"):
    return {"device":{"devices":[uid(device)],"component":component,"capability":capability,"attribute":attribute,"trigger":trigger}}

def command(device, capability, cmd, component="main", args=None):
    body={"component":component,"capability":capability,"command":cmd}
    if args is not None:
        body["arguments"]=args
    return {"command":{"devices":[uid(device)],"commands":[body]}}

def condition(op,left,right,actions):
    return {"if":{op:{"left":left,"right":right},"then":actions}}

def eq(left,value,actions):
    return condition("equals",left,{"string":value},actions)

def number_guard(device,cap,attr,component,minimum,maximum,trigger,actions):
    left=operand(device,cap,attr,component,trigger)
    # Always true for valid values, without changes edge-trigger semantics.
    return condition("greaterThanOrEquals",left,{"integer":minimum},[
        condition("lessThanOrEquals",operand(device,cap,attr,component,"Never"),{"integer":maximum},actions)])

def rule_name(proxy, suffix):
    return f"STLB1 {uid(proxy)} {suffix}"

def make_rules(physical,proxy,fields):
    physical,proxy=uid(physical),uid(proxy)
    if physical==proxy: raise ValueError("Physical and proxy must differ")
    fields=set(fields)
    if not fields or fields- (set(ENUMS)|set(NUMBERS)|{"stop","button"}) or {"switch","shade"}<=fields or ("stop" in fields and "shade" not in fields) or ("position" in fields and "shade" not in fields) or ("brightness" in fields and "switch" not in fields):
        raise ValueError("Unsupported field combination")
    rules=[]; sync=[]
    def add(suffix,action):
        rules.append({"name":rule_name(proxy,suffix),"actions":[action]})
    for field,(cap,attr,comp,values) in ENUMS.items():
        if field not in fields: continue
        for value,code in values.items():
            target,target_cap,target_cmd=REPORT_TARGETS[field]
            action=command(proxy,target_cap,target_cmd,target,[{"integer":code}])
            add(f"{field} {code}",eq(operand(physical,cap,attr),value,[action]))
            sync.append(eq(operand(physical,cap,attr,trigger="Never"),value,[action]))
    for field,(cap,attr,comp,lo,hi) in NUMBERS.items():
        if field not in fields: continue
        target,target_cap,target_cmd=REPORT_TARGETS[field]
        action=command(proxy,target_cap,target_cmd,target,[operand(physical,cap,attr,trigger="Never")])
        add(f"{field} report",number_guard(physical,cap,attr,"main",lo,hi,"Always",[action]))
        sync.append(number_guard(physical,cap,attr,"main",lo,hi,"Never",[action]))
    if "button" in fields:
        for value,code in BUTTONS.items():
            add(f"button {code}",eq(operand(physical,"button","button"),value,
                [command(proxy,"audioVolume","setVolume","reportC",[{"integer":code}])]))
    if sync:
        add("sync",eq(operand(proxy,"button","button","sync"),"pushed",sync))
    pairs=[]
    if "switch" in fields: pairs += [("commandOn","switch","on"),("commandOff","switch","off")]
    if "shade" in fields:
        pairs += [("commandOn","windowShade","open"),("commandOff","windowShade","close")]
        if "stop" in fields: pairs += [("commandStop","windowShade","pause")]
    for component,cap,cmd in pairs:
        add(f"command {cmd}",eq(operand(proxy,"button","button",component),"pushed",[command(physical,cap,cmd)]))
    for field,component,cap,cmd in (("brightness","commandLevel","switchLevel","setLevel"),("position","commandLevel","windowShadeLevel","setShadeLevel")):
        if field in fields:
            add(f"command {field}",number_guard(proxy,"switchLevel","level",component,0,100,"Always",
                [command(physical,cap,cmd,args=[operand(proxy,"switchLevel","level",component,"Never")])]))
    return rules

def discovery(manager, record):
    physical=uid(record["physical"]); fields=set(record["fields"])
    base=f"{root(manager)}/{physical}"
    device={"identifiers":[f"stlb1_{physical}"],"name":record["name"],"manufacturer":"SmartThings","model":record.get("model") or "Local Edge"}
    def cfg(field,platform,extra,availability=None,name=None):
        unique=f"stlb1_{physical}_{field}"
        topics=[{"topic":f"{root(manager)}/availability"}]
        for key in (availability or [field]):
            topics.append({"topic":f"{base}/{key}/available"})
        if field=="button": topics=topics[:1]
        data={"name":name,"unique_id":unique,"device":device,"availability":topics,"availability_mode":"all",**extra}
        return f"homeassistant/{platform}/{unique}/config",data
    result=[]
    if "switch" in fields:
        light="brightness" in fields or record.get("light",False)
        extra={"command_topic":f"{base}/cmd/switch","state_topic":f"{base}/switch/state","payload_on":"on","payload_off":"off","optimistic":False,"qos":1,"retain":False}
        if "brightness" in fields:
            extra.update(brightness_command_topic=f"{base}/cmd/brightness",brightness_state_topic=f"{base}/brightness/state",brightness_scale=100,on_command_type="first")
        result.append(cfg("switch","light" if light else "switch",extra))
    if "shade" in fields:
        extra={"command_topic":f"{base}/cmd/shade","state_topic":f"{base}/shade/state","payload_open":"OPEN","payload_close":"CLOSE","state_open":"open","state_closed":"closed","state_opening":"opening","state_closing":"closing","state_stopped":"stopped","optimistic":False,"qos":1,"retain":False,"device_class":"window"}
        if "stop" in fields: extra["payload_stop"]="STOP"
        else: extra["payload_stop"]=None
        if "position" in fields: extra.update(position_topic=f"{base}/position/state",set_position_topic=f"{base}/cmd/position")
        result.append(cfg("shade","cover",extra))
    for field,klass in (("motion","motion"),("contact","door"),("presence","presence"),("water","moisture")):
        if field in fields:
            result.append(cfg(field,"binary_sensor",{"device_class":klass,"state_topic":f"{base}/{field}/state","payload_on":"on","payload_off":"off"},name=field))
    for field,klass,unit in (("temperature","temperature",record.get("temperature_unit","°C")),("humidity","humidity","%"),("battery","battery","%")):
        if field in fields:
            result.append(cfg(field,"sensor",{"device_class":klass,"state_class":"measurement","state_topic":f"{base}/{field}/state","unit_of_measurement":unit},name=field))
    if "button" in fields:
        result.append(cfg("button","event",{"state_topic":f"{base}/button/state","event_types":list(BUTTONS),"device_class":"button"},name="Button"))
    return result
