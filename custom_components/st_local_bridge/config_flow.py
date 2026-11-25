"""Register a physical SmartThings device by UUID."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from .const import DOMAIN, KINDS, device_key

class BridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                key = device_key(user_input["device_id"])
            except (ValueError, AttributeError):
                errors["device_id"] = "invalid_uuid"
            else:
                name = user_input[CONF_NAME].strip()
                if not name:
                    errors[CONF_NAME] = "invalid_name"
                else:
                    await self.async_set_unique_id(key)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=name, data={
                        CONF_NAME: name, "device_id": key, "kind": user_input["kind"],
                        "native_edge": user_input.get("native_edge", False) or user_input["kind"] == "cover"
                    })
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_NAME): str,
            vol.Required("device_id"): str,
            vol.Required("kind", default="switch"): vol.In(KINDS),
            vol.Optional("native_edge", default=False): bool,
        }))

