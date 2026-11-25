"""Read-only physical sensor reports."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from .entity import BridgeEntity

CLASSES = {
    "motion": BinarySensorDeviceClass.MOTION,
    "contact": BinarySensorDeviceClass.DOOR,
    "moisture": BinarySensorDeviceClass.MOISTURE,
    "presence": BinarySensorDeviceClass.PRESENCE,
}

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BridgeSensor(entry)])

class BridgeSensor(BridgeEntity, BinarySensorEntity):
    def __init__(self, entry):
        super().__init__(entry)
        self._attr_device_class = CLASSES[entry.data["kind"]]

