#!/usr/bin/env python3
"""Generate and optionally install explicit Edge MQTT bridge rules."""
import argparse
import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError
from uuid import UUID

TYPES = {
    "switch": ("switch", "switch", "on", "off"),
    "motion": ("motionSensor", "motion", "active", "inactive"),
    "contact": ("contactSensor", "contact", "open", "closed"),
    "moisture": ("waterSensor", "water", "wet", "dry"),
    "presence": ("presenceSensor", "presence", "present", "not present"),
}
BASE = "https://api.smartthings.com/v1"
PUBLISH = "partyvoice23922.mqttpublish"

def uid(value):
    return str(UUID(value))

def operand(device, capability, attribute):
    return {"device": {"devices": [device], "component": "main",
                       "capability": capability, "attribute": attribute}}

def action(device, capability, command, arguments=None):
    item = {"component": "main", "capability": capability, "command": command}
    if arguments is not None:
        item["arguments"] = arguments
    return {"command": {"devices": [device], "commands": [item]}}

def rule(name, device, capability, attribute, value, then):
    return {"name": name, "actions": [{"if": {"equals": {
        "left": operand(device, capability, attribute), "right": {"string": value}
    }, "then": [then]}}]}

def build(device, creator, kind, on_button=None, off_button=None):
    device, creator = uid(device), uid(creator)
    ids = [device, creator]
    if kind == "switch":
        if not on_button or not off_button:
            raise ValueError("Switch needs two distinct MQTT momentary button devices")
        on_button, off_button = uid(on_button), uid(off_button)
        ids += [on_button, off_button]
    elif on_button or off_button:
        raise ValueError("Read-only sensors do not use command buttons")
    if len(set(ids)) != len(ids):
        raise ValueError("All physical and virtual device UUIDs must differ")
    cap, attr, positive, negative = TYPES[kind]
    prefix = "st/local/" + device
    name = "ST Local " + device
    result = []
    for value, payload in [(positive, "on"), (negative, "off")]:
        result.append(rule(name + " report " + payload, device, cap, attr, value,
            action(creator, PUBLISH, "publish", [
                {"string": prefix + "/state"}, {"string": payload}, {"integer": 1}
            ])))
    if kind == "switch":
        for button, command in [(on_button, "on"), (off_button, "off")]:
            result.append(rule(name + " command " + command, button, "button", "button",
                "pushed", action(device, "switch", command)))
    return result

def request(method, path, body=None):
    token = os.environ.get("ST_TOKEN")
    if not token:
        raise ValueError("Set ST_TOKEN environment variable first")
    data = json.dumps(body).encode() if body is not None else None
    req = Request(BASE + path, data=data, method=method, headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json",
        "Accept": "application/json"})
    with urlopen(req, timeout=20) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}

def listing(path, params):
    result = []
    while True:
        page = request("GET", path + "?" + urlencode(params))
        result.extend(page.get("items", []))
        link = page.get("_links", {}).get("next", {}).get("href")
        if not link:
            return result
        # Never send credentials to a different host.
        if not link.startswith(BASE + "/"):
            raise ValueError("Unexpected pagination URL")
        path = link[len(BASE):]
        if "?" not in path:
            params = {}
        else:
            from urllib.parse import parse_qsl
            path, query = path.split("?", 1)
            params = dict(parse_qsl(query))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--location", help="SmartThings location UUID")
    parser.add_argument("--list", action="store_true", help="List accessible devices")
    parser.add_argument("--device")
    parser.add_argument("--creator")
    parser.add_argument("--kind", choices=TYPES, default="switch")
    parser.add_argument("--on-button")
    parser.add_argument("--off-button")
    parser.add_argument("--apply", action="store_true", help="Actually create rules; default is dry run")
    args = parser.parse_args()
    if args.list:
        if args.apply:
            parser.error("--list and --apply are mutually exclusive")
        params = {"locationId": uid(args.location)} if args.location else {}
        for item in listing("/devices", params):
            print(json.dumps({"name": item.get("label") or item.get("name"),
                              "id": item.get("deviceId"), "location": item.get("locationId"),
                              "type": item.get("type"), "components": item.get("components", [])},
                             ensure_ascii=False))
        return
    if not args.device or not args.creator:
        parser.error("--device and --creator are required")
    rules = build(args.device, args.creator, args.kind, args.on_button, args.off_button)
    if not args.apply:
        print(json.dumps(rules, indent=2, ensure_ascii=False))
        return
    if not args.location:
        parser.error("--apply requires --location")
    location = uid(args.location)
    query = "?" + urlencode({"locationId": location})
    existing = {r["name"]: r for r in listing("/rules", {"locationId": location})}
    for body in rules:
        if body["name"] in existing:
            raise ValueError("Rule already exists: " + body["name"] + "; inspect/delete manually before reinstall")
    created = []
    try:
        for body in rules:
            response = request("POST", "/rules" + query, body)
            rule_id = response.get("id")
            if not rule_id:
                raise ValueError("Create response missing rule ID; inspect Advanced manually")
            created.append(rule_id)
            execution = response.get("executionLocation")
            if execution is None:
                execution = request("GET", "/rules/" + rule_id + query).get("executionLocation")
            print(json.dumps({"name": body["name"], "id": rule_id, "executionLocation": execution}), flush=True)
            if execution != "Local":
                raise ValueError("Rule not confirmed Local; stopping. Remove newly created rules or inspect manually.")
    except Exception:
        print("Created rule IDs (inspect/delete manually): " + ", ".join(created), file=sys.stderr)
        raise

if __name__ == "__main__":
    try:
        main()
    except (ValueError, HTTPError, OSError) as exc:
        print("Error:", exc, file=sys.stderr)
        sys.exit(1)

