import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build
root=Path(sys.argv[1]);names=["st-zigbee-motion-sensor","st-zigbee-switch","st-zigbee-window-treatment","ef00-covers-2","ef00-presence-general-2","zcl-plugs","zcl-sensors"][:int(sys.argv[2])]
root.mkdir(parents=True,exist_ok=True)
(root/"manifest.json").write_text(json.dumps([{"family":n} for n in names]),encoding="utf-8")
for n in names:
 p=root/n
 (p/"profiles").mkdir(parents=True,exist_ok=True)
 cfg={"name":"ST MQTT Test","packageKey":build.direct.package_key(n),"description":"Test","permissions":{"zigbee":{},"lan":{}}}
 (p/"config.yml").write_text(build.yaml.safe_dump(cfg),encoding="utf-8")
 (p/"profiles"/"test.yml").write_text(build.direct.patch_profile("{name: test, components: []}"),encoding="utf-8")
