import runpy,unittest,json
from pathlib import Path
m=runpy.run_path(str(Path(__file__).resolve().parents[1]/"custom_components/st_local_bridge/manager_contract.py"))
D="11111111-1111-4111-8111-111111111111"
P="22222222-2222-4222-8222-222222222222"
H="33333333-3333-4333-8333-333333333333"
class Contract(unittest.TestCase):
    def test_cover(self):
        rules=m["make_rules"](D,P,["shade","position","stop","battery"])
        names=[r["name"] for r in rules]
        self.assertEqual(len(names),len(set(names)))
        self.assertTrue(all(len(n)<=100 for n in names))
        self.assertIn("setShadeLevel",json.dumps(rules))
        self.assertIn("pause",json.dumps(rules))
        sync=next(r for r in rules if r["name"].endswith(" sync"))
        self.assertNotIn('"command": "open"',json.dumps(sync))
        self.assertNotIn('"command": "close"',json.dumps(sync))
    def test_scope(self):
        with self.assertRaises(ValueError):m["make_rules"](D,D,["switch"])
        with self.assertRaises(ValueError):m["make_rules"](D,P,["lock"])
    def test_discovery(self):
        record={"physical":D,"name":"세탁실","fields":["shade","position","stop","battery"]}
        result=m["discovery"](H,record)
        self.assertEqual(len(result),2)
        cover=result[0][1]
        self.assertEqual(cover["command_topic"],f"stbridge/v1/{H}/{D}/cmd/shade")
        self.assertEqual(cover["availability_mode"],"all")
        self.assertFalse(cover["retain"])
    def test_specs(self):
        d={"type":"ZIGBEE","executionContext":"LOCAL","components":[{"id":"main","capabilities":[{"id":"windowShade"},{"id":"windowShadeLevel"},{"id":"battery"}]}]}
        self.assertEqual(set(m["specs"](d)),{"shade","position","stop","battery"})
        d["components"][0]["capabilities"].append({"id":"lock"})
        self.assertEqual(m["specs"](d),[])
        d["executionContext"]="CLOUD"
        self.assertEqual(m["specs"](d),[])
    def test_report_direction(self):
        rules=m["make_rules"](D,P,["switch","brightness","temperature"])
        for r in rules:
            if "report" in r["name"]:
                self.assertIn(P,json.dumps(r))
        self.assertIn("setHeatingSetpoint",json.dumps(rules))
