import os,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ["ST_SOURCE"]=str(Path(__file__).resolve().parents[2].parent)
import manager as m
class TestManager(unittest.TestCase):
 def test_config(self):
  x=m.mqtt_config("192.168.0.19","1883","a","x","home")
  self.assertEqual(x["port"],1883)
  with self.assertRaises(ValueError):m.mqtt_config("8.8.8.8",1883,"a","x","home")
  self.assertEqual(m.lua_string('a"\\'),'"\\097\\034\\092"')
 def test_identity(self):
  fam="zcl-plugs";key=m.load_build().package_key(fam);did="00000000-0000-4000-8000-000000000001";ch="00000000-0000-4000-8000-000000000002"
  owned=[{"packageKey":key,"driverId":did}];ins=[{"driverId":did,"channelId":ch,"version":"old"}];ass=[{"driverId":did}]
  p=m.make_plan([fam],ins,owned,ass,ch)[0]
  self.assertEqual(m.verify_uploaded(p,{"packageKey":key,"driverId":did,"version":"new"}),(did,"new"))
  with self.assertRaises(RuntimeError):m.verify_uploaded(p,{"packageKey":key,"driverId":ch,"version":"new"})
  with self.assertRaises(ValueError):m.make_plan([fam],ins,owned,[],ch)
 def test_embed(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/"src/st_mqtt";p.mkdir(parents=True)
   src=m.SOURCE/"direct/lua/bridge.lua";(p/"bridge.lua").write_bytes(src.read_bytes())
   m.embed(Path(td),m.mqtt_config("192.168.0.19",1883,"a","x","home"))
   s=(p/"bridge.lua").read_text()
   self.assertIn('if next(s.devices) then chosen=require "st_mqtt.local_config" end',s)
   self.assertNotIn('password="x"',(p/"local_config.lua").read_text())
