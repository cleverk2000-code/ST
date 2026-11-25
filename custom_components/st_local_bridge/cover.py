"""Physical shade state reported by SmartThings local Rules."""
from homeassistant.components import mqtt
from homeassistant.components.cover import CoverEntity, CoverDeviceClass, CoverEntityFeature
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from .entity import BridgeEntity
from .const import topic

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BridgeCover(entry)])

class BridgeCover(BridgeEntity, CoverEntity):
    _state_suffix = "shade"
    _attr_device_class = CoverDeviceClass.WINDOW
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    _attr_is_closed = None
    _attr_is_opening = False
    _attr_is_closing = False

    @callback
    def _clear_state(self):
        self._attr_is_closed = None
        self._attr_is_opening = False
        self._attr_is_closing = False

    @callback
    def _set_payload(self, payload):
        if payload not in ("", "closed", "open", "opening", "closing", "partially open", "paused", "unknown"):
            return
        self._clear_state()
        self._attr_is_opening = payload == "opening"
        self._attr_is_closing = payload == "closing"
        if payload == "closed":
            self._attr_is_closed = True
        elif payload in ("open", "partially open"):
            self._attr_is_closed = False
        self.async_write_ha_state()

    async def _command(self, suffix):
        if not self.available:
            raise HomeAssistantError("ST Local Edge is offline")
        await mqtt.async_publish(self.hass, topic(self.key, suffix), "pushed", qos=1, retain=False)

    async def async_open_cover(self, **kwargs):
        await self._command("on")

    async def async_close_cover(self, **kwargs):
        await self._command("off")

    async def async_stop_cover(self, **kwargs):
        await self._command("stop")
