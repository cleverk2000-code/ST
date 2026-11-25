"""MQTT state transport with optional native Edge availability watchdog."""
from homeassistant.components import mqtt
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_call_later
from .const import DOMAIN, parse_state, topic

class BridgeEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = None
    _attr_is_on = None

    def __init__(self, entry):
        self.key = entry.data["device_id"]
        self._native = entry.data.get("native_edge", False) or entry.data["kind"] == "cover"
        self._attr_available = not self._native
        self._online = False
        self._cancel_watchdog = None
        self._attr_unique_id = self.key
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.key)},
            "name": entry.data[CONF_NAME],
            "manufacturer": "SmartThings",
            "model": "ST Local Edge" if self._native else "Edge MQTT bridge",
        }

    @callback
    def _stop_watchdog(self):
        if self._cancel_watchdog is not None:
            self._cancel_watchdog()
            self._cancel_watchdog = None

    _state_suffix = "state"

    @callback
    def _set_payload(self, payload):
        value = parse_state(payload)
        if value is not None or (self._native and payload == ""):
            self._attr_is_on = value
            self.async_write_ha_state()

    @callback
    def _clear_state(self):
        self._attr_is_on = None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()

        @callback
        def receive(message):
            self._set_payload(message.payload)

        self.async_on_remove(await mqtt.async_subscribe(
            self.hass, topic(self.key, self._state_suffix), receive, qos=1
        ))
        if not self._native:
            return

        @callback
        def unavailable(_now):
            self._cancel_watchdog = None
            self._attr_available = False
            self._clear_state()
            self.async_write_ha_state()

        @callback
        def availability(message):
            self._online = message.payload == "online"
            if not self._online:
                self._stop_watchdog()
                unavailable(None)
            # Require a fresh, non-retained heartbeat before declaring available.

        @callback
        def heartbeat(message):
            if not self._online:
                return
            self._stop_watchdog()
            self._attr_available = True
            self._cancel_watchdog = async_call_later(self.hass, 45, unavailable)
            self.async_write_ha_state()

        self.async_on_remove(self._stop_watchdog)
        self.async_on_remove(await mqtt.async_subscribe(
            self.hass, topic(self.key, "availability"), availability, qos=1
        ))
        self.async_on_remove(await mqtt.async_subscribe(
            self.hass, topic(self.key, "heartbeat"), heartbeat, qos=1
        ))
