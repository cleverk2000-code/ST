"""Shared state transport; no optimistic state or retained commands."""
from homeassistant.components import mqtt
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, parse_state, topic

class BridgeEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = None
    _attr_is_on = None

    def __init__(self, entry):
        self.key = entry.data["device_id"]
        self._attr_unique_id = self.key
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.key)},
            "name": entry.data[CONF_NAME],
            "manufacturer": "SmartThings",
            "model": "Edge MQTT bridge",
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        @callback
        def receive(message):
            value = parse_state(message.payload)
            if value is not None:
                self._attr_is_on = value
                self.async_write_ha_state()
        self.async_on_remove(await mqtt.async_subscribe(
            self.hass, topic(self.key, "state"), receive, qos=1
        ))

