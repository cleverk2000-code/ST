"""Local MQTT bridge for SmartThings Edge."""
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

def platforms(entry: ConfigEntry) -> list[Platform]:
    kind = entry.data["kind"]
    return [Platform.COVER if kind == "cover" else Platform.SWITCH if kind == "switch" else Platform.BINARY_SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await mqtt.async_wait_for_mqtt_client(hass):
        raise ConfigEntryNotReady("MQTT client unavailable")
    if "manager" in entry.data:
        from .manager import Manager
        from .manager_contract import root
        mgr=Manager(hass,entry.data["manager"])
        async def online(message):
            if message.payload=="online":
                await mgr.republish()
        entry.async_on_unload(await mqtt.async_subscribe(hass,root(mgr.manager)+"/availability",online,qos=1))
        await mgr.republish()
        return True
    await hass.config_entries.async_forward_entry_setups(entry, platforms(entry))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if "manager" in entry.data:return True
    return await hass.config_entries.async_unload_platforms(entry, platforms(entry))


async def async_remove_entry(hass,entry):
    """Do not silently delete cloud resources with an expired PAT. Disable local discovery; retain journal."""
    if "manager" not in entry.data:return
    from .manager import Manager
    mgr=Manager(hass,entry.data["manager"])
    async with mgr.lock:
        data=await mgr.load()
        for physical,record in data["records"].items():
            try:await mgr.rpc("deactivate",physical=physical)
            except Exception:pass
            try:await mgr.publish_discovery(record,True)
            except Exception:pass
            record["phase"]="removing"
        await mgr.save(data)
