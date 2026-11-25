import importlib.util,sys,tempfile,unittest,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import register
class RegisterTest(unittest.TestCase):
 def test_repo(self):
  self.assertEqual(register.repo_name("https://github.com/owner/repo.git"),"owner/repo")
  for x in ("https://evil.example/a/b","owner/repo/tree/main","../repo","owner/.."):
   with self.assertRaises(ValueError):register.repo_name(x)
 def test_family(self):
  a=register.family_name("owner/repo","zigbee-switch")
  self.assertLessEqual(len(a),63)
  self.assertEqual(a,register.family_name("owner/repo","zigbee-switch"))
  self.assertNotEqual(a,register.family_name("other/repo","zigbee-switch"))
 def test_registry(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/"registry.json"
   x={"family":"custom-a","repo":"a/b","package":".","installed_name":"Driver"}
   register.update_registry(p,x);register.update_registry(p,{**x,"revision":"next"})
   self.assertEqual(len(json.loads(p.read_text())),1)
   with self.assertRaises(ValueError):register.update_registry(p,{**x,"family":"custom-b"})
