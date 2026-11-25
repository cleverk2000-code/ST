#!/usr/bin/env python3
"""Reproducible MQTT overlays for pinned MIT-licensed upstream Edge packages."""
import argparse, hashlib, json, os, re, shutil, sys, tempfile, urllib.request, zipfile
from pathlib import Path, PurePosixPath
import yaml

# PyYAML defaults to YAML 1.1: preserve unquoted on/off as strings, as in YAML 1.2.
class ProfileLoader(yaml.SafeLoader):
    pass
ProfileLoader.yaml_implicit_resolvers={k:[(tag,regex) for tag,regex in values if tag!="tag:yaml.org,2002:bool"] for k,values in yaml.SafeLoader.yaml_implicit_resolvers.items()}
ProfileLoader.add_implicit_resolver("tag:yaml.org,2002:bool",re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),list("tTfF"))
def read_yaml(data):return yaml.load(data,Loader=ProfileLoader)

ROOT=Path(__file__).resolve().parent
UPSTREAM="wonjj6768/smartthings-zigbee-edge-drivers"
REV="2c97fe1729dc74ee598737a98296ae7c3b902257"
DRIVER_BLOB="5b750e4f6545659135154c42de783ba172462950"
ANCHOR='local bI=require"st.zigbee"local n=bI("tuya-universal",bv)'
DEFAULT=["ef00-covers-2-wonjj6768","zcl-plugs-wonjj6768"]
ALLOWED=re.compile(r"^(?:ef00-(?:covers|switch|lights|energy|meters|sensors|presence|pir-motion)|zcl-(?:plugs|switch|lights|covers|sensors|controls))(?:[a-z0-9-]*)-wonjj6768$")
def blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
def package_key(family):
    # API rejects keys longer than 36 characters. Preserve already-valid keys
    # so successfully installed packages keep their identity on future builds.
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*",family):raise ValueError("Invalid package family")
    old="cleverk2000.st-direct."+family
    key=old if len(old)<=36 else "std-"+family[:19].rstrip("-")+"-"+hashlib.sha256(family.encode()).hexdigest()[:12]
    if not re.fullmatch(r"[a-z0-9.-]{1,36}",key):raise ValueError("Invalid package key")
    return key
def display_name(name):
    # Conservative 36-character limit for our generated display names.
    name=str(name).strip()
    if len(name)>36:name=name[:36].rstrip()
    if len(name)<3:raise ValueError("Invalid driver name")
    return name
def validate_config(cfg,family):
    if cfg.get("packageKey")!=package_key(family):raise ValueError("Invalid package key: "+family)
    if not isinstance(cfg.get("name"),str) or not 3<=len(cfg["name"])<=36:raise ValueError("Invalid driver name: "+family)
    if not isinstance(cfg.get("description"),str) or not cfg["description"].strip():raise ValueError("Missing driver description")
    perms=cfg.get("permissions")
    if not isinstance(perms,dict) or not {"zigbee","lan"}<=set(perms):raise ValueError("Missing driver permissions")
# Server reported limit on total bytes. Count uncompressed file bytes, not ZIP size.
PACKAGE_LIMIT=655360
PACKAGE_TARGET=PACKAGE_LIMIT-8192
def package_files(pkg):
    paths=[]
    for name in ("config","fingerprints","search-parameters"):
        for ext in (".yml",".yaml"):
            p=pkg/(name+ext)
            if p.is_file():paths.append(p);break
    paths.extend(p for p in (pkg/"profiles").glob("*.y*ml") if p.is_file())
    # SmartThings CLI default excludes src/test/** and src/tests/**.
    paths.extend(p for p in (pkg/"src").rglob("*") if p.is_file() and p.relative_to(pkg/"src").parts[0] not in ("test","tests"))
    return paths
def package_bytes(pkg):
    return sum(p.stat().st_size for p in package_files(pkg))
def compact_yaml(data):
    obj=read_yaml(data.decode("utf-8-sig"))
    options=[data]
    # JSON is a YAML subset. Keep the shortest lossless representation.
    try:options.append((json.dumps(obj,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n").encode("utf-8"))
    except (TypeError,ValueError):pass
    options.append(yaml.safe_dump(obj,allow_unicode=True,sort_keys=False,default_flow_style=True,width=1000000).encode("utf-8"))
    options.append(yaml.safe_dump(obj,allow_unicode=True,sort_keys=False,default_flow_style=None,width=1000000).encode("utf-8"))
    valid=[]
    for candidate in options:
        try:
            if read_yaml(candidate.decode("utf-8-sig"))==obj:valid.append(candidate)
        except yaml.YAMLError:pass
    return min(valid,key=len)
def optimize_package(pkg,force=False):
    before=package_bytes(pkg)
    if before>PACKAGE_TARGET or force:
        changes=[]
        for p in package_files(pkg):
            if p.suffix not in (".yaml",".yml"):continue
            data=p.read_bytes();new=compact_yaml(data)
            if len(new)<len(data):changes.append((p,new))
        after=before+sum(len(new)-p.stat().st_size for p,new in changes)
        if after>PACKAGE_LIMIT:raise ValueError(f"{pkg.name}: {after} bytes after lossless compaction; limit {PACKAGE_LIMIT}; no profiles removed")
        for p,new in changes:p.write_bytes(new)
    after=package_bytes(pkg)
    if after>PACKAGE_LIMIT:raise ValueError(f"{pkg.name}: {after} bytes exceeds {PACKAGE_LIMIT}")
    print(f"{pkg.name}: package bytes {before} -> {after} / {PACKAGE_LIMIT}")
    return after
def textpref(name,title,default="",password=False,maxlen=64):
    return dict(name=name,title=title,description=title,required=False,preferenceType="string",
        definition=dict(stringType="password" if password else "text",minLength=0,maxLength=maxlen,default=default))
def boolpref(name,title,default):
    return dict(name=name,title=title,description=title,required=True,preferenceType="boolean",definition=dict(default=default))
PREFS=[
    boolpref("stMqttExport","Export to HA MQTT",True),
    boolpref("stMqttMaster","MQTT master device",False),
    textpref("stMqttHost","MQTT broker IPv4","192.168.0.19",maxlen=15),
    dict(name="stMqttPort",title="MQTT broker port",description="MQTT broker port",required=True,preferenceType="integer",definition=dict(minimum=1,maximum=65535,default=1883)),
    textpref("stMqttUser","MQTT username"),
    textpref("stMqttPass","MQTT password",password=True,maxlen=128),
    textpref("stMqttSite","MQTT site identifier","home",maxlen=32),
]
def validate_mqtt_preferences(prefs):
    expected={p["name"]:p for p in PREFS}
    seen=set()
    for p in prefs:
        name=p.get("name")
        if name not in expected:continue
        if name in seen:raise ValueError("Duplicate MQTT preference: "+name)
        seen.add(name)
        title=p.get("title")
        if not isinstance(title,str) or not 3<=len(title)<=36 or not re.fullmatch(r"[A-Za-z][A-Za-z0-9 ]*",title):
            raise ValueError("Invalid MQTT preference title: "+name)
        if p!=expected[name]:raise ValueError("MQTT preference schema mismatch: "+name)
    if seen!=set(expected):raise ValueError("Incomplete MQTT preferences")
def patch_profile(content):
    obj=read_yaml(content)
    if not isinstance(obj,dict) or not isinstance(obj.get("components"),list) or not obj.get("name"):
        raise ValueError("Invalid upstream profile")
    prefs=obj.setdefault("preferences",[])
    if not isinstance(prefs,list):raise ValueError("Unknown preferences layout")
    names={p.get("name") or p.get("preferenceId") for p in prefs}
    if names & {p["name"] for p in PREFS}:raise ValueError("Preference collision")
    prefs.extend(PREFS)
    validate_mqtt_preferences(prefs)
    return yaml.safe_dump(obj,allow_unicode=True,sort_keys=False,width=120)
def patch_driver(data,family,verify=True):
    if verify and blob(data)!=DRIVER_BLOB:raise ValueError("Upstream driver changed; review before patch")
    src=data.decode("utf-8")
    if src.count(ANCHOR)!=1 or src.count("n:run()")!=1:raise ValueError("Unknown upstream entry point")
    return src.replace(ANCHOR,'\nrequire("st_mqtt.bridge").wrap(bv,"'+family+'")\n'+ANCHOR,1)
def archive_path(cache):
    cache.mkdir(parents=True,exist_ok=True)
    path=cache/(REV+".zip")
    if not path.exists():
        temp=path.with_suffix(".part")
        try:
            with urllib.request.urlopen(f"https://codeload.github.com/{UPSTREAM}/zip/{REV}",timeout=90) as src,temp.open("wb") as dst:
                shutil.copyfileobj(src,dst)
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
    return path
def catalog(z):
    result={}
    for item in z.infolist():
        p=PurePosixPath(item.filename)
        if len(p.parts)==4 and p.parts[1]=="deploy" and p.name=="config.yml" and ALLOWED.fullmatch(p.parts[2]):
            result[p.parts[2]]=p.parts[0]
    return result
def build(z,packages,out):
    found=catalog(z)
    if not packages or len(set(packages))!=len(packages) or any(n not in found for n in packages):
        raise ValueError("Unknown, duplicate, or disallowed package")
    if out.exists():raise ValueError(f"Output already exists: {out}; choose new directory")
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="st-direct-",dir=out.parent) as td:
        temp=Path(td)/"build";temp.mkdir()
        for name in packages:
            root=found[name]
            dest=temp/name;dest.mkdir()
            path_prefix=f"{root}/deploy/{name}/"
            copied=set()
            for info in z.infolist():
                if not info.filename.startswith(path_prefix) or info.is_dir():continue
                rel=PurePosixPath(info.filename[len(path_prefix):])
                if not rel.parts or rel.is_absolute() or ".." in rel.parts or any("\\" in p or ":" in p for p in rel.parts) or (info.external_attr>>16)&0o170000==0o120000:
                    raise ValueError("Unsafe archive member")
                if rel in copied:raise ValueError("Duplicate archive member")
                copied.add(rel)
                target=dest.joinpath(*rel.parts);target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(z.read(info))
            conf=dest/"config.yml";cfg=read_yaml(conf.read_text(encoding="utf-8"))
            if cfg.get("packageKey")!=name or "zigbee" not in cfg.get("permissions",{}):raise ValueError("Unexpected upstream config")
            family=name.removesuffix("-wonjj6768")
            cfg["packageKey"]=package_key(family)
            cfg["name"]=display_name("ST MQTT "+cfg["name"].replace(" wonjj6768",""))
            cfg["description"]="MQTT overlay; original Zigbee support by wonjj6768"
            cfg["vendorSupportInformation"]="https://github.com/cleverk2000-code/ST"
            cfg["permissions"]["lan"]={}
            validate_config(cfg,family)
            conf.write_text(yaml.safe_dump(cfg,sort_keys=False,allow_unicode=True),encoding="utf-8")
            fingerprints=read_yaml((dest/"fingerprints.yml").read_text(encoding="utf-8"))
            profiles={read_yaml(p.read_text(encoding="utf-8"))["name"] for p in (dest/"profiles").glob("*.y*ml")}
            for value in fingerprints.values():
                if isinstance(value,list):
                    for fp in value:
                        if fp.get("deviceProfileName") not in profiles:raise ValueError("Fingerprint profile missing")
            driver=dest/"src/app/driver.lua";driver.write_text(patch_driver(driver.read_bytes(),family),encoding="utf-8")
            module=dest/"src/st_mqtt";module.mkdir()
            for p in (ROOT/"lua").glob("*.lua"):shutil.copy2(p,module/p.name)
            for p in (dest/"profiles").glob("*.y*ml"):p.write_text(patch_profile(p.read_text(encoding="utf-8")),encoding="utf-8")
            optimize_package(dest)
            (dest/"LICENSE.upstream").write_bytes(z.read(f"{root}/LICENSE"))
        (temp/"manifest.json").write_text(json.dumps({"upstream":UPSTREAM,"revision":REV,"packages":packages},indent=2),encoding="utf-8")
        temp.rename(out)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive",type=Path)
    p.add_argument("--cache",type=Path,default=ROOT/".cache")
    p.add_argument("--out",type=Path,default=ROOT/"build")
    p.add_argument("--packages",nargs="+",default=DEFAULT)
    p.add_argument("--list",action="store_true")
    p.add_argument("--find",nargs=2,metavar=("MANUFACTURER","MODEL"))
    args=p.parse_args()
    with zipfile.ZipFile(args.archive or archive_path(args.cache)) as z:
        found=catalog(z)
        if args.list:
            print("\n".join(sorted(found)));return
        if args.find:
            for name,root in sorted(found.items()):
                fp=read_yaml(z.read(f"{root}/deploy/{name}/fingerprints.yml"))
                for x in fp.get("zigbeeManufacturer",[]):
                    if (str(x.get("manufacturer")),str(x.get("model")))==tuple(args.find):print(name,x["deviceProfileName"])
            return
        build(z,args.packages,args.out.resolve())
    print("Built:",args.out)
if __name__=="__main__":main()
