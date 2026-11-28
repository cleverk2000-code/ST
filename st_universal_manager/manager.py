"""Local admin manager. No credentials in stdout, GitHub or permanent build artifacts."""
import ipaddress,json,os,re,subprocess,tempfile,uuid,zipfile,sys,importlib.util,stat,time
from pathlib import Path

SOURCE=Path(os.getenv("ST_SOURCE","/opt/st"))
DATA=Path(os.getenv("ST_DATA","/data"))
DEFAULT_FAMILIES=["st-zigbee-motion-sensor","st-zigbee-switch","st-zigbee-window-treatment","ef00-covers-2","ef00-presence-general-2","zcl-plugs","zcl-sensors"]
FAMILIES=DEFAULT_FAMILIES+["zcl-controls"]
def load_build():
    spec=importlib.util.spec_from_file_location("st_manager_direct",SOURCE/"direct/build.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def uuid_text(s):
    return str(uuid.UUID(s))
def token_valid(s):
    return isinstance(s,str) and 16<=len(s)<=4096 and not any(c.isspace() or ord(c)<32 for c in s)
def mqtt_config(host,port,user,password,site):
    ip=ipaddress.IPv4Address(host)
    if not any(ip in ipaddress.IPv4Network(n) for n in ("10.0.0.0/8","172.16.0.0/12","192.168.0.0/16")):raise ValueError("MQTT broker must be a private IPv4 address")
    port=int(port)
    if not 1<=port<=65535:raise ValueError("Invalid MQTT port")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}",site):raise ValueError("Invalid site")
    for v in (user,password):
        if not v or len(v.encode("utf-8"))>128 or any(ord(c)<32 or ord(c)==127 for c in v):raise ValueError("Invalid MQTT credential")
    return dict(host=str(ip),port=port,user=user,password=password,site=site)
def save_config(cfg):
    DATA.mkdir(parents=True,exist_ok=True)
    target=DATA/"mqtt.local.json"
    fd,name=tempfile.mkstemp(dir=DATA,prefix=".mqtt-")
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as out:json.dump(cfg,out)
        os.replace(name,target)
    finally:
        Path(name).unlink(missing_ok=True)
def read_config():
    p=DATA/"mqtt.local.json"
    if not p.exists():return None
    return mqtt_config(**json.loads(p.read_text(encoding="utf-8")))
def lua_string(s):
    return '"'+''.join("\\%03d"%b for b in s.encode("utf-8"))+'"'
def embed(pkg,cfg):
    path=pkg/"src/st_mqtt/bridge.lua"
    src=path.read_text(encoding="utf-8")
    anchor=" local chosen,invalid=nil,false\n for _,rec in pairs(s.devices) do"
    end=" if invalid then chosen=nil;log.warn("
    if src.count(anchor)!=1 or src.count(end)!=1:raise ValueError("Unexpected bridge source; no patch")
    # Explicit per-device export flag remains effective. Default broker overrides obsolete master settings.
    src=src.replace(anchor," local chosen,invalid=nil,false\n if next(s.devices) then chosen=require \"st_mqtt.local_config\" end\n if not chosen then\n for _,rec in pairs(s.devices) do",1)
    src=src.replace(end," end\n"+end,1)
    path.write_text(src,encoding="utf-8")
    local="return {"+",".join(k+"="+(str(v) if isinstance(v,int) else lua_string(v)) for k,v in cfg.items())+"}\n"
    (path.parent/"local_config.lua").write_text(local,encoding="ascii")
def normalize(x):
    if isinstance(x,list):return [r for r in x if isinstance(r,dict)]
    if isinstance(x,dict):return normalize(x["items"]) if "items" in x else [x]
    return []
class CLI:
    def __init__(self,token):
        if not token_valid(token):raise ValueError("Enter a valid temporary PAT")
        self.token=token
    def run(self,args,as_json=False):
        cmd=["smartthings",*args,"--token",self.token]
        if as_json:cmd+=["-j"]
        try:
            p=subprocess.run(cmd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",errors="replace",timeout=180,env={**os.environ,"NO_COLOR":"1","CI":"true"})
        except subprocess.TimeoutExpired:raise RuntimeError(args[0]+": timed out; verify server state before retry") from None
        if p.returncode:
            # Never include arbitrary CLI output: can contain credentials or device information.
            status=re.search(r"\b(400|401|403|404|409|422|429|500|502|503)\b",p.stderr+" "+p.stdout)
            raise RuntimeError(args[0]+": failed"+(" (HTTP "+status.group(1)+")" if status else "")+"; verify PAT permissions and server state")
        if as_json:
            try:return json.loads(p.stdout.lstrip("\ufeff").strip())
            except ValueError:raise RuntimeError(args[0]+": expected JSON output") from None
        return None
    def inventory(self,hub,channel):
        installed=normalize(self.run(["edge:drivers:installed","-H",hub],True))
        owned=normalize(self.run(["edge:drivers"],True))
        assigned=normalize(self.run(["edge:channels:drivers",channel],True))
        return installed,owned,assigned
def make_plan(families,installed,owned,assigned,channel,allow_new=False):
    b=load_build();plan=[]
    allowed=set(FAMILIES)|{"st-"+x for x in json.loads((SOURCE/"universal/catalog.json").read_text())["official"]["packages"]}
    if not families or len(set(families))!=len(families) or any(x not in allowed for x in families):raise ValueError("Unknown or duplicate package family")
    for fam in families:
        key=b.package_key(fam);matches=[d for d in owned if d.get("packageKey")==key]
        if len(matches)>1:raise ValueError("Ambiguous owned package: "+fam)
        if not matches:
            if not allow_new:raise ValueError("Existing owned package not found: "+fam)
            plan.append(dict(family=fam,key=key,driver_id=None,mode="new"));continue
        did=uuid_text(matches[0]["driverId"])
        ins=[d for d in installed if d.get("driverId")==did]
        ass=[d for d in assigned if d.get("driverId")==did]
        if len(ins)!=1 or len(ass)!=1 or ins[0].get("channelId")!=channel:raise ValueError("Existing package not verified on selected hub/channel: "+fam)
        plan.append(dict(family=fam,key=key,driver_id=did,mode="update",previous_version=ins[0].get("version")))
    return plan
def verify_uploaded(item,result):
    if not isinstance(result,dict) or result.get("packageKey")!=item["key"]:raise RuntimeError("Uploaded package identity mismatch; not assigned")
    did=uuid_text(result["driverId"]);version=result.get("version")
    if item["driver_id"] and did!=item["driver_id"]:raise RuntimeError("Driver ID changed; not assigned or installed")
    if not isinstance(version,str) or not re.fullmatch(r"[0-9A-Za-z:.+_-]{1,128}",version):raise RuntimeError("Invalid uploaded version")
    return did,version
def local_run(args):
    try:p=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
    except subprocess.TimeoutExpired:raise RuntimeError("Local build timed out") from None
    if p.returncode:raise RuntimeError("Local build or syntax check failed; no upload")
def zip_package(pkg,out,b):
    # Same archive members as default CLI (test dirs excluded); preserve filenames and no extra artifacts.
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in b.package_files(pkg):
            name=p.relative_to(pkg).as_posix()
            if not name.startswith("src/") and name.endswith(".yaml"):name=name[:-5]+".yml"
            z.write(p,name)
    with zipfile.ZipFile(out) as z:
        expanded=sum(x.file_size for x in z.infolist() if not x.is_dir())
        if expanded>b.PACKAGE_LIMIT or out.stat().st_size>b.PACKAGE_LIMIT or z.testzip():raise RuntimeError("ZIP size or integrity failed: "+pkg.name)
    return expanded
def build_and_deploy(cli,hub,channel,plan,cfg,apply,report):
    b=load_build()
    # Avoid disk persistence of secret-bearing packages. /tmp is temporary, no stored zip/credential dumps.
    DATA.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="st-manager-") as td:
        root=Path(td);out=root/"build"
        official=[p["family"][3:] for p in plan if p["family"].startswith("st-")]
        wonjj=[p["family"]+"-wonjj6768" for p in plan if not p["family"].startswith("st-")]
        report("Pinned source build started")
        local_run([sys.executable,str(SOURCE/"universal/build.py"),"--cache",str(DATA/"cache"),"--out",str(out),"--official",*official,"--wonjj",*wonjj])
        artifacts=[]
        for item in plan:
            fam=item["family"];pkg=out/fam
            if cfg:embed(pkg,cfg)
            b.optimize_package(pkg,force=True)
            meta=b.read_yaml((pkg/"config.yml").read_text(encoding="utf-8"))
            b.validate_config(meta,fam)
            for p in (pkg/"profiles").glob("*.y*ml"):b.validate_mqtt_preferences(b.read_yaml(p.read_text(encoding="utf-8"))["preferences"])
            for p in (pkg/"src").rglob("*.lua"):
                if p.relative_to(pkg/"src").parts[0] not in ("test","tests"):local_run(["luac5.3","-p",str(p)])
            z=root/(fam+".zip");size=zip_package(pkg,z,b)
            report(f"{fam}: {size} bytes, preflight PASS")
            artifacts.append((item,z))
        if not apply:
            report("Dry run complete. No upload or device change.");return
        # Recheck current IDs immediately before any write.
        current=make_plan([p["family"] for p in plan],*cli.inventory(hub,channel),channel,any(p["mode"]=="new" for p in plan))
        if current!=plan:raise RuntimeError("Inventory changed since preflight; no upload")
        for item,z in artifacts:
            fam=item["family"];report(f"{fam}: uploading new revision")
            result=cli.run(["edge:drivers:package","--upload",str(z)],True)
            did,version=verify_uploaded(item,result)
            cli.run(["edge:channels:assign",did,version,"-C",channel])
            cli.run(["edge:drivers:install",did,"-C",channel,"-H",hub])
            verified=False
            for _ in range(5):
                found=normalize(cli.run(["edge:drivers:installed","-H",hub],True))
                if any(d.get("driverId")==did and d.get("channelId")==channel and d.get("version")==version for d in found):
                    verified=True;break
                time.sleep(2)
            if not verified:raise RuntimeError(f"{fam}: revision submitted but hub version not verified; stop and check before retry")
            report(f"{fam}: installed and verified, ID {did}")
        report("All selected driver versions verified. No device switching performed.")
