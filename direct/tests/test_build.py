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
    def test_duplicate(self):
        with self.assertRaises(ValueError):b.patch_profile("{name: p,components: [],preferences:[{name: stMqttMaster}]}")
    def test_patch(self):
        data=(b.ANCHOR+"\nn:run()\n").encode()
        out=b.patch_driver(data,"test",verify=False)
        self.assertEqual(out.count("n:run()"),1)
        self.assertIn('wrap(bv,"test")',out)
        with self.assertRaises(ValueError):b.patch_driver(data,"test")
        with self.assertRaises(ValueError):b.patch_driver(data+data,"test",verify=False)
    def test_allowed(self):
        self.assertTrue(b.ALLOWED.fullmatch("ef00-covers-2-wonjj6768"))
        self.assertTrue(b.ALLOWED.fullmatch("zcl-plugs-wonjj6768"))
        self.assertFalse(b.ALLOWED.fullmatch("zcl-locks-wonjj6768"))
        self.assertFalse(b.ALLOWED.fullmatch("ef00-valves-wonjj6768"))
if __name__=="__main__":unittest.main()
