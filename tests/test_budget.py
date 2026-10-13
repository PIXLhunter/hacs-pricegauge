import asyncio
import copy
import importlib.util
import sys
import types
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB = {}
class Store:
    def __init__(self, hass, version, key): self.key = key
    async def async_load(self): return copy.deepcopy(DB.get(self.key))
    async def async_save(self, value): DB[self.key] = copy.deepcopy(value)

for name in ('homeassistant', 'homeassistant.helpers', 'homeassistant.helpers.storage'):
    sys.modules[name] = types.ModuleType(name)
sys.modules['homeassistant.helpers.storage'].Store = Store
p = Path(__file__).parents[1] / 'custom_components/price_monitor/budget.py'
spec = importlib.util.spec_from_file_location('budget', p)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

def config(query='product', **kw):
    return dict(mode='search', query=query, api_key='test-key', monthly_budget=250,
                reserve=25, checks_per_month=4, reset_day=1, **kw)

def hass(configs):
    entries = [types.SimpleNamespace(data=s, options={}) for s in configs]
    return types.SimpleNamespace(config_entries=types.SimpleNamespace(async_entries=lambda domain: entries))

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)
class Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self): DB.clear()
    async def test_no_key(self):
        s=config();s['api_key']=''
        r=await b.DiscoveryBudget(hass([s])).reserve(s,now=NOW)
        self.assertEqual(r['reason'],'no_api_key')
    async def test_due_gate(self):
        s=config();m=b.DiscoveryBudget(hass([s]))
        self.assertTrue((await m.reserve(s,now=NOW))['allowed'])
        self.assertEqual((await m.reserve(s,now=NOW))['reason'],'cached_not_due')
        self.assertTrue((await m.reserve(s,now=NOW+timedelta(days=8)))['allowed'])
    async def test_manual_cap(self):
        s=config();m=b.DiscoveryBudget(hass([s]))
        results=[await m.reserve(s,force=True,now=NOW) for _ in range(8)]
        self.assertEqual(sum(r['allowed'] for r in results),4)
    async def test_concurrent_cap(self):
        s=config();m=b.DiscoveryBudget(hass([s]))
        rs=await asyncio.gather(*(m.reserve(s,force=True,now=NOW) for _ in range(30)))
        self.assertEqual(sum(r['allowed'] for r in rs),4)
    async def test_global_budget(self):
        configs=[config(str(i)) for i in range(100)]
        m=b.DiscoveryBudget(hass(configs))
        rs=[]
        for _ in range(5):
            rs.extend(await asyncio.gather(*(m.reserve(s,force=True,now=NOW) for s in configs)))
        self.assertEqual(sum(r['allowed'] for r in rs),225)
    async def test_restart(self):
        s=config();h=hass([s]);m=b.DiscoveryBudget(h)
        for _ in range(4): await m.reserve(s,force=True,now=NOW)
        m=b.DiscoveryBudget(h)
        self.assertFalse((await m.reserve(s,force=True,now=NOW))['allowed'])
    async def test_cache_survives_reset(self):
        s=config();m=b.DiscoveryBudget(hass([s]))
        await m.reserve(s,now=NOW)
        await m.save_cache(s,{'count':1,'offers':[{'seller':'test'}]})
        r=await m.reserve(s,now=datetime(2026,11,1,tzinfo=timezone.utc))
        self.assertTrue(r['allowed']);self.assertEqual(r['cache']['count'],1)
        self.assertEqual(r['budget_used'],1)
    async def test_reset_conflict(self):
        a=config('a');c=config('c');c['reset_day']=10
        r=await b.DiscoveryBudget(hass([a,c])).reserve(a,now=NOW)
        self.assertEqual(r['reason'],'reset_day_conflict')
    async def test_duplicate_query(self):
        s=config();m=b.DiscoveryBudget(hass([s,s]))
        for _ in range(4): await m.reserve(s,force=True,now=NOW)
        self.assertFalse((await m.reserve(s,force=True,now=NOW))['allowed'])
    async def test_zero_budget(self):
        s=config();s['monthly_budget']=0;s['reserve']=0
        self.assertFalse((await b.DiscoveryBudget(hass([s])).reserve(s,now=NOW))['allowed'])
    def test_month_end(self):
        start,end=b.cycle_bounds(datetime(2026,2,28,tzinfo=timezone.utc),31)
        self.assertEqual(start.day,28);self.assertEqual(end.day,31)
    def test_more_products_than_requests(self):
        groups=[str(i) for i in range(300)]
        self.assertEqual(sum(b.allocation(225,groups,g,NOW) for g in groups),225)
    async def test_failed_attempt_consumes(self):
        s=config();m=b.DiscoveryBudget(hass([s]))
        await m.reserve(s,now=NOW)
        self.assertEqual((await m.reserve(s,now=NOW))['product_used'],1)

if __name__=='__main__': unittest.main(verbosity=2)
