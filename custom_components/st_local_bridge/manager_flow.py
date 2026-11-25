"""Manager setup and bulk add/remove UI. PAT is ephemeral."""
import asyncio
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType, SelectSelector, SelectSelectorConfig, SelectOptionDict
from homeassistant.components import mqtt
from .manager_api import Api
from .manager_contract import is_manager,hub_id,specs,uid
from .manager import Manager

TOKEN=vol.Schema({vol.Required("token"):TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))})

def options(items,multiple=False):
    return SelectSelector(SelectSelectorConfig(options=[SelectOptionDict(value=k,label=v) for k,v in items],multiple=multiple))

class ManagerOptions(config_entries.OptionsFlow):
    def __init__(self):
        self._mode=None;self._api=None;self._task=None;self._choices=[];self._result=None
    async def async_step_init(self,user_input=None):
        return self.async_show_menu(step_id="init",menu_options=["add","remove","sync"])
    async def async_step_add(self,user_input=None):
        self._mode="add";return await self.async_step_token(user_input)
    async def async_step_remove(self,user_input=None):
        self._mode="remove";return await self.async_step_token(user_input)
    async def async_step_sync(self,user_input=None):
        mgr=Manager(self.hass,self.config_entry.data["manager"])
        try:
            data=await mgr.load()
            for key,r in data["records"].items():
                if r["phase"]=="active":await mgr.rpc("sync",physical=key)
            await mgr.republish()
        except Exception:
            return self.async_abort(reason="manager_unreachable")
        return self.async_create_entry(title="",data={})
    async def async_step_token(self,user_input=None):
        errors={}
        if user_input:
            try:
                self._api=Api(async_get_clientsession(self.hass),user_input["token"].strip())
                mgr=Manager(self.hass,self.config_entry.data["manager"])
                info=await self._api.device(mgr.manager)
                if not is_manager(info):raise ValueError("manager")
                await mgr.inventory()
                records=(await mgr.load())["records"]
                if self._mode=="add":
                    devices=await self._api.devices()
                    self._choices=[(uid(d["deviceId"]),f"{d.get('label') or d.get('name')} ({', '.join(specs(d))})")
                        for d in devices if hub_id(d)==hub_id(info) and d.get("locationId")==info.get("locationId") and specs(d)
                        and records.get(d["deviceId"],{}).get("phase")!="active"]
                else:self._choices=[(k,f"{v['name']} ({v['phase']})") for k,v in records.items()]
                if not self._choices:return self.async_abort(reason="no_devices")
                return await self.async_step_select()
            except Exception:
                self._api=None;errors["base"]="cannot_connect"
        return self.async_show_form(step_id="token",data_schema=TOKEN,errors=errors)
    async def async_step_select(self,user_input=None):
        if user_input:
            valid={k for k,_ in self._choices}
            chosen=user_input["devices"]
            if chosen and set(chosen)<=valid:
                mgr=Manager(self.hass,self.config_entry.data["manager"])
                operation=mgr.add_many if self._mode=="add" else mgr.remove_many
                self._task=self.hass.async_create_task(operation(self._api,chosen))
                return await self.async_step_progress()
        return self.async_show_form(step_id="select",data_schema=vol.Schema({vol.Required("devices"):options(self._choices,True)}))
    async def async_step_progress(self,user_input=None):
        if not self._task.done():
            return self.async_show_progress(step_id="progress",progress_action="provisioning",progress_task=self._task)
        try:self._result=self._task.result()
        except Exception as exc:self._result={"operation":type(exc).__name__}
        self._api=None
        return self.async_show_progress_done(next_step_id="result")
    async def async_step_result(self,user_input=None):
        if user_input is not None:return self.async_create_entry(title="",data={})
        names=dict(self._choices)
        result="\n".join(f"{names.get(k,k)}: {v}" for k,v in (self._result or {}).items())
        return self.async_show_form(step_id="result",data_schema=vol.Schema({}),description_placeholders={"result":result})
