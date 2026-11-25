"""Transactional setup of local bridge Rules and MQTT Discovery."""
import asyncio
import json
import logging
from uuid import uuid4
from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers.storage import Store
from .manager_contract import uid, root, hub_id, driver_id, components, specs, make_rules, discovery, REQUIRED_COMPONENTS, is_manager
from .manager_api import ApiError

_LOGGER=logging.getLogger(__name__)
DOMAIN="st_local_bridge"

class ManagerError(Exception): pass

class Manager:
    def __init__(self,hass,manager):
        self.hass=hass;self.manager=uid(manager)
        self.store=Store(hass,1,f"{DOMAIN}.manager.{self.manager}")
        self.lock=hass.data.setdefault(DOMAIN,{}).setdefault("manager_locks",{}).setdefault(self.manager,asyncio.Lock())
    async def load(self):
        return await self.store.async_load() or {"records":{}}
    async def save(self,data): await self.store.async_save(data)
    async def publish(self,topic,payload,retain=False):
        await mqtt.async_publish(self.hass,topic,payload,qos=1,retain=retain)
    async def rpc(self,op,**kwargs):
        req=str(uuid4()); future=asyncio.get_running_loop().create_future()
        @callback
        def received(msg):
            try:
                data=json.loads(msg.payload)
                if data.get("request")==req and not future.done(): future.set_result(data)
            except (ValueError,TypeError,AttributeError): pass
        topic=f"{root(self.manager)}/reply/{req}"
        unsubscribe=await mqtt.async_subscribe(self.hass,topic,received,qos=1)
        cancel_status=None
        try:
            # HA subscribes asynchronously; do not send the request before SUBACK.
            ready=asyncio.Event()
            monitor=getattr(mqtt,"async_on_subscribe_done",None)
            if monitor:
                import inspect
                cancel_status=monitor(self.hass,topic,qos=1,on_subscribe_status=ready.set)
                if inspect.isawaitable(cancel_status):cancel_status=await cancel_status
                await asyncio.wait_for(ready.wait(),15)
            payload=json.dumps({"request":req,"op":op,**kwargs})
            for _ in range(3):
                await self.publish(f"{root(self.manager)}/control",payload)
                try:
                    reply=await asyncio.wait_for(asyncio.shield(future),8)
                    if reply.get("ok") is not True: raise ManagerError(f"Manager rejected {op}")
                    return reply
                except TimeoutError:continue
            raise ManagerError(f"Manager response timeout: {op}")
        finally:
            if callable(cancel_status):cancel_status()
            if not future.done():future.cancel()
            unsubscribe()
    async def inventory(self):
        result=(await self.rpc("inventory")).get("devices",{})
        return result if isinstance(result,dict) else {}
    async def publish_discovery(self,record,remove=False):
        for topic,config in discovery(self.manager,record):
            await self.publish(topic,"" if remove else json.dumps(config,ensure_ascii=False),True)
    async def republish(self):
        async with self.lock:
            data=await self.load()
            for record in data["records"].values():
                if record.get("phase")=="active": await self.publish_discovery(record)
    @staticmethod
    def assert_proxy(manager,device,physical,proxy,inventory):
        if uid(device["deviceId"])!=uid(proxy) or uid(proxy)==uid(physical): raise ManagerError("Proxy identity mismatch")
        if device.get("type")!="LAN" or device.get("locationId")!=manager.get("locationId") or hub_id(device)!=hub_id(manager):raise ManagerError("Proxy location/hub mismatch")
        if driver_id(manager) and driver_id(device)!=driver_id(manager):raise ManagerError("Proxy driver mismatch")
        if not REQUIRED_COMPONENTS.issubset(components(device)):raise ManagerError("Proxy profile mismatch")
        if uid(inventory[physical]["proxy"])!=uid(proxy):raise ManagerError("Proxy inventory mismatch")
    async def get_proxy(self,api,manager,physical):
        inv=await self.inventory()
        if physical not in inv:
            await self.rpc("create",physical=physical)
            for _ in range(30):
                await asyncio.sleep(2)
                inv=await self.inventory()
                if physical in inv:break
        if physical not in inv:raise ManagerError("Proxy creation timed out")
        proxy=uid(inv[physical]["proxy"])
        for _ in range(10):
            try:
                device=await api.device(proxy);break
            except ApiError as exc:
                if exc.status!=404:raise
                await asyncio.sleep(2)
        else:raise ManagerError("Proxy not visible in SmartThings")
        self.assert_proxy(manager,device,physical,proxy,inv)
        return proxy
    @staticmethod
    def matches(rule,expected):
        # API may attach action IDs; strip only server metadata, never ignore actual commands.
        def clean(v):
            if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if k not in {"actionId","conditionId"}}
            if isinstance(v,list):return [clean(x) for x in v]
            return v
        return rule.get("name")==expected["name"] and clean(rule.get("actions"))==clean(expected["actions"])
    async def install_rules(self,api,record,data):
        loc=record["location"]; existing=await api.rules(loc)
        for body in make_rules(record["physical"],record["proxy"],record["fields"]):
            named=[r for r in existing if r.get("name")==body["name"]]
            recorded=record["rules"].get(body["name"])
            if recorded and not named:
                try:
                    old=await api.rule(loc,uid(recorded))
                    named=[{"id":recorded,"name":old.get("name")}]
                except ApiError as exc:
                    if exc.status!=404:raise
            if len(named)>1:raise ManagerError("Duplicate Rule name; cleanup required")
            if named:
                rid=uid(named[0]["id"])
                detail=await api.rule(loc,rid)
                if detail.get("name")!=body["name"] or (recorded!=rid and not self.matches(detail,body)):raise ManagerError("Existing Rule contents differ")
            else:
                created=await api.create_rule(loc,body)
                rid=uid(created["id"])
                record["rules"][body["name"]]=rid
                await self.save(data)
                detail=await api.rule(loc,rid)
            record["rules"][body["name"]]=rid
            await self.save(data)
            if str(detail.get("executionLocation","")).lower()!="local":raise ManagerError("Rule not Local: "+body["name"])
    async def add_many(self,api,physical_ids):
        async with self.lock:
            manager=await api.device(self.manager)
            if not is_manager(manager):raise ManagerError("Wrong manager")
            data=await self.load(); records=data["records"];results={}
            for key in physical_ids:
                physical=uid(key)
                try:
                    dev=await api.device(physical)
                    if hub_id(dev)!=hub_id(manager) or dev.get("locationId")!=manager.get("locationId"):raise ManagerError("Physical device belongs to another hub")
                    fields=specs(dev)
                    if not fields:raise ManagerError("Unsupported or non-local device")
                    status=await api.status(physical)
                    unit=status.get("components",{}).get("main",{}).get("temperatureMeasurement",{}).get("temperature",{}).get("unit")
                    if "temperature" in fields and unit not in {"C","F","°C","°F"}:raise ManagerError("Temperature unit unknown")
                    record=records.get(physical)
                    if record and record.get("phase")=="active":
                        results[physical]="Already active";continue
                    if record and set(record["fields"])!=set(fields):raise ManagerError("Capabilities changed; remove and add again")
                    if not record:
                        cats=[x.get("name","").lower() for c in dev.get("components",[]) for x in c.get("categories",[])]
                        record={"physical":physical,"location":uid(dev["locationId"]),"name":dev.get("label") or dev.get("name") or physical,
                            "model":dev.get("deviceModel"),"fields":fields,"rules":{},"phase":"pending","light":any("light" in x for x in cats),
                            "temperature_unit":"°F" if unit in {"F","°F"} else "°C"}
                        records[physical]=record;await self.save(data)
                    proxy=await self.get_proxy(api,manager,physical)
                    if record.get("proxy") and record["proxy"]!=proxy:raise ManagerError("Proxy changed; remove stale registration first")
                    record["proxy"]=proxy;await self.save(data)
                    await self.rpc("deactivate",physical=physical)
                    await self.install_rules(api,record,data)
                    # Discovery is enabled only after every Rule is verified Local.
                    await self.rpc("activate",physical=physical,fields=record["fields"])
                    record["phase"]="active";await self.save(data)
                    await self.publish_discovery(record)
                    results[physical]="Active"
                except Exception as exc:
                    # Keep the journal so retries/removal can recover partial cloud mutations.
                    record=records.get(physical)
                    if record and record.get("phase")!="active":
                        record["phase"]="failed";await self.save(data)
                        try: await self.rpc("deactivate",physical=physical)
                        except Exception: pass
                    results[physical]=str(exc) if isinstance(exc,(ManagerError,ApiError)) else type(exc).__name__
            return results
    async def remove_many(self,api,physical_ids):
        async with self.lock:
            manager=await api.device(self.manager)
            if not is_manager(manager):raise ManagerError("Wrong manager")
            data=await self.load();records=data["records"];results={}
            for key in physical_ids:
                physical=uid(key);record=records.get(physical)
                if not record:continue
                try:
                    record["phase"]="removing";await self.save(data)
                    await self.publish_discovery(record,True)
                    inv=await self.inventory()
                    if physical in inv:
                        proxy=uid(inv[physical]["proxy"])
                        if record.get("proxy") and record["proxy"]!=proxy:raise ManagerError("Proxy mismatch")
                        self.assert_proxy(manager,await api.device(proxy),physical,proxy,inv)
                        await self.rpc("deactivate",physical=physical)
                        record["proxy"]=proxy;await self.save(data)
                    proxy=record.get("proxy")
                    if proxy:
                        expected={r["name"]:r for r in make_rules(physical,proxy,record["fields"])}
                        candidates=dict(record["rules"])
                        for item in await api.rules(record["location"]):
                            name=item.get("name")
                            if name not in expected:continue
                            rid=uid(item["id"])
                            if name in candidates and candidates[name]!=rid:raise ManagerError("Duplicate Rule; manual review needed")
                            candidates[name]=rid
                        # Use recorded IDs directly even if the list endpoint omits them.
                        for name,rid in candidates.items():
                            if name not in expected:raise ManagerError("Unknown Rule ownership")
                            try: detail=await api.rule(record["location"],uid(rid))
                            except ApiError as exc:
                                if exc.status==404:continue
                                raise
                            if detail.get("name")!=name or (record["rules"].get(name)!=rid and not self.matches(detail,expected[name])):raise ManagerError("Rule ownership mismatch")
                            await api.delete_rule(record["location"],rid)
                        # Never delete a physical device. Only the verified proxy inventory ID.
                        if physical in inv:await api.delete_device(proxy)
                        else:
                            # If inventory is missing but the device still exists, refuse to guess.
                            try: await api.device(proxy)
                            except ApiError as exc:
                                if exc.status!=404:raise
                            else:raise ManagerError("Proxy not in manager inventory; manual review needed")
                    del records[physical];await self.save(data);results[physical]="Removed"
                except Exception as exc:
                    results[physical]=str(exc) if isinstance(exc,(ManagerError,ApiError)) else type(exc).__name__
            return results
