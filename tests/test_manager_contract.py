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
        sync=next(r for r in rules if r["name"].endswith(" report"))
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

    def test_rule_budget(self):
        self.assertEqual(len(m["make_rules"](D,P,["switch"])),3)
        self.assertEqual(len(m["make_rules"](D,P,["shade","position","stop","battery"])),5)
        self.assertEqual(len(m["make_rules"](D,P,["motion","temperature","battery"])),1)
    def test_trigger_isolation(self):
        def triggers(node):
            if isinstance(node,list):
                for item in node:yield from triggers(item)
            elif isinstance(node,dict):
                if "device" in node and node["device"].get("trigger")=="Always":
                    d=node["device"];yield (d["devices"][0],d["component"],d["capability"],d["attribute"])
                for v in node.values():yield from triggers(v)
        def commands(node):
            if isinstance(node,list):
                for item in node:yield from commands(item)
            elif isinstance(node,dict):
                if "command" in node and isinstance(node["command"],dict):yield node["command"]
                for v in node.values():yield from commands(v)
        rules=m["make_rules"](D,P,["shade","position","stop","battery","button"])
        for r in rules:
            ts=set(triggers(r));cs=list(commands(r))
            if r["name"].endswith(" report"):
                self.assertIn((P,"sync","button","button"),ts)
                self.assertNotIn((D,"main","button","button"),ts)
                self.assertTrue(all(c["devices"]==[P] for c in cs))
            elif r["name"].endswith(" button"):
                self.assertEqual(ts,{(D,"main","button","button")})
                self.assertTrue(all(c["devices"]==[P] for c in cs))
            else:
                self.assertEqual(len(ts),1)
                self.assertTrue(all(x[0]==P and x[1]!="sync" for x in ts))
                self.assertTrue(all(c["devices"]==[D] for c in cs))
    def test_group_report_evaluation(self):
        # Independent small evaluator: models conditions, trigger selection and command destinations.
        def value(o,state):
            if "device" in o:
                d=o["device"];return state.get((d["devices"][0],d["component"],d["capability"],d["attribute"]))
            return o.get("string",o.get("integer"))
        def check(c,state):
            if "or" in c:return any(check(x,state) for x in c["or"])
            for key in ("equals","greaterThanOrEquals","lessThanOrEquals"):
                if key in c:
                    a=value(c[key]["left"],state);b=value(c[key]["right"],state)
                    if a is None:return False
                    return a==b if key=="equals" else a>=b if key=="greaterThanOrEquals" else a<=b
            raise AssertionError(c)
        def evaluate(actions,state):
            out=[]
            for a in actions:
                if "if" in a:
                    body=a["if"]
                    if check(body,state):out.extend(evaluate(body["then"],state))
                else:out.append(a["command"])
            return out
        rules=m["make_rules"](D,P,["shade","position","stop","battery","button"])
        report=next(r for r in rules if r["name"].endswith(" report"))
        state={(D,"main","windowShade","windowShade"):"open",(D,"main","windowShadeLevel","shadeLevel"):73,(D,"main","battery","battery"):38,(D,"main","button","button"):"pushed",(P,"sync","button","button"):"pushed",(P,"commandOff","button","button"):"pushed"}
        cmds=evaluate(report["actions"],state)
        self.assertEqual(len(cmds),3)
        self.assertTrue(all(c["devices"]==[P] for c in cmds))
        self.assertFalse(any(c["commands"][0]["component"]=="reportC" for c in cmds))
        close=next(r for r in rules if r["name"].endswith(" command close"))
        self.assertEqual(evaluate(close["actions"],state)[0]["commands"][0]["command"],"close")
