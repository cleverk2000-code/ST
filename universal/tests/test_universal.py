import importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(n):
 s=importlib.util.spec_from_file_location(n,ROOT/(n+".py"));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
b=load("build");i=load("inventory")
class UniversalTest(unittest.TestCase):
 def test_patch(self):
  src=b'local ZigbeeDriver = require "st.zigbee"\nlocal t = {}\nlocal d = ZigbeeDriver("test", t)\nd:run()\n'
  out=b.patch(src,"st-test")
  self.assertIn('attach(d,"st-test")',out)
  self.assertEqual(out.count("d:run()"),1)
  with self.assertRaises(ValueError):b.patch(src,"st-test","0"*40)
 def test_reject(self):
  with self.assertRaises(ValueError):b.patch(b'local D=require "st.driver"\nlocal d=D("x",t)\nd:run()\n',"test")
 def test_native(self):
  src=b'local Z=require "st.zigbee"\nlocal t={native_capability_attrs_enabled = true}\nlocal d=Z("x",t)\nd:run()\n'
  self.assertIn("native_capability_attrs_enabled = false",b.patch(src,"test"))
 def test_power_restore_profile_scope(self):
  profile="name: sample\ncomponents:\n  - id: main\n    capabilities:\n      - id: switch\n      - id: powerMeter\n"
  def prefs(data,family):
   return {p["name"]:p for p in b.direct.read_yaml(b.patch_sdk_profile(data,family))["preferences"]}
  p=prefs(profile,"st-zigbee-switch")["stPowerRestore"]
  self.assertEqual(p["definition"]["default"],"unchanged")
  self.assertEqual(set(p["definition"]["options"]),{"unchanged","off","on","restore"})
  self.assertNotIn("stPowerRestore",prefs(profile,"st-zigbee-motion-sensor"))
  self.assertNotIn("stPowerRestore",prefs(profile.replace("      - id: powerMeter\n",""),"st-zigbee-switch"))
 def test_inventory(self):
  d=lambda id:{"type":"ZIGBEE","deviceId":id,"zigbee":{"driverId":id}}
  r=i.plan([d("1"),d("2"),d("3"),d("4")],[{"driverId":"1","name":"Zigbee Switch"},{"driverId":"2","name":"EF00 Covers 2 wonjj6768"},{"driverId":"3","name":"Unknown"},{"driverId":"4","name":"ST MQTT Zigbee Switch"}])
  self.assertEqual([x["method"] for x in r],["official","wonjj","rules_or_review","already_mqtt"])

 def test_unsafe_inventory(self):
  devices=[{"type":"ZIGBEE","deviceId":"a","zigbee":{"driverId":"a"}},{"type":"ZIGBEE","deviceId":"b","zigbee":{"driverId":"b"}}]
  drivers=[{"driverId":"a","name":"EF00 Valves wonjj6768"},{"driverId":"b","name":"Unreviewed driver"}]
  self.assertEqual([x["method"] for x in i.plan(devices,drivers)],["rules_or_review","rules_or_review"])

 def test_empty_cli_inventory(self):
  for x in (None,[],[None],{"items":None},{"items":[None]},[None,"bad",3]):
   self.assertEqual(i.items(x),[])
   self.assertEqual(i.plan(x,x),[])
  dev={"type":"ZIGBEE","deviceId":"a","zigbee":{"driverId":"x"}}
  self.assertEqual(i.plan([None,dev],[None])[0]["method"],"rules_or_review")
  self.assertEqual(i.plan({"items":[None,dev]},{"items":[None,{"driverId":"x","name":"Zigbee Switch"}]})[0]["package"],"zigbee-switch")
  self.assertEqual(i.plan(dev,{"driverId":"x","name":"Zigbee Switch"})[0]["method"],"official")
