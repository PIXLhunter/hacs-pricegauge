"""Synthetic fixtures and mocked HA storage, never live retailer tests."""
import asyncio,copy,importlib.util,json,sys,types,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import AsyncMock,Mock
BASE=Path(__file__).parents[1]/'custom_components/price_monitor'
DB={}
class Store:
    def __init__(self,hass,version,key):self.key=key
    async def async_load(self):return copy.deepcopy(DB.get(self.key))
    async def async_save(self,data):DB[self.key]=copy.deepcopy(data)
def mod(name,**attrs):
    m=types.ModuleType(name)
    for k,v in attrs.items():setattr(m,k,v)
    sys.modules[name]=m;return m
mod('homeassistant');mod('homeassistant.helpers');mod('homeassistant.helpers.storage',Store=Store)
mod('homeassistant.helpers.dispatcher',async_dispatcher_send=lambda *args:None)
pkg=mod('pgtest');pkg.__path__=[str(BASE)]
def load(name):
    spec=importlib.util.spec_from_file_location('pgtest.'+name,BASE/(name+'.py'))
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);return m
c=load('const');parser=load('parser');network=load('network');manager=load('manager')
HTML='<html><head><title>Test product</title></head><body><div><span class="price">129,99</span></div></body></html>'
class ParserTests(unittest.TestCase):
    def test_locale(self):
        for v in ('1.299,99','1,299.99','1 299,99'):self.assertEqual(parser.money(v),1299.99)
    def test_ambiguous(self):
        for v in ('1.299','1,299','-2','12.00 24.00','NaN'):
            with self.assertRaises(parser.PriceError):parser.money(v)
    def test_css_count(self):
        soup,p=parser.parse('<b>1</b><b>2</b>')
        with self.assertRaisesRegex(parser.PriceError,'2 elements'):parser.extract(soup,p,{'selector':'b'})
    def test_missing(self):
        soup,p=parser.parse(HTML)
        with self.assertRaisesRegex(parser.PriceError,'0 elements'):parser.extract(soup,p,{'selector':'.missing'})
    def test_path(self):
        soup,p=parser.parse(HTML);el=soup.select_one('.price');path=parser.path_for(el)
        self.assertIs(soup.select_one(path),el)
    def test_preview_no_script(self):
        soup,p=parser.parse('<script>alert(1)</script><b onclick="evil()">12</b><iframe src="evil"></iframe>')
        tree,mapping=parser.preview(soup);serialized=json.dumps(tree)
        self.assertNotIn('alert',serialized);self.assertNotIn('onclick',serialized);self.assertNotIn('iframe',serialized)
    def test_preview_mapping(self):
        soup,p=parser.parse(HTML);tree,mapping=parser.preview(soup)
        for item in mapping.values():self.assertEqual(len(soup.select(item['selector'])),1)
    def test_structured(self):
        html='<script type="application/ld+json">'+json.dumps({'@type':'Product','name':'P','gtin13':'4006381333931','offers':{'price':'12.99','priceCurrency':'EUR'}})+'</script>'
        soup,p=parser.parse(html);self.assertEqual(parser.extract(soup,p,{})['price'],12.99)
        self.assertEqual(parser.metadata(soup,p)['ean'],'4006381333931')
    def test_currency_no_fallback(self):
        html='<script type="application/ld+json">'+json.dumps({'@type':'Product','offers':{'price':'12','priceCurrency':'USD'}})+'</script><meta itemprop="price" content="12">'
        soup,p=parser.parse(html)
        with self.assertRaises(parser.PriceError):parser.extract(soup,p,{'currency':'EUR'})
    def test_private_urls(self):
        for url in ('http://127.0.0.1','http://10.0.0.1','http://localhost','http://[::1]','file:///etc/passwd','https://user:pass@example.com','https://example.com:123'):
            with self.assertRaises(parser.PriceError):network.valid_url(url)
    def test_public_url(self):self.assertEqual(network.valid_url('https://example.com/p'),'https://example.com/p')
    def test_sample_average(self):
        s={}
        for price in (10,20,15):manager.record(s,price,'now')
        summary=manager.summary({'sellers':[s]})
        self.assertEqual(summary,{'retailers':1,'average':15.0,'minimum':15.0,'maximum':15.0})
    def test_cycle(self):
        start,end=manager.cycle(datetime(2026,2,28,tzinfo=timezone.utc),31)
        self.assertEqual(start.day,28);self.assertEqual(end.day,31)
class ManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        DB.clear()
        async def executor(fn,*args):return fn(*args)
        self.hass=types.SimpleNamespace(async_add_executor_job=executor,bus=types.SimpleNamespace(async_fire=Mock()))
        self.m=manager.Manager(self.hass)
        self.m.net.start=AsyncMock();self.m.net.html=AsyncMock(return_value=HTML)
        self.m.net.shopping=AsyncMock(return_value={'shopping_results':[{'source':'Shop','title':'P','price':'EUR 12','product_link':'https://example.com/p'}]})
        await self.m.start()
    async def add(self):
        snap=await self.m.inspect('https://example.com/product')
        node=next(k for k,v in self.m.snapshots[snap['token']]['mapping'].items() if v['selector'].endswith('span:nth-of-type(1)'))
        pid=await self.m.add({'token':snap['token'],'node':node,'name':'P'})
        return pid,snap,node
    async def test_empty_state(self):self.assertEqual(self.m.view()['products'],[])
    async def test_inspect_one_fetch(self):
        pid,snap,node=await self.add();await self.m.select(snap['token'],node)
        self.m.net.html.assert_awaited_once();self.assertEqual(len(self.m.data['products']),1)
    async def test_add_remove(self):
        pid,_,_=await self.add();await self.m.remove(pid)
        self.assertEqual(self.m.data['products'],[])
    async def test_remove_seller(self):
        pid,_,_=await self.add();sid=self.m.product(pid)['sellers'][0]['id'];await self.m.remove(pid,sid)
        self.assertEqual(self.m.product(pid)['sellers'],[])
    async def test_duplicate(self):
        pid,snap,node=await self.add()
        with self.assertRaises(parser.PriceError):await self.m.add({'token':snap['token'],'node':node,'product_id':pid})
    async def test_edit_preserves_stats(self):
        pid,snap,node=await self.add();sid=self.m.product(pid)['sellers'][0]['id']
        await self.m.add({'token':snap['token'],'node':node,'product_id':pid,'replace_id':sid})
        self.assertEqual(len(self.m.product(pid)['sellers']),1)
        self.assertEqual(self.m.product(pid)['sellers'][0]['stats']['count'],2)
    async def test_no_key(self):
        pid,_,_=await self.add();r=await self.m.discover(pid,True)
        self.assertEqual(r['status'],'no_api_key');self.m.net.shopping.assert_not_awaited()
    async def test_key_redacted(self):
        await self.m.settings({'api_key':'key_ABC123_NEVER_RETURN'})
        self.assertNotIn('key_ABC123_NEVER_RETURN',json.dumps(self.m.view()))
    async def test_quota(self):
        pid,_,_=await self.add();await self.m.settings({'api_key':'secret','monthly_budget':2,'reserve':0,'checks_per_month':4})
        results=await asyncio.gather(*(self.m.discover(pid,True) for _ in range(8)))
        self.assertEqual(sum(r['status']=='ok' for r in results),2);self.assertEqual(self.m.net.shopping.await_count,2)
    async def test_cache_on_failure(self):
        pid,_,_=await self.add();await self.m.settings({'api_key':'secret'})
        await self.m.discover(pid,True);self.m.net.shopping.side_effect=parser.PriceError('quota')
        r=await self.m.discover(pid,True);self.assertEqual(r['status'],'failed');self.assertEqual(len(self.m.product(pid)['offers']),1)
    async def test_failed_price_no_zero(self):
        pid,_,_=await self.add();self.m.net.html.side_effect=parser.PriceError('blocked')
        await self.m.poll(True);s=self.m.product(pid)['sellers'][0]
        self.assertEqual(s['stats']['count'],1);self.assertEqual(s['price'],129.99);self.assertEqual(s['status'],'error')
    async def test_save_before_event(self):
        pid,_,_=await self.add();self.m.net.html.return_value=HTML.replace('129,99','99,99')
        def event(*args):self.assertEqual(DB['price_monitor.gui_v3']['products'][0]['sellers'][0]['price'],99.99)
        self.hass.bus.async_fire.side_effect=event;await self.m.poll(True)
        self.hass.bus.async_fire.assert_called_once()
    async def test_restart_persistence(self):
        pid,_,_=await self.add();m=manager.Manager(self.hass);m.net.start=AsyncMock();await m.start()
        self.assertEqual(m.product(pid)['sellers'][0]['stats']['count'],1)
    async def test_legacy_budget_import(self):
        DB['price_monitor.discovery_budget']={'hash':{'cycle':'2026-10-01T00:00:00+00:00','used':200}}
        m=manager.Manager(self.hass);m.net.start=AsyncMock();await m.start()
        self.assertEqual(m.data['budget']['hash']['used'],200)
    async def test_expired_snapshot(self):
        with self.assertRaises(parser.PriceError):await self.m.select('unknown')
    async def test_invalid_settings(self):
        with self.assertRaises(parser.PriceError):await self.m.settings({'reserve':999})
    async def test_log_visibility(self):
        self.m.log('ERROR','test','visible');self.assertEqual(self.m.view()['logs'][-1]['message'],'visible')
