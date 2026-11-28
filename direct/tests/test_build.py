import importlib.util, unittest, zipfile, tempfile
from pathlib import Path
import yaml
p=Path(__file__).resolve().parents[1]/"build.py"
spec=importlib.util.spec_from_file_location("direct_build",p)
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class BuildTest(unittest.TestCase):
    def test_profile(self):
        src="{name: plug,components:[{id: main,capabilities:[{id: switch,version: 1}]}],preferences:[{preferenceId: reverse,explicit: true}]}"
        old=yaml.safe_load(src);new=yaml.safe_load(b.patch_profile(src))
        self.assertEqual(new["components"],old["components"])
        self.assertEqual(new["preferences"][0],old["preferences"][0])
        self.assertEqual(len(new["preferences"]),8)
        self.assertFalse(next(x for x in new["preferences"] if x.get("name")=="stMqttMaster")["definition"]["default"])
    def test_yaml_enums(self):
        source="{name: p,components: [],deviceConfig: {x: on, y: off, z: true}}"
        new=b.read_yaml(b.patch_profile(source))
        self.assertEqual(new["deviceConfig"],{"x":"on","y":"off","z":True})
    def test_preference_constraints(self):
        prefs=b.read_yaml(b.patch_profile("{name: p,components: []}"))["preferences"]
        b.validate_mqtt_preferences(prefs)
        for p in prefs:self.assertTrue(3<=len(p["title"])<=36)
        next(p for p in prefs if p["name"]=="stMqttMaster")["title"]="Use this device for driver MQTT settings"
        with self.assertRaises(ValueError):b.validate_mqtt_preferences(prefs)
    def test_duplicate(self):
        with self.assertRaises(ValueError):b.patch_profile("{name: p,components: [],preferences:[{name: stMqttMaster}]}")
    def test_patch(self):
        data=(b.ANCHOR+"\nn:run()\n").encode()
        out=b.patch_driver(data,"test",verify=False)
        self.assertEqual(out.count("n:run()"),1)
        self.assertIn('wrap(bv,"test")',out)
        with self.assertRaises(ValueError):b.patch_driver(data,"test")
        with self.assertRaises(ValueError):b.patch_driver(data+data,"test",verify=False)
    def test_package_keys(self):
        families=["st-zigbee-motion-sensor","st-zigbee-window-treatment","st-zigbee-switch","ef00-covers-2","ef00-presence-general-2","zcl-plugs","zcl-sensors","custom-"+"a"*55,"custom-"+"a"*54+"b"]
        keys=[b.package_key(x) for x in families]
        self.assertEqual(len(keys),len(set(keys)))
        for k in keys:self.assertRegex(k,r"^[a-z0-9.-]{1,36}$")
        self.assertEqual(b.package_key("zcl-plugs"),"cleverk2000.st-direct.zcl-plugs")
        self.assertEqual(b.package_key(families[0]),keys[0])
        self.assertLessEqual(len(b.display_name("ST MQTT "+"x"*100)),36)
    def test_radar_query_package_scope(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/"target";target.mkdir()
            other=Path(td)/"other";other.mkdir()
            b.copy_bridge_modules(target,"ef00-presence-general-2")
            b.copy_bridge_modules(other,"zcl-sensors")
            for name in ("bridge.lua","model.lua"):
                a=(target/name).read_text();c=(other/name).read_text()
                self.assertIn("radar_query",a)
                self.assertNotIn("radar_query",c)
                self.assertNotIn("RADAR_QUERY_BEGIN",a)
                self.assertNotIn("RADAR_QUERY_BEGIN",c)
                self.assertIn("radar_dp",c)
    def test_allowed(self):
        self.assertTrue(b.ALLOWED.fullmatch("ef00-covers-2-wonjj6768"))
        self.assertTrue(b.ALLOWED.fullmatch("zcl-plugs-wonjj6768"))
        self.assertFalse(b.ALLOWED.fullmatch("zcl-locks-wonjj6768"))
        self.assertFalse(b.ALLOWED.fullmatch("ef00-valves-wonjj6768"))
if __name__=="__main__":unittest.main()
