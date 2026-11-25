#!/usr/bin/env python3
"""Build reviewed SmartThings Zigbee MQTT overlays; never executes downloaded source."""
import argparse, hashlib, importlib.util, json, os, re, shutil, tempfile, urllib.request, zipfile
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parent
D=ROOT.parent/"direct"
spec=importlib.util.spec_from_file_location("direct_build",D/"build.py")
direct=importlib.util.module_from_spec(spec);spec.loader.exec_module(direct)
yaml=direct.yaml
CAT=json.loads((ROOT/"catalog.json").read_text())
OFF=CAT["official"]
REPO=re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REV=re.compile(r"^[0-9a-f]{40}$")
FAMILY=re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
# Conservative support for ordinary SDK entrypoints only. Reject alternate constructors.
ENTRY=re.compile(r'(?m)^\s*local\s+(\w+)\s*=\s*(\w+)\(\s*["\'][^"\'\n]+["\']\s*,\s*(\w+)\s*\)\s*\n\s*\1:run\(\)\s*\Z')
def patch(data,family,expected=None):
    if expected and direct.blob(data)!=expected:raise ValueError("Unreviewed entrypoint revision")
    if not FAMILY.fullmatch(family):raise ValueError("Invalid family")
    src=data.decode("utf-8")
    match=ENTRY.search(src)
    if not match:raise ValueError("Unsupported entrypoint; manual adapter review required")
    var,ctor,template=match.groups()
    if not re.search(r'(?m)^\s*local\s+'+re.escape(ctor)+r'\s*=\s*require\s*\(?\s*["\']st\.zigbee["\']',src):
        raise ValueError("Not a recognized Zigbee SDK constructor")
    # The common default Lua handlers must run to observe events and inject commands.
    src=re.sub(r'(native_capability_(?:cmds|attrs)_enabled\s*=\s*)true\b',r'\g<1>false',src)
    match=ENTRY.search(src)
    run=re.search(r'(?m)^\s*'+re.escape(var)+r':run\(\)\s*\Z',src)
    return src[:run.start()]+'\n-- ST Direct MQTT adapter (modified source)\nlocal st_mqtt_ok = pcall(function() require("st_mqtt.bridge").attach('+var+',"'+family+'") end)\nif not st_mqtt_ok then require("log").warn("ST Direct MQTT initialization unavailable") end\n'+src[run.start():]
def download(repo,rev,cache):
    if not REPO.fullmatch(repo) or not REV.fullmatch(rev):raise ValueError("Explicit repository and immutable full commit required")
    if any(x in (".","..") for x in repo.split("/")):raise ValueError("Invalid repository")
    cache.mkdir(parents=True,exist_ok=True)
    path=cache/(repo.replace("/","_")+"-"+rev+".zip")
    if path.exists():return path
    with tempfile.NamedTemporaryFile(dir=cache,delete=False) as tmp:
        name=Path(tmp.name)
        try:
            with urllib.request.urlopen(f"https://codeload.github.com/{repo}/zip/{rev}",timeout=120) as response:
                count=0
                while chunk:=response.read(1024*1024):
                    count+=len(chunk)
                    if count>350*1024*1024:raise ValueError("Archive too large")
                    tmp.write(chunk)
            tmp.close();name.replace(path)
        finally:name.unlink(missing_ok=True)
    return path
def extract_package(z,package,dest):
    rel=PurePosixPath(package)
    if rel.is_absolute() or ".." in rel.parts or any("\\" in p or ":" in p for p in rel.parts):raise ValueError("Invalid package path")
    roots={PurePosixPath(x.filename).parts[0] for x in z.infolist() if x.filename}
    if len(roots)!=1:raise ValueError("Expected single archive root")
    root=roots.pop();prefix=root+"/"+(str(rel)+"/" if str(rel)!="." else "")
    total=0;seen=set()
    for info in z.infolist():
        if not info.filename.startswith(prefix) or info.is_dir():continue
        p=PurePosixPath(info.filename[len(prefix):])
        if not p.parts or p.is_absolute() or ".." in p.parts or any("\\" in x or ":" in x for x in p.parts) or (info.external_attr>>16)&0o170000==0o120000:
            raise ValueError("Unsafe archive path")
        if p in seen:raise ValueError("Duplicate path")
        seen.add(p)
        total+=info.file_size
        if total>100*1024*1024:raise ValueError("Package too large")
        if p.parts[0] not in {"src","profiles","config.yml","config.yaml","fingerprints.yml","fingerprints.yaml","LICENSE","NOTICE"}:continue
        target=dest.joinpath(*p.parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info))
    return root
def build_sdk(archive,package,dest,family,license_id,expected=None):
    with zipfile.ZipFile(archive) as z:
        dest.mkdir()
        root=extract_package(z,package,dest)
        config=next((dest/n for n in ("config.yml","config.yaml") if (dest/n).is_file()),None)
        if config is None:raise ValueError("No config")
        cfg=direct.read_yaml(config.read_text(encoding="utf-8"))
        permissions=cfg.get("permissions") or {}
        if "zigbee" not in permissions or set(permissions)-{"zigbee","lan","discovery"}:raise ValueError("Unsupported permissions")
        cfg["permissions"]={**permissions,"lan":{}}
        cfg["name"]=direct.display_name("ST MQTT "+str(cfg["name"]))
        cfg["packageKey"]=direct.package_key(family)
        cfg["vendorSupportInformation"]="https://github.com/cleverk2000-code/ST"
        direct.validate_config(cfg,family)
        config.write_text(yaml.safe_dump(cfg,sort_keys=False,allow_unicode=True),encoding="utf-8")
        init=dest/"src/init.lua";init.write_text(patch(init.read_bytes(),family,expected),encoding="utf-8")
        profiles=list((dest/"profiles").glob("*.y*ml"))
        if not profiles:raise ValueError("No profiles")
        for p in profiles:p.write_text(direct.patch_profile(p.read_text(encoding="utf-8")),encoding="utf-8")
        module=dest/"src/st_mqtt";module.mkdir()
        for p in (D/"lua").glob("*.lua"):shutil.copy2(p,module/p.name)
        # Preserve license/notice and require explicit compatible license.
        if license_id not in {"MIT","Apache-2.0","BSD-2-Clause","BSD-3-Clause"}:raise ValueError("License requires review")
        license_path=next((n for n in (root+"/LICENSE",root+"/LICENSE.txt",root+"/LICENSE.md") if n in z.namelist()),None)
        if not license_path:raise ValueError("Root license unavailable")
        license_bytes=z.read(license_path)
        license_text=license_bytes.decode("utf-8",errors="strict")
        if license_id=="Apache-2.0" and ("Apache License" not in license_text or "Version 2.0" not in license_text):raise ValueError("License mismatch")
        if license_id=="MIT" and "Permission is hereby granted, free of charge" not in license_text:raise ValueError("License mismatch")
        if license_id.startswith("BSD-") and "Redistribution and use" not in license_text:raise ValueError("License mismatch")
        (dest/"LICENSE.upstream").write_bytes(license_bytes)
        for n in ("NOTICE","NOTICE.txt"):
            if root+"/"+n in z.namelist():(dest/"NOTICE.upstream").write_bytes(z.read(root+"/"+n))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--cache",type=Path,default=ROOT/".cache")
    p.add_argument("--official",nargs="*",default=["zigbee-switch","zigbee-motion-sensor","zigbee-window-treatment"])
    p.add_argument("--wonjj",nargs="*",default=["ef00-covers-2-wonjj6768","zcl-plugs-wonjj6768"])
    p.add_argument("--all-official",action="store_true")
    p.add_argument("--bootstrap",action="store_true",help="Include known baseline families even with empty inventory")
    p.add_argument("--plan",type=Path,help="Read-only inventory plan; select known package families")
    p.add_argument("--custom",type=Path,help="Reviewed JSON list: repo,revision,package,family,license,entry_blob")
    p.add_argument("--official-archive",type=Path)
    p.add_argument("--wonjj-archive",type=Path)
    args=p.parse_args()
    official=list(OFF["packages"]) if args.all_official else args.official
    if len(set(official))!=len(official) or any(n not in OFF["packages"] for n in official):p.error("Unknown or duplicate official package")
    custom=json.loads(args.custom.read_text(encoding="utf-8")) if args.custom else []
    if not isinstance(custom,list):p.error("Custom JSON must be a list")
    if args.plan:
        plan=json.loads(args.plan.read_text(encoding="utf-8-sig"))
        official=sorted({r["package"] for r in plan if r["method"]=="official" and r["package"] in OFF["packages"]})
        args.wonjj=sorted({r["package"] for r in plan if r["method"]=="wonjj" and direct.ALLOWED.fullmatch(r["package"] or "")})
        selected={r["package"] for r in plan if r["method"]=="custom"}
        custom=[c for c in custom if c["family"] in selected]
        if args.bootstrap:
            official=sorted(set(official)|{"zigbee-switch","zigbee-motion-sensor","zigbee-window-treatment"})
            args.wonjj=sorted(set(args.wonjj)|set(direct.DEFAULT))
        if not (official or args.wonjj or custom):p.error("No supported unconverted devices in plan; use --bootstrap to include baseline packages")
        print("Selected:",official,args.wonjj,[c["family"] for c in custom])
    out=args.out.resolve()
    if out.exists():p.error("Output must not exist")
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent) as td:
        temp=Path(td)/"build";temp.mkdir();report=[]
        if official:
            archive=args.official_archive or download(OFF["repo"],OFF["revision"],args.cache)
            for name in official:
                family="st-"+name;build_sdk(archive,"drivers/SmartThings/"+name,temp/family,family,OFF["license"],OFF["packages"][name])
                report.append({"family":family,"repo":OFF["repo"],"revision":OFF["revision"],"adapter":"sdk"})
        if args.wonjj:
            archive=args.wonjj_archive or direct.archive_path(args.cache)
            with zipfile.ZipFile(archive) as z:direct.build(z,args.wonjj,temp/"wonjj")
            for name in args.wonjj:
                family=name.removesuffix("-wonjj6768");(temp/"wonjj"/name).rename(temp/family)
                report.append({"family":family,"repo":direct.UPSTREAM,"revision":direct.REV,"adapter":"wonjj"})
            shutil.rmtree(temp/"wonjj")
        for c in custom:
            family=c["family"]
            if not FAMILY.fullmatch(family) or not family.startswith("custom-") or (temp/family).exists():raise ValueError("Custom family must be unique and start custom-")
            if not REV.fullmatch(c["entry_blob"]):raise ValueError("Reviewed entrypoint Git blob SHA required")
            archive=download(c["repo"],c["revision"],args.cache)
            build_sdk(archive,c["package"],temp/family,family,c["license"],c["entry_blob"])
            report.append({"family":family,"repo":c["repo"],"revision":c["revision"],"adapter":"sdk"})
        if not report:raise ValueError("No packages selected")
        (temp/"manifest.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
        temp.rename(out)
    print("Built",out)
if __name__=="__main__":main()
