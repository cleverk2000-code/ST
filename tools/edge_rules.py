"""Generate Rules for a dedicated ST Local Edge proxy (dry run by default)."""
import argparse
import json
try:
    from .st_rules import TYPES, uid, rule, action
except ImportError:
    from st_rules import TYPES, uid, rule, action

SHADE_CODES = {"closed":0,"open":1,"opening":2,"closing":3,"partially open":4,"paused":5,"unknown":6}

def cover_rules(physical, proxy):
    prefix = "ST Edge " + physical
    rules = []
    for observed, code in SHADE_CODES.items():
        report = action(proxy, "switchLevel", "setLevel", [{"integer": code}])
        report["command"]["commands"][0]["component"] = "shadeReport"
        r = rule(prefix + " shade " + observed, physical, "windowShade", "windowShade", observed, report)
        r["actions"][0]["if"]["equals"]["left"]["device"]["trigger"] = "Always"
        rules.append(r)
    for command, component in (("open","commandOn"),("close","commandOff"),("pause","commandStop")):
        r = rule(prefix + " command " + command, proxy, "button", "button", "pushed",
                 action(physical, "windowShade", command))
        operand = r["actions"][0]["if"]["equals"]["left"]["device"]
        operand["component"] = component
        operand["trigger"] = "Always"
        rules.append(r)
    return rules

def build(physical, proxy, kind="switch"):
    physical, proxy = uid(physical), uid(proxy)
    if physical == proxy:
        raise ValueError("Physical and proxy device must differ")
    if kind == "cover":
        return cover_rules(physical, proxy)
    capability, attribute, positive, negative = TYPES[kind]
    prefix = "ST Edge " + physical
    rules = []
    for observed, value in ((positive, "on"), (negative, "off")):
        r = rule(prefix + " report " + value, physical, capability, attribute, observed,
                 action(proxy, "switch", value))
        r["actions"][0]["if"]["equals"]["left"]["device"]["trigger"] = "Always"
        rules.append(r)
    if kind == "switch":
        for value, component in (("on", "commandOn"), ("off", "commandOff")):
            r = rule(prefix + " command " + value, proxy, "button", "button", "pushed",
                     action(physical, "switch", value))
            operand = r["actions"][0]["if"]["equals"]["left"]["device"]
            operand["component"] = component
            operand["trigger"] = "Always"
            rules.append(r)
    return rules

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--device", required=True)
    p.add_argument("--proxy", required=True)
    p.add_argument("--kind", choices=(*TYPES, "cover"), default="switch")
    args = p.parse_args()
    print(json.dumps(build(args.device, args.proxy, args.kind), indent=2))

if __name__ == "__main__":
    main()
