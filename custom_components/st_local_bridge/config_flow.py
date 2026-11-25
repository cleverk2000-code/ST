"""Register a physical SmartThings device by UUID."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from .const import DOMAIN, KINDS, device_key
from .manager_flow import TOKEN, options, ManagerOptions, LegacyOptions
from .manager_api import Api
from .manager_contract import is_manager, uid, hub_id, specs
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
        return ManagerOptions() if "manager" in config_entry.data else LegacyOptions()

    async def async_step_user(self,user_input=None):
        return self.async_show_menu(step_id="user",menu_options=["manager","legacy"])

    async def async_step_manager(self,user_input=None):
        errors={}
        if user_input:
            try:
                self._api=Api(async_get_clientsession(self.hass),user_input["token"].strip())
                self._managers=[(uid(d["deviceId"]),d.get("label") or d.get("name") or "ST Local Manager")
                    for d in await self._api.devices() if is_manager(d)]
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
                    self._manager=manager
                    try:
                        info=await self._api.device(manager)
                        records=(await Manager(self.hass,manager).load())["records"]
                        self._choices=[(uid(d["deviceId"]),f"{d.get('label') or d.get('name')} ({', '.join(specs(d))})")
                            for d in await self._api.devices() if hub_id(d)==hub_id(info) and d.get("locationId")==info.get("locationId") and specs(d)
                            and records.get(d["deviceId"],{}).get("phase")!="active"]
                    except Exception:
                        errors["base"]="cannot_connect"
                    else:
                        return await self.async_step_initial_select()
        return self.async_show_form(step_id="choose_manager",data_schema=vol.Schema({vol.Required("manager"):options(self._managers)}),errors=errors)

    async def async_step_initial_select(self,user_input=None):
        if user_input is not None:
            chosen=user_input.get("devices",[])
            if not chosen:
                self._api=None
                return self.async_create_entry(title=dict(self._managers)[self._manager],data={"manager":self._manager})
            if set(chosen)<=set(dict(self._choices)):
                self._task=self.hass.async_create_task(Manager(self.hass,self._manager).add_many(self._api,chosen))
                return await self.async_step_initial_progress()
        return self.async_show_form(step_id="initial_select",data_schema=vol.Schema({vol.Optional("devices",default=[]):options(self._choices,True)}))

    async def async_step_initial_progress(self,user_input=None):
        if not self._task.done():
            return self.async_show_progress(step_id="initial_progress",progress_action="provisioning",progress_task=self._task)
        try:self._result=self._task.result()
        except Exception as exc:self._result={"operation":type(exc).__name__}
        self._api=None
        return self.async_show_progress_done(next_step_id="initial_result")

    async def async_step_initial_result(self,user_input=None):
        if user_input is not None:return self.async_create_entry(title=dict(self._managers)[self._manager],data={"manager":self._manager})
        names=dict(self._choices)
        result="\n".join(f"{names.get(k,k)}: {v}" for k,v in self._result.items())
        return self.async_show_form(step_id="initial_result",data_schema=vol.Schema({}),description_placeholders={"result":result})
