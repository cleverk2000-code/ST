import unittest
from tools.edge_rules import build

D = "11111111-1111-4111-8111-111111111111"
P = "22222222-2222-4222-8222-222222222222"

class EdgeRulesTests(unittest.TestCase):
    def test_switch(self):
        rules = build(D, P)
        self.assertEqual(len(rules), 4)
        for i, value in enumerate(("on", "off")):
            report = rules[i]["actions"][0]["if"]
            self.assertEqual(report["equals"]["left"]["device"]["devices"], [D])
            self.assertEqual(report["then"][0]["command"]["devices"], [P])
            self.assertEqual(report["then"][0]["command"]["commands"][0]["command"], value)
            command = rules[i+2]["actions"][0]["if"]
            self.assertEqual(command["equals"]["left"]["device"]["component"], ("commandOn","commandOff")[i])
            self.assertEqual(command["equals"]["left"]["device"]["trigger"], "Always")
            self.assertEqual(command["then"][0]["command"]["devices"], [D])
            self.assertEqual(command["then"][0]["command"]["commands"][0]["command"], value)
    def test_sensor(self):
        self.assertEqual(len(build(D, P, "motion")), 2)
    def test_duplicate(self):
        with self.assertRaises(ValueError):
            build(D, D)

if __name__ == "__main__":
    unittest.main()
