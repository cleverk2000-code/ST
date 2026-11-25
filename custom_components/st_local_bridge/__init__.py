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
    await hass.config_entries.async_forward_entry_setups(entry, platforms(entry))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, platforms(entry))

