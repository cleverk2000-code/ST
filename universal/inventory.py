#!/usr/bin/env python3
"""Read-only SmartThings inventory planner. Unknown drivers never get guessed/deployed."""
import argparse,json,re,subprocess
from pathlib import Path
WONJJ=re.compile(r"^(?:ef00-(?:covers|switch|lights|energy|meters|sensors|presence|pir-motion)|zcl-(?:plugs|switch|lights|covers|sensors|controls))(?:[a-z0-9-]*)-wonjj6768$")
CAT=json.loads((Path(__file__).parent/"catalog.json").read_text())
def items(x):return x if isinstance(x,list) else x.get("items",[])
def normal(s):return re.sub(r"[^a-z0-9]+","-",str(s or "").lower()).strip("-")
def plan(devices,drivers,custom=()):
    known={normal(k):("official",k) for k in CAT["official"]["packages"]}
    for c in custom:
        if c.get("installed_name"):known[normal(c["installed_name"])]=("custom",c["family"])
    indexed={x.get("driverId") or x.get("id"):x for x in drivers if x.get("driverId") or x.get("id")}
    result=[]
    for d in devices:
        if d.get("type")!="ZIGBEE":continue
        z=d.get("zigbee") or {};driver=indexed.get(z.get("driverId") or d.get("driverId"),{})
        name=driver.get("name") or driver.get("driverName") or z.get("driverName") or ""
        key=normal(name);found=known.get(key)
        if key.startswith("st-mqtt-"):method,package="already_mqtt",None
        elif found:method,package=found
        elif WONJJ.fullmatch(key):method,package="wonjj",key
        else:method,package="rules_or_review",None
        result.append({"device_id":d.get("deviceId"),"label":d.get("label") or d.get("name"),"driver_id":z.get("driverId"),"driver":name,"manufacturer":z.get("manufacturer"),"model":z.get("model"),"method":method,"package":package})
    return result
def cli(*args):
    p=subprocess.run(["smartthings",*args,"-j"],capture_output=True,text=True,encoding="utf-8",check=True,shell=False)
    raw=p.stdout.lstrip("\ufeff").strip()
    return [] if raw in ("","no items found") else items(json.loads(raw))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--devices",type=Path);p.add_argument("--drivers",type=Path);p.add_argument("--custom",type=Path);p.add_argument("--hub");p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.devices and a.drivers:
        ds=items(json.loads(a.devices.read_text(encoding="utf-8-sig")));dr=items(json.loads(a.drivers.read_text(encoding="utf-8-sig")))
    elif not a.devices and not a.drivers:
        ds=cli("devices");dr=cli("edge:drivers:installed",*(["-H",a.hub] if a.hub else []))
    else:p.error("Provide both saved JSON files or neither")
    if a.hub:ds=[d for d in ds if (d.get("zigbee") or {}).get("hubId")==a.hub or d.get("parentDeviceId")==a.hub]
    result=plan(ds,dr,json.loads(a.custom.read_text()) if a.custom else [])
    data=json.dumps(result,ensure_ascii=False,indent=2)
    if a.out:a.out.write_text(data,encoding="utf-8")
    else:print(data)
if __name__=="__main__":main()
