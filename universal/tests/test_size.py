import sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import compact_package as c
class SizeTest(unittest.TestCase):
 def test_compaction(self):
  source=c.build.direct.patch_profile("{name: test,components:[{id: main,capabilities:[{id: switch,version: 1}]}]}").encode()
  compact=c.build.direct.compact_yaml(source)
  self.assertLess(len(compact),len(source))
  self.assertEqual(c.build.direct.read_yaml(source),c.build.direct.read_yaml(compact))
 def test_limit(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"test.zip"
   with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as z:z.writestr("src/init.lua",b"x"*655361)
   with self.assertRaises(ValueError):c.verify_zip(path)
