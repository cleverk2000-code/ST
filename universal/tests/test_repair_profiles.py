import copy,json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import repair_profiles as r
class RepairTest(unittest.TestCase):
 def test_old_profile(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);fam="st-zigbee-motion-sensor";p=root/fam/"profiles";p.mkdir(parents=True)
   (root/"manifest.json").write_text(json.dumps([{"family":fam}]))
   (p.parent/"config.yml").write_text("packageKey: cleverk2000.st-direct."+fam)
   prefs=copy.deepcopy(r.direct.PREFS)
   for x in prefs:
    if x["name"]=="stMqttMaster":x["title"]=x["description"]="Use this device for driver MQTT settings"
   obj={"name":"sensor","components":[],"preferences":[{"preferenceId":"reverse","explicit":True}]+prefs}
   path=p/"sensor.yml";path.write_text(r.direct.yaml.safe_dump(obj))
   with self.assertRaises(ValueError):r.repair(root,True)
   r.repair(root);r.repair(root,True)
   repaired=r.direct.read_yaml(path.read_text())
   self.assertEqual(repaired["preferences"][0],obj["preferences"][0])
   self.assertEqual(repaired["preferences"][1:],r.direct.PREFS)
