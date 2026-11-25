import copy,json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import repair_profiles as r
class RepairTest(unittest.TestCase):
 def test_old_profile(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);fam="st-zigbee-motion-sensor";p=root/fam/"profiles";p.mkdir(parents=True)
   (root/"manifest.json").write_text(json.dumps([{"family":fam}]))
   (p.parent/"config.yml").write_text("name: ST MQTT Sensor\npackageKey: cleverk2000.st-direct."+fam+"\ndescription: Test driver\npermissions: {zigbee: {}, lan: {}}")
   prefs=copy.deepcopy(r.direct.PREFS)
   for x in prefs:
    if x["name"]=="stMqttMaster":x["title"]=x["description"]="Use this device for driver MQTT settings"
   obj={"name":"sensor","components":[],"preferences":[{"preferenceId":"reverse","explicit":True}]+prefs}
   path=p/"sensor.yml";path.write_text(r.direct.yaml.safe_dump(obj))
   with self.assertRaises(ValueError):r.repair(root,True)
   r.repair(root);r.repair(root,True)
   config=r.direct.read_yaml((p.parent/"config.yml").read_text())
   self.assertEqual(config["packageKey"],r.direct.package_key(fam))
   self.assertLessEqual(len(config["packageKey"]),36)
   repaired=r.direct.read_yaml(path.read_text())
   self.assertEqual(repaired["preferences"][0],obj["preferences"][0])
   self.assertEqual(repaired["preferences"][1:],r.direct.PREFS)
