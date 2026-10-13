"""Internal bootstrap only; products and settings live in the GUI."""
from homeassistant import config_entries
from .const import DOMAIN
class Flow(config_entries.ConfigFlow,domain=DOMAIN):
    VERSION=3
    async def async_step_import(self,user_input):
        await self.async_set_unique_id('pricegauge_gui_manager')
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title='PriceGauge GUI',data={'gui_manager':True})
    async def async_step_user(self,user_input=None):
        return await self.async_step_import({'gui_manager':True})
