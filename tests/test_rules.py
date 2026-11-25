"""Pure unit tests for the topic and rule contract."""
import unittest
from tools.st_rules import build, TYPES
import runpy
from pathlib import Path
contract = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'custom_components/st_local_bridge/const.py'))
topic, parse_state = contract['topic'], contract['parse_state']
D = "11111111-1111-4111-8111-111111111111"
C = "22222222-2222-4222-8222-222222222222"
A = "33333333-3333-4333-8333-333333333333"
B = "44444444-4444-4444-8444-444444444444"

class RuleTests(unittest.TestCase):
    def test_switch(self):
        rules = build(D, C, "switch", A, B)
        self.assertEqual(len(rules), 4)
        for idx, value in enumerate(("on", "off")):
            report = rules[idx]["actions"][0]["if"]
            self.assertEqual(report["equals"]["left"]["device"]["devices"], [D])
            pub = report["then"][0]["command"]
            self.assertEqual(pub["devices"], [C])
            self.assertEqual(pub["commands"][0]["arguments"][0]["string"], topic(D, "state"))
            self.assertEqual(pub["commands"][0]["arguments"][1]["string"], value)
            cmd = rules[idx+2]["actions"][0]["if"]
            self.assertEqual(cmd["equals"]["left"]["device"]["devices"], [[A, B][idx]])
            self.assertEqual(cmd["then"][0]["command"]["devices"], [D])
            self.assertEqual(cmd["then"][0]["command"]["commands"][0]["command"], value)
    def test_sensors(self):
        for kind in TYPES:
            if kind == "switch":
                continue
            rules = build(D, C, kind)
            self.assertEqual(len(rules), 2)
            self.assertEqual(rules[0]["actions"][0]["if"]["equals"]["right"]["string"], TYPES[kind][2])
    def test_invalid(self):
        for args in [(D,C,"switch",A,A), (D,C,"switch"), (D,D,"motion"), (D,C,"motion",A,B)]:
            with self.assertRaises(ValueError):
                build(*args)
    def test_payload(self):
        self.assertIs(parse_state("on"), True)
        self.assertIs(parse_state("off"), False)
        self.assertIsNone(parse_state("pushed"))
        self.assertIsNone(parse_state("unknown"))

if __name__ == "__main__":
    unittest.main()

