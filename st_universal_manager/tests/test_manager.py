import os,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ["ST_SOURCE"]=str(Path(__file__).resolve().parents[2])
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
 def test_zcl_controls_opt_in(self):
  fam="zcl-controls";ch="00000000-0000-4000-8000-000000000002"
  self.assertIn(fam,m.FAMILIES)
  self.assertNotIn(fam,m.DEFAULT_FAMILIES)
  self.assertEqual(len(m.DEFAULT_FAMILIES),7)
  with self.assertRaises(ValueError):m.make_plan([fam],[],[],[],ch)
  p=m.make_plan([fam],[],[],[],ch,True)[0]
  self.assertEqual(p["mode"],"new")
  self.assertEqual(p["key"],m.load_build().package_key(fam))
 def test_zcl_controls_ui(self):
  import re
  import webapp
  from flask import render_template_string
  with webapp.app.test_request_context():
   html=render_template_string(webapp.PAGE,families=m.FAMILIES,default_families=m.DEFAULT_FAMILIES)
  self.assertRegex(html,r'name="family" value="zcl-plugs" checked')
  self.assertRegex(html,r'name="family" value="zcl-controls">')
  self.assertNotRegex(html,r'name="family" value="zcl-controls" checked')
 def test_target_persistence(self):
  from unittest.mock import patch
  h="00000000-0000-4000-8000-000000000001";c="00000000-0000-4000-8000-000000000002";other="00000000-0000-4000-8000-000000000003"
  with tempfile.TemporaryDirectory() as td,patch.object(m,"DATA",Path(td)):
   self.assertIsNone(m.read_target())
   self.assertEqual(m.save_target(h,c),{"hub":h,"channel":c})
   p=Path(td)/"target.local.json"
   self.assertEqual(p.stat().st_mode & 0o777,0o600)
   before=p.read_bytes()
   with self.assertRaises(ValueError):m.save_target(h,"invalid")
   self.assertEqual(p.read_bytes(),before)
   self.assertEqual(m.read_target(),{"hub":h,"channel":c})
   m.save_target(h,other)
   self.assertEqual(m.read_target(),{"hub":h,"channel":other})
   p.write_text("broken")
   self.assertIsNone(m.read_target())
 def test_target_prefill_and_validation(self):
  from unittest.mock import patch
  import webapp as w
  h="00000000-0000-4000-8000-000000000001";c="00000000-0000-4000-8000-000000000002";other="00000000-0000-4000-8000-000000000003"
  with tempfile.TemporaryDirectory() as td,patch.object(m,"DATA",Path(td)),patch.dict(w.state,{"busy":False,"hub":"","channel":"","lines":[]}),patch.object(m,"CLI") as cli,patch.object(m,"make_plan") as plan:
   cli.return_value.inventory.return_value=([],[],[])
   plan.return_value=[]
   w.worker("test-token-123456",h,c,["zcl-plugs"],None,"inventory",False)
   self.assertEqual(m.read_target(),{"hub":h,"channel":c})
   w.state.update(hub="",channel="")
   with w.app.test_request_context():
    html=w.page()
   self.assertIn('name="hub" value="'+h+'"',html)
   self.assertIn('name="channel" value="'+c+'"',html)
   plan.side_effect=ValueError("invalid target")
   w.worker("test-token-123456",h,other,["zcl-plugs"],None,"inventory",False)
   self.assertEqual(m.read_target(),{"hub":h,"channel":c})
   plan.side_effect=None
   w.worker("test-token-123456",h,other,["zcl-plugs"],None,"inventory",False)
   self.assertEqual(m.read_target(),{"hub":h,"channel":other})
 def test_embed(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/"src/st_mqtt";p.mkdir(parents=True)
   src=m.SOURCE/"direct/lua/bridge.lua";(p/"bridge.lua").write_bytes(src.read_bytes())
   m.embed(Path(td),m.mqtt_config("192.168.0.19",1883,"a","x","home"))
   s=(p/"bridge.lua").read_text()
   self.assertIn('if next(s.devices) then chosen=require "st_mqtt.local_config" end',s)
   self.assertNotIn('password="x"',(p/"local_config.lua").read_text())
