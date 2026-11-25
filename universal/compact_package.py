#!/usr/bin/env python3
"""Losslessly compact package YAML, and verify actual CLI ZIP byte limits."""
import argparse,json,zipfile
from pathlib import Path
import build
def verify_zip(path):
    with zipfile.ZipFile(path) as z:
        total=sum(x.file_size for x in z.infolist() if not x.is_dir())
        if total>build.direct.PACKAGE_LIMIT or path.stat().st_size>build.direct.PACKAGE_LIMIT:
            raise ValueError(f"{path.name}: ZIP {path.stat().st_size}, expanded {total}, limit {build.direct.PACKAGE_LIMIT}")
        if z.testzip() is not None:raise ValueError("Corrupt ZIP")
        print(f"ZIP PASS: {path.name}: {total} expanded bytes / {build.direct.PACKAGE_LIMIT}")
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("path",type=Path);p.add_argument("--zip",action="store_true")
    a=p.parse_args()
    if a.zip:verify_zip(a.path)
    else:
        cfg=next((a.path/n for n in ("config.yml","config.yaml") if (a.path/n).is_file()),None)
        if not cfg or not (a.path/"src/init.lua").is_file():raise ValueError("Missing driver package")
        meta=build.direct.read_yaml(cfg.read_text(encoding="utf-8-sig"))
        build.direct.validate_config(meta,a.path.name)
        profiles=list((a.path/"profiles").glob("*.y*ml"))
        for f in profiles:build.direct.validate_mqtt_preferences(build.direct.read_yaml(f.read_text(encoding="utf-8-sig"))["preferences"])
        build.direct.optimize_package(a.path,force=True)
        print(f"Preserved {len(profiles)} profiles; source code unchanged")
if __name__=="__main__":main()
