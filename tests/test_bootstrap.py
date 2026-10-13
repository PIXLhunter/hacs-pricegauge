import importlib.util,sys,types,unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock
BASE=Path(__file__).parents[1]/'custom_components/price_monitor'
def mod(name,**attrs):
    m=types.ModuleType(name)
    for k,v in attrs.items():setattr(m,k,v)
    sys.modules[name]=m;return m
class Schema:
    def __init__(self,*args,**kw):pass
mod('voluptuous',Schema=Schema,Optional=lambda v:v,ALLOW_EXTRA=True)
mod('homeassistant.components')
front=mod('homeassistant.components.frontend',async_register_built_in_panel=Mock())
ws=mod('homeassistant.components.websocket_api',async_register_command=Mock())
mod('homeassistant.components.http',StaticPathConfig=lambda *args:args)
mod('homeassistant.const',EVENT_HOMEASSISTANT_STOP='stop')
mod('homeassistant.helpers.event',async_track_time_interval=lambda *args:lambda:None)
mod('boot.const',DOMAIN='price_monitor',VERSION='0.3.0')
class Manager:
    def __init__(self,hass):self.net=types.SimpleNamespace(close=AsyncMock());self.start=AsyncMock();self.log=Mock();self.import_entry=AsyncMock()
mod('boot.manager',Manager=Manager);mod('boot.api',command=Mock())
spec=importlib.util.spec_from_file_location('boot',BASE/'__init__.py',submodule_search_locations=[str(BASE)])
b=importlib.util.module_from_spec(spec);sys.modules['boot']=b;spec.loader.exec_module(b)
class Tests(unittest.IsolatedAsyncioTestCase):
    def hass(self):
        def task(coro):coro.close()
        return types.SimpleNamespace(data={},http=types.SimpleNamespace(async_register_static_paths=AsyncMock()),
            bus=types.SimpleNamespace(async_listen_once=Mock()),async_create_task=task,
            config_entries=types.SimpleNamespace(flow=types.SimpleNamespace(async_init=AsyncMock()),async_forward_entry_setups=AsyncMock()))
    async def test_empty_bootstrap_registers_panel(self):
        h=self.hass();self.assertTrue(await b.async_setup(h,{}))
        self.assertIn('price_monitor',h.data);front.async_register_built_in_panel.assert_called()
        h.http.async_register_static_paths.assert_awaited_once()
    async def test_legacy_failure_does_not_fetch(self):
        h=self.hass();await b.async_setup(h,{})
        e=types.SimpleNamespace(data={'mode':'monitor'})
        self.assertTrue(await b.async_setup_entry(h,e));h.data['price_monitor'].import_entry.assert_awaited_once()
    async def test_internal_sensor_entry(self):
        h=self.hass();await b.async_setup(h,{})
        e=types.SimpleNamespace(data={'gui_manager':True})
        self.assertTrue(await b.async_setup_entry(h,e));h.config_entries.async_forward_entry_setups.assert_awaited_once()
