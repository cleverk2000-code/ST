"""Generate Rules for a dedicated ST Local Edge proxy (dry run by default)."""
import argparse
import json
try:
    from .st_rules import TYPES, uid, rule, action
except ImportError:
    from st_rules import TYPES, uid, rule, action

def build(physical, proxy, kind="switch"):
    physical, proxy = uid(physical), uid(proxy)
    if physical == proxy:
        raise ValueError("Physical and proxy device must differ")
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
    p.add_argument("--kind", choices=TYPES, default="switch")
    args = p.parse_args()
    print(json.dumps(build(args.device, args.proxy, args.kind), indent=2))

if __name__ == "__main__":
    main()
