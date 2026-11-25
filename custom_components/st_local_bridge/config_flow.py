"""Register a physical SmartThings device by UUID."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from .const import DOMAIN, KINDS, device_key
from .manager_flow import TOKEN, options, ManagerOptions
from .manager_api import Api
from .manager_contract import is_manager, uid
from .manager import Manager
from homeassistant.helpers.aiohttp_client import async_get_clientsession

class BridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_legacy(self, user_input=None):
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
        return self.async_show_form(step_id="legacy", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_NAME): str,
            vol.Required("device_id"): str,
            vol.Required("kind", default="switch"): vol.In(KINDS),
            vol.Optional("native_edge", default=False): bool,
        }))


    @staticmethod
    def async_get_options_flow(config_entry):
        return ManagerOptions()

    async def async_step_user(self,user_input=None):
        return self.async_show_menu(step_id="user",menu_options=["manager","legacy"])

    async def async_step_manager(self,user_input=None):
        errors={}
        if user_input:
            try:
                api=Api(async_get_clientsession(self.hass),user_input["token"].strip())
                self._managers=[(uid(d["deviceId"]),d.get("label") or d.get("name") or "ST Local Manager")
                    for d in await api.devices() if is_manager(d)]
                if not self._managers:errors["base"]="no_manager"
                else:return await self.async_step_choose_manager()
            except Exception:errors["base"]="cannot_connect"
        return self.async_show_form(step_id="manager",data_schema=TOKEN,errors=errors)

    async def async_step_choose_manager(self,user_input=None):
        errors={}
        if user_input:
            manager=uid(user_input["manager"])
            if manager not in dict(self._managers):errors["base"]="cannot_connect"
            else:
                try:await Manager(self.hass,manager).inventory()
                except Exception:errors["base"]="cannot_connect"
                else:
                    await self.async_set_unique_id("manager_"+manager)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=dict(self._managers)[manager],data={"manager":manager})
        return self.async_show_form(step_id="choose_manager",data_schema=vol.Schema({vol.Required("manager"):options(self._managers)}),errors=errors)
