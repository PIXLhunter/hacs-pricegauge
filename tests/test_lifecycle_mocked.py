"""Mocked contracts, not a live HA compatibility test."""
import asyncio
import copy
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock

BASE=Path(__file__).parents[1]/'custom_components/price_monitor'
DB={}
class Store:
    def __init__(self,hass,version,key):self.key=key
    async def async_load(self):return copy.deepcopy(DB.get(self.key))
    async def async_save(self,data):DB[self.key]=copy.deepcopy(data)
    async def async_remove(self):DB.pop(self.key,None)
class UpdateFailed(Exception):
    def __init__(self,message='',**kw):super().__init__(message);self.retry_after=kw.get('retry_after')
class AuthFailed(Exception):pass
class Coordinator:
    def __init__(self,hass,logger,**kw):self.hass=hass;self.data=None;self.kw=kw
    async def async_config_entry_first_refresh(self):
        await self._async_setup();self.data=await self._async_update_data()
    async def async_request_refresh(self):self.data=await self._async_update_data()

def module(name,**attrs):
    mod=types.ModuleType(name)
    for k,v in attrs.items():setattr(mod,k,v)
    sys.modules[name]=mod;return mod
module('homeassistant')
module('homeassistant.helpers')
module('homeassistant.helpers.storage',Store=Store)
module('homeassistant.helpers.update_coordinator',DataUpdateCoordinator=Coordinator,UpdateFailed=UpdateFailed)
module('homeassistant.helpers.aiohttp_client',async_get_clientsession=lambda hass:None)
module('homeassistant.exceptions',ConfigEntryAuthFailed=AuthFailed)
module('homeassistant.util')
from datetime import datetime,timezone
module('homeassistant.util.dt',utcnow=lambda:datetime.now(timezone.utc))
# Client is mocked; no network dependency is imported by these tests.
pkg=module('pm_test');pkg.__path__=[str(BASE)]
class PriceError(ValueError):pass
class RateLimited(PriceError):
    def __init__(self,retry_after):self.retry_after=retry_after
module('pm_test.scraper',PriceError=PriceError)
client=module('pm_test.client',fetch_price=AsyncMock(),search_offers=AsyncMock(),RateLimited=RateLimited)
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
load('pm_test.const',BASE/'const.py')
load('pm_test.budget',BASE/'budget.py')
c=load('pm_test.coordinator',BASE/'coordinator.py')
# Load package lifecycle functions under same namespace without replacing the client mocks.
spec=importlib.util.spec_from_file_location('pm_test',BASE/'__init__.py',submodule_search_locations=[str(BASE)])
init=importlib.util.module_from_spec(spec);sys.modules['pm_test']=init;spec.loader.exec_module(init)

def entry(mode='monitor',**kw):
    return types.SimpleNamespace(entry_id='id1',title='Product',version=2,
        data={'mode':mode,'url':'https://example.test/product','currency':'EUR',**kw},options={},
        async_on_unload=Mock(),add_update_listener=Mock(return_value=lambda:None))
def hass(entries):
    return types.SimpleNamespace(data={},bus=types.SimpleNamespace(async_fire=Mock()),
        config_entries=types.SimpleNamespace(async_entries=lambda domain:entries,
        async_forward_entry_setups=AsyncMock(),async_unload_platforms=AsyncMock(return_value=True),
        async_reload=AsyncMock(),async_update_entry=Mock()))
def price(n):return {'price':n,'currency':'EUR','source':'css','available':None,'ean_verified':False}
class Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        DB.clear();c.fetch_price.reset_mock();c.fetch_price.side_effect=None;c.fetch_price.return_value=price(100)
        c.search_offers.reset_mock();c.search_offers.side_effect=None
    async def test_setup_unload_reload(self):
        e=entry();h=hass([e]);self.assertTrue(await init.async_setup_entry(h,e))
        h.config_entries.async_forward_entry_setups.assert_awaited_once()
        self.assertTrue(await init.async_unload_entry(h,e))
        await init.async_reload_entry(h,e);h.config_entries.async_reload.assert_awaited_once_with('id1')
    async def test_save_before_event(self):
        e=entry();h=hass([e]);co=c.PriceCoordinator(h,e,None);await co.async_config_entry_first_refresh()
        def event(*args):self.assertEqual(DB['price_monitor.id1']['price'],80)
        h.bus.async_fire.side_effect=event;c.fetch_price.return_value=price(80)
        await co.async_request_refresh();h.bus.async_fire.assert_called_once()
    async def test_first_observation_no_event(self):
        e=entry();h=hass([e]);co=c.PriceCoordinator(h,e,None);await co.async_config_entry_first_refresh()
        h.bus.async_fire.assert_not_called()
    async def test_failed_fetch_keeps_saved(self):
        e=entry();h=hass([e]);co=c.PriceCoordinator(h,e,None);await co.async_config_entry_first_refresh()
        c.fetch_price.side_effect=PriceError('missing')
        with self.assertRaises(UpdateFailed):await co.async_request_refresh()
        self.assertEqual(DB['price_monitor.id1']['price'],100)
    async def test_rate_limit(self):
        e=entry();h=hass([e]);co=c.PriceCoordinator(h,e,None);c.fetch_price.side_effect=RateLimited(120)
        with self.assertRaises(UpdateFailed) as ex:await co.async_config_entry_first_refresh()
        self.assertEqual(ex.exception.retry_after,120)
    async def test_no_key_no_api(self):
        e=entry('search',query='product');h=hass([e]);co=c.PriceCoordinator(h,e,None)
        await co.async_config_entry_first_refresh();c.search_offers.assert_not_awaited()
        self.assertEqual(co.data['discovery_status'],'no_api_key')
    async def test_discovery_cached(self):
        e=entry('search',query='product',api_key='key');h=hass([e]);co=c.PriceCoordinator(h,e,None)
        c.search_offers.return_value={'count':1,'offers':[{'seller':'test'}]}
        await co.async_config_entry_first_refresh();await co.async_request_refresh()
        c.search_offers.assert_awaited_once();self.assertEqual(co.data['count'],1)
    async def test_auth_propagates(self):
        e=entry('search',query='product',api_key='key');h=hass([e]);co=c.PriceCoordinator(h,e,None)
        c.search_offers.side_effect=AuthFailed()
        with self.assertRaises(AuthFailed):await co.async_config_entry_first_refresh()
    async def test_migration_preserves_entity_identity(self):
        e=entry('search',query='old');e.version=1;e.options={'query':'new','api_key':'key'}
        h=hass([e]);self.assertTrue(await init.async_migrate_entry(h,e))
        kw=h.config_entries.async_update_entry.call_args.kwargs
        self.assertEqual(kw['data']['query'],'new');self.assertEqual(kw['version'],2)
        self.assertIsNone(kw['unique_id']);self.assertEqual(e.entry_id,'id1')
    async def test_remove_storage(self):
        e=entry();h=hass([e]);DB['price_monitor.id1']={'price':10}
        await init.async_remove_entry(h,e);self.assertNotIn('price_monitor.id1',DB)
