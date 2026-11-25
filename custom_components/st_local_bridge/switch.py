"""Switch sends discrete momentary ON/OFF requests."""
from homeassistant.components import mqtt
from homeassistant.components.switch import SwitchEntity
from .entity import BridgeEntity
from .const import topic

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BridgeSwitch(entry)])

class BridgeSwitch(BridgeEntity, SwitchEntity):
    async def async_turn_on(self, **kwargs):
        await mqtt.async_publish(self.hass, topic(self.key, "on"), "pushed", qos=1, retain=False)

    async def async_turn_off(self, **kwargs):
        await mqtt.async_publish(self.hass, topic(self.key, "off"), "pushed", qos=1, retain=False)

