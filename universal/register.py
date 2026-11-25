#!/usr/bin/env python3
"""Review a public GitHub driver and generate a pinned custom-source registry entry.

The tool does not execute, install, or trust code based on search rank.
"""
import argparse, base64, hashlib, json, re, tempfile, urllib.parse, urllib.request
from pathlib import Path, PurePosixPath
import build

ROOT=Path(__file__).resolve().parent
LICENSES={"MIT","Apache-2.0","BSD-2-Clause","BSD-3-Clause"}

def repo_name(value):
    if value.startswith("https://github.com/"):
        value=value[len("https://github.com/"):].rstrip("/")
    if value.endswith(".git"):value=value[:-4]
    if not build.REPO.fullmatch(value) or any(x in (".","..") for x in value.split("/")):
        raise ValueError("Specify github.com/owner/repository, not a branch or file URL")
    return value

def api(path):
    if not path.startswith("/") or path.startswith("//"):raise ValueError("Invalid GitHub API path")
    req=urllib.request.Request("https://api.github.com"+path,headers={"Accept":"application/vnd.github+json","User-Agent":"ST-Universal-Registry/0.2"})
    with urllib.request.urlopen(req,timeout=30) as response:
        raw=response.read(20*1024*1024+1)
        if len(raw)>20*1024*1024:raise ValueError("GitHub response too large")
        return json.loads(raw)

def get_repo(repo):
    meta=api("/repos/"+repo)
    if meta.get("private") or meta.get("visibility") not in (None,"public"):raise ValueError("Only public repositories")
    branch=meta["default_branch"]
    rev=api("/repos/"+repo+"/commits/"+urllib.parse.quote(branch,safe=""))["sha"]
    if not build.REV.fullmatch(rev):raise ValueError("Invalid GitHub revision")
    return meta,rev

def source_paths(repo,rev):
    tree=api("/repos/"+repo+"/git/trees/"+rev+"?recursive=1")
    if tree.get("truncated"):raise ValueError("GitHub tree truncated; specify exact --package")
    blobs={x["path"] for x in tree["tree"] if x.get("type")=="blob"}
    result=[]
    for p in sorted(blobs):
        pp=PurePosixPath(p)
        if pp.name in ("config.yml","config.yaml") and str(pp.parent/"src/init.lua") in blobs:
            result.append(str(pp.parent))
    return sorted(set(result))

def content(repo,rev,path):
    p=PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or any("\\" in x or ":" in x for x in p.parts):raise ValueError("Unsafe source path")
    body=api("/repos/"+repo+"/contents/"+urllib.parse.quote(str(p),safe="/")+"?ref="+rev)
    if not isinstance(body,dict) or body.get("encoding")!="base64" or body.get("type")!="file":raise ValueError("Expected ordinary text file")
    data=base64.b64decode(body["content"])
    if build.direct.blob(data)!=body["sha"]:raise ValueError("GitHub blob checksum mismatch")
    return data,body["sha"]

def family_name(repo,key):
    clean=re.sub(r"[^a-z0-9-]+","-",(repo+"-"+key).lower()).strip("-")
    digest=hashlib.sha256((repo.lower()+"\0"+key).encode()).hexdigest()[:10]
    return "custom-"+clean[:43].rstrip("-")+"-"+digest

def review(repo,rev,package,license_id):
    if license_id not in LICENSES:raise ValueError("Repository license not supported; manual license review required")
    p=PurePosixPath(package)
    cfg=None
    for name in ("config.yml","config.yaml"):
        try:
            raw,_=content(repo,rev,p/name);cfg=build.direct.read_yaml(raw);break
        except urllib.error.HTTPError as exc:
            if exc.code!=404:raise
    if not isinstance(cfg,dict):raise ValueError("Driver config unavailable")
    if "zigbee" not in (cfg.get("permissions") or {}):raise ValueError("Not a Zigbee driver")
    name,key=cfg.get("name"),cfg.get("packageKey")
    if not isinstance(name,str) or not name.strip() or not isinstance(key,str) or not key:raise ValueError("Missing driver identity")
    entry,sha=content(repo,rev,p/"src/init.lua")
    family=family_name(repo,key)
    build.patch(entry,family,sha) # validate recognized constructor, without executing Lua
    return {"repo":repo,"revision":rev,"package":str(p),"family":family,"license":license_id,"entry_blob":sha,"installed_name":name}

def update_registry(path,item):
    data=json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if not isinstance(data,list):raise ValueError("Registry is not a list")
    for old in data:
        if old["family"]!=item["family"] and old.get("installed_name","").casefold()==item["installed_name"].casefold():
            raise ValueError("Driver name collision; review registry manually")
        if old["family"]==item["family"] and (old["repo"].lower()!=item["repo"].lower() or old["package"]!=item["package"]):
            raise ValueError("Package identity changed; review manually")
    data=[x for x in data if x["family"]!=item["family"]]+[item]
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,delete=False) as tmp:
        tmp_path=Path(tmp.name)
        try:
            json.dump(data,tmp,ensure_ascii=False,indent=2);tmp.write("\n");tmp.close();tmp_path.replace(path)
        finally:tmp_path.unlink(missing_ok=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo")
    p.add_argument("--package",help="Exact package directory; use . for repository root")
    p.add_argument("--search",help="Show public repository candidates only")
    p.add_argument("--registry",type=Path,default=ROOT/"custom.local.json")
    p.add_argument("--approve",action="store_true",help="After source/license review, write the registry entry")
    p.add_argument("--check-updates",action="store_true",help="Report new default-branch commits; never update automatically")
    a=p.parse_args()
    if a.search:
        q=urllib.parse.urlencode({"q":a.search+" smartthings in:name,description,readme","per_page":10})
        for x in api("/search/repositories?"+q).get("items",[]):
            print(x["full_name"],x.get("html_url"),(x.get("license") or {}).get("spdx_id","unknown"))
        print("Search results are candidates, not verified source identities.")
        return
    if a.check_updates:
        if not a.registry.exists():p.error("Registry not found")
        for item in json.loads(a.registry.read_text(encoding="utf-8")):
            _,rev=get_repo(repo_name(item["repo"]))
            print(item["installed_name"],"unchanged" if rev==item["revision"] else "REVIEW UPDATE "+rev)
        return
    if not a.repo:p.error("Specify --repo, --search or --check-updates")
    repo=repo_name(a.repo);meta,rev=get_repo(repo)
    license_id=(meta.get("license") or {}).get("spdx_id")
    if not a.package:
        print("Repository:",repo,"revision:",rev,"license:",license_id)
        print("\n".join(source_paths(repo,rev)));return
    item=review(repo,rev,a.package,license_id)
    print(json.dumps(item,ensure_ascii=False,indent=2))
    if not a.approve:
        print("Preview only. Review full source and license; repeat with --approve to register.")
        return
    update_registry(a.registry,item)
    print("Registry updated:",a.registry)
if __name__=="__main__":main()
