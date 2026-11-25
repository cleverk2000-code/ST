#!/usr/bin/env python3
"""Repair ST Direct MQTT generated metadata and inline preferences in an existing local build.
Validate every package before writing anything. Original vendor settings remain unchanged.
"""
import argparse,copy,json,os
from pathlib import Path
import build
direct=build.direct
def repair(root,check=False):
    root=root.resolve()
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8-sig"))
    if not isinstance(manifest,list) or not manifest:raise ValueError("Missing Universal manifest")
    names=[x["family"] for x in manifest]
    if len(set(names))!=len(names):raise ValueError("Duplicate package")
    expected={p["name"]:p for p in direct.PREFS}
    pending=[];count=0;errors=[];keys=set()
    for name in names:
        if not build.FAMILY.fullmatch(name):raise ValueError("Invalid family: "+name)
        pkg=root/name
        cfg=next((pkg/n for n in ("config.yml","config.yaml") if (pkg/n).is_file()),None)
        if not cfg:raise ValueError("Missing config: "+name)
        metadata=direct.read_yaml(cfg.read_text(encoding="utf-8-sig"))
        old_key="cleverk2000.st-direct."+name
        key=direct.package_key(name)
        if metadata.get("packageKey") not in (old_key,key) or not str(metadata.get("name","")).startswith("ST MQTT "):
            raise ValueError("Not an ST Direct package: "+name)
        updated=copy.deepcopy(metadata)
        updated["packageKey"]=key
        updated["name"]=direct.display_name(metadata["name"])
        direct.validate_config(updated,name)
        if key in keys:raise ValueError("Package key collision: "+name)
        keys.add(key)
        if updated!=metadata:
            if check:errors.append(name+": old package metadata")
            else:pending.append((cfg,direct.yaml.safe_dump(updated,sort_keys=False,allow_unicode=True)))
        print(f"{name}: packageKey={key} ({len(key)} characters)")
        profiles=sorted((pkg/"profiles").glob("*.y*ml"))
        if not profiles:raise ValueError("Missing profiles: "+name)
        for path in profiles:
            obj=direct.read_yaml(path.read_text(encoding="utf-8-sig"))
            prefs=obj.get("preferences",[])
            if not isinstance(prefs,list):raise ValueError("Invalid preferences: "+str(path))
            replacement=[]
            for p in prefs:
                if p.get("name") in expected:
                    new=copy.deepcopy(expected[p["name"]])
                    old=copy.deepcopy(p)
                    if old.get("name")=="stMqttMaster" and old.get("title")=="Use this device for driver MQTT settings":
                        old["title"]=new["title"]
                        if old.get("description")=="Use this device for driver MQTT settings":old["description"]=new["description"]
                    if old!=new:raise ValueError("Unexpected preference definition: "+str(path)+" / "+p["name"])
                    replacement.append(new)
                else:
                    replacement.append(p)
                    if "title" in p and (not isinstance(p["title"],str) or not 3<=len(p["title"])<=36):
                        errors.append(f"{name}/{path.name}: upstream title length: {p.get('name')}")
            direct.validate_mqtt_preferences(replacement)
            if replacement!=prefs:
                if check:errors.append(f"{name}/{path.name}: old MQTT preference")
                else:
                    obj["preferences"]=replacement
                    pending.append((path,direct.yaml.safe_dump(obj,sort_keys=False,allow_unicode=True,width=120)))
            count+=1
        print(f"{name}: {len(profiles)} profiles inspected")
    if errors:raise ValueError("\n".join(errors))
    for path,data in pending:
        tmp=path.with_suffix(path.suffix+".tmp")
        try:
            tmp.write_text(data,encoding="utf-8");os.replace(tmp,path)
        finally:tmp.unlink(missing_ok=True)
    print(f"PASS: {len(names)} packages, {count} profiles; {len(pending)} repaired")
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("root",type=Path);p.add_argument("--check",action="store_true")
    a=p.parse_args();repair(a.root,a.check)
if __name__=="__main__":main()
