import unittest
from tools.edge_rules import build, SHADE_CODES

D="11111111-1111-4111-8111-111111111111"
P="22222222-2222-4222-8222-222222222222"
class CoverRulesTest(unittest.TestCase):
    def test_shade(self):
        rules=build(D,P,"cover")
        self.assertEqual(len(rules),10)
        for r,(state,code) in zip(rules,SHADE_CODES.items()):
            cond=r["actions"][0]["if"]
            self.assertEqual(cond["equals"]["right"]["string"],state)
            self.assertEqual(cond["equals"]["left"]["device"]["devices"],[D])
            command=cond["then"][0]["command"]
            self.assertEqual(command["devices"],[P])
            self.assertEqual(command["commands"][0],{"component":"shadeReport","capability":"switchLevel","command":"setLevel","arguments":[{"integer":code}]})
        for r,cmd,component in zip(rules[7:],("open","close","pause"),("commandOn","commandOff","commandStop")):
            cond=r["actions"][0]["if"]
            self.assertEqual(cond["equals"]["left"]["device"]["component"],component)
            self.assertEqual(cond["then"][0]["command"]["devices"],[D])
            self.assertEqual(cond["then"][0]["command"]["commands"][0]["command"],cmd)
    def test_duplicate(self):
        with self.assertRaises(ValueError):
            build(D,D,"cover")
