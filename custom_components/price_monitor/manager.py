"""GUI-managed products, durable sampled statistics, discovery budget and logs."""
import asyncio
import calendar
import copy
from collections import deque
from datetime import datetime,timezone,timedelta
import hashlib
import logging
import re
from difflib import SequenceMatcher
import uuid
from urllib.parse import urlsplit
from homeassistant.helpers.storage import Store
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import DOMAIN,SIGNAL
from .network import Network,valid_url
from .parser import parse,metadata,preview,extract,PriceError

_LOGGER=logging.getLogger(__name__)
def now():return datetime.now(timezone.utc)
def cycle(at,day):
    def date(y,m):return datetime(y,m,min(day,calendar.monthrange(y,m)[1]),tzinfo=timezone.utc)
    start=date(at.year,at.month)
    if at<start:start=date(at.year-1,12) if at.month==1 else date(at.year,at.month-1)
    end=date(start.year+1,1) if start.month==12 else date(start.year,start.month+1)
    return start,end

def record(s,price,at):
    s['price']=price;s['checked_at']=at;s['status']='ok';s['error']=None
    stats=s.setdefault('stats',{'count':0,'sum':0,'min':None,'max':None})
    stats['count']+=1;stats['sum']+=price
    stats['min']=price if stats['min'] is None else min(stats['min'],price)
    stats['max']=price if stats['max'] is None else max(stats['max'],price)
    history=s.setdefault('history',[]);history.append({'at':at,'price':price})
    del history[:-1000]

def summary(product):
    """Current market snapshot across successful tracked retailers, not history."""
    prices=[float(s['price']) for s in product.get('sellers',[])
            if s.get('status')=='ok' and isinstance(s.get('price'),(int,float))]
    return {'retailers':len(prices),
            'average':sum(prices)/len(prices) if prices else None,
            'minimum':min(prices) if prices else None,
            'maximum':max(prices) if prices else None}

ACCESSORY_WORDS={
    'case','cover','cable','adapter','charger','stand','mount','holder','strap','screen','protector',
    'replacement','earpad','earpads','sleeve','skin','dock','bag','pouch','battery','remote','filter',
    'hoes','hoesje','kabel','adapter','lader','houder','standaard','bandje','beschermer','vervanging',
    'oorkussen','oorkussens','tas','etui','accu','afstandsbediening'
}
STOP_WORDS={'the','and','with','for','van','met','een','de','het','voor','new','nieuw','wireless','draadloos'}

def _tokens(text):
    return re.findall(r'[a-z0-9]+',str(text).casefold())

def offer_similarity(product, title):
    """Conservative title match. Discovery is candidate filtering, not identity proof."""
    wanted=_tokens(product.get('name','')); found=_tokens(title)
    if not wanted or not found:return 0.0,'empty_title'
    wanted_set=set(wanted);found_set=set(found)
    # Accessory language in a result is a strong negative unless it is part of the product name itself.
    if (found_set & ACCESSORY_WORDS) - wanted_set:return 0.0,'accessory'
    # Model-like identifiers (letters+digits, or long numbers) must survive exactly.
    models={t for t in wanted_set if len(t)>=4 and ((any(c.isalpha() for c in t) and any(c.isdigit() for c in t)) or t.isdigit())}
    if models and not models.issubset(found_set):return 0.0,'model_mismatch'
    significant=[t for t in wanted if len(t)>=3 and t not in STOP_WORDS]
    coverage=sum(t in found_set for t in significant)/len(significant) if significant else (1.0 if wanted_set.issubset(found_set) else 0.0)
    sequence=SequenceMatcher(None,' '.join(wanted),' '.join(found)).ratio()
    score=0.7*coverage+0.3*sequence
    return score, 'ok' if coverage>=0.72 and score>=0.68 else 'low_similarity'

class Manager:
    def __init__(self,hass):
        self.hass=hass;self.store=Store(hass,1,'price_monitor.gui_v3')
        self.data=None;self.lock=asyncio.Lock();self.logs=deque(maxlen=500)
        self.snapshots={};self.net=Network();self.poll_lock=asyncio.Lock()
    def log(self,level,event,message,product_id=None,seller_id=None):
        item={'at':now().isoformat(),'level':level,'event':event,'message':message,
              'product_id':product_id,'seller_id':seller_id}
        self.logs.append(item)
        getattr(_LOGGER,level.lower())('%s: %s [product=%s seller=%s]',event,message,product_id,seller_id)
    async def start(self):
        self.data=await self.store.async_load() or {'products':[],'settings':{'api_key':'','monthly_budget':250,'reserve':25,'checks_per_month':4,'reset_day':1,'interval':60,'country':'nl','language':'en'},'budget':{},'imported':[]}
        self.logs.extend(self.data.get('logs',[]))
        old_budget=await Store(self.hass,1,'price_monitor.discovery_budget').async_load() or {}
        if not self.data.get('budget_imported'):
            for key,value in old_budget.items():
                if isinstance(value,dict) and value.get('cycle'):
                    self.data['budget'][key]={'cycle':value['cycle'],'used':value.get('used',0),'products':{}}
            self.data['budget_imported']=True
        await self.net.start();self.log('INFO','startup','GUI manager initialized')
    async def save(self):
        self.data['logs']=list(self.logs)[-200:]
        await self.store.async_save(self.data)
        async_dispatcher_send(self.hass,SIGNAL)
    def product(self,pid):
        p=next((p for p in self.data['products'] if p['id']==pid),None)
        if not p:raise PriceError('Product not found')
        return p
    def view_product_summary(self,pid):
        return summary(self.product(pid))
    def view(self):
        d=copy.deepcopy(self.data);d['settings'].pop('api_key',None)
        d['settings']['has_api_key']=bool(self.data['settings'].get('api_key'))
        key=hashlib.sha256(self.data['settings'].get('api_key','').encode()).hexdigest()
        current=self.data['budget'].get(key,{})
        d['settings']['budget_used']=current.get('used',0)
        d['settings']['budget_cycle']=current.get('cycle')
        d['logs']=list(self.logs)
        for p in d['products']:
            p['summary']=summary(p)
            for s in p['sellers']:
                s.pop('history',None)
        return d
    async def inspect(self,url,currency='EUR',ean=''):
        valid_url(url);self.log('INFO','inspect_start','Fetching public retailer page')
        try:
            html=await self.net.html(url)
            soup,products=await self.hass.async_add_executor_job(parse,html)
            host=urlsplit(url).hostname
            hints=[{'selector':s.get('selector',''),'attribute':s.get('attribute',''),'separator':s.get('separator','auto')}
                   for p in self.data['products'] for s in p['sellers']
                   if urlsplit(s['url']).hostname==host and s.get('selector')][:5]
            def build():
                meta=metadata(soup,products);tree,mapping=preview(soup)
                try:auto=extract(soup,products,{'currency':currency,'ean':ean})
                except PriceError as err:auto={'error':str(err)}
                auto_settings={}
                if 'price' not in auto:
                    for hint in hints:
                        try:auto=extract(soup,products,{'currency':currency,'ean':ean,**hint})
                        except PriceError:continue
                        auto['reused_selector']=True;auto_settings=hint;break
                return meta,tree,mapping,auto,auto_settings
            meta,tree,mapping,auto,auto_settings=await self.hass.async_add_executor_job(build)
            self.snapshots={k:v for k,v in self.snapshots.items() if (now()-v['at']).total_seconds()<600}
            if len(self.snapshots)>=10:self.snapshots.pop(next(iter(self.snapshots)))
            token=uuid.uuid4().hex
            self.snapshots[token]={'at':now(),'url':url,'soup':soup,'products':products,'mapping':mapping,'currency':currency,'ean':ean,'metadata':meta,'auto_settings':auto_settings}
            self.log('INFO','inspect_ready',f'Snapshot ready; automatic price {"valid" if "price" in auto else "unavailable"}')
            return {'token':token,**meta,**tree,'automatic':auto}
        except Exception as err:
            message=str(err) if isinstance(err,PriceError) else f'Page fetch/parse failed ({type(err).__name__})'
            self.log('ERROR','inspect_failed',message);raise PriceError(message) from None
    def snapshot(self,token):
        snap=self.snapshots.get(token)
        if not snap or (now()-snap['at']).total_seconds()>600:raise PriceError('Inspection expired; fetch the page again')
        return snap
    async def select(self,token,node='',separator='auto'):
        snap=self.snapshot(token)
        settings={'currency':snap['currency'],'ean':snap['ean'],'separator':separator}
        if not node:settings.update(snap.get('auto_settings',{}))
        if node:
            mapping=snap['mapping'].get(node)
            if not mapping:raise PriceError('Invalid inspected node')
            settings.update(mapping)
        result=await self.hass.async_add_executor_job(extract,snap['soup'],snap['products'],settings)
        self.log('INFO','selector_valid',f'Validated price {result["price"]} {result["currency"]}')
        return {**result,'selector':settings.get('selector',''),'attribute':settings.get('attribute',''),'separator':separator}
    async def add(self,payload):
        snap=self.snapshot(payload['token'])
        result=await self.select(payload['token'],payload.get('node',''),payload.get('separator','auto'))
        async with self.lock:
            pid=payload.get('product_id')
            if pid:
                p=self.product(pid)
                if p['currency']!=snap['currency']:raise PriceError('Seller currency must match product currency')
            else:
                name=payload.get('name','').strip() or snap['metadata']['name']
                if not name:raise PriceError('Enter a product name')
                p={'id':uuid.uuid4().hex,'name':name[:200],'ean':payload.get('ean','').strip() or snap['metadata']['ean'],'currency':snap['currency'],'sellers':[],'offers':[]}
                self.data['products'].append(p)
            replace_id=payload.get('replace_id','')
            existing=next((s for s in p['sellers'] if s['id']==replace_id),None) if replace_id else None
            if replace_id and not existing:raise PriceError('Seller to edit not found')
            if any(s['url']==snap['url'] and s['id']!=replace_id for s in p['sellers']):raise PriceError('This seller URL is already tracked')
            if existing and existing['url']!=snap['url']:raise PriceError('Editing a selector cannot change the seller URL; add a new website')
            seller={'id':uuid.uuid4().hex,'url':snap['url'],'store':urlsplit(snap['url']).hostname,
                    'selector':result['selector'],'attribute':result['attribute'],'separator':result['separator'],'currency':p['currency'],'ean':p['ean'],'status':'ok'}
            if existing:
                existing.update(selector=result['selector'],attribute=result['attribute'],separator=result['separator'])
                seller=existing
            else:p['sellers'].append(seller)
            record(seller,result['price'],now().isoformat())
            self.log('INFO','seller_added','Seller validated and added',p['id'],seller['id']);await self.save()
        return p['id']
    async def remove(self,pid,sid=None):
        async with self.lock:
            p=self.product(pid)
            if sid:p['sellers']=[s for s in p['sellers'] if s['id']!=sid]
            else:self.data['products']=[p for p in self.data['products'] if p['id']!=pid]
            self.log('INFO','removed','Seller removed' if sid else 'Product removed',pid,sid);await self.save()
    async def settings(self,values):
        async with self.lock:
            s=self.data['settings'];updated={**s,**values}
            for key,low,high in [('monthly_budget',0,100000),('reserve',0,100000),('checks_per_month',0,10000),('reset_day',1,31),('interval',15,10080)]:
                if not isinstance(updated[key],int) or not low<=updated[key]<=high:raise PriceError(f'Invalid {key}')
            if updated['reserve']>updated['monthly_budget']:raise PriceError('Reserve exceeds budget')
            for key in ('api_key','country','language'):
                if not isinstance(updated[key],str):raise PriceError(f'Invalid {key}')
            if len(updated['country'])!=2 or not updated['country'].isalpha():raise PriceError('Use a two-letter country code')
            self.data['settings']=updated
            self.log('INFO','settings_saved','GUI settings updated (secrets omitted)');await self.save()
    async def discover(self,pid,force=False):
        async with self.lock:
            p=self.product(pid);s=copy.deepcopy(self.data['settings'])
            if not s.get('api_key'):
                if force:self.log('WARNING','discovery_skipped','No SerpApi key; add stores manually',pid)
                return {'status':'no_api_key'}
            start,end=cycle(now(),s['reset_day']);key=hashlib.sha256(s['api_key'].encode()).hexdigest()
            b=self.data['budget'].setdefault(key,{})
            if b.get('cycle')!=start.isoformat():b.update(cycle=start.isoformat(),used=0,products={})
            ids=sorted(p['id'] for p in self.data['products']);total=max(0,s['monthly_budget']-s['reserve'])
            base,extra=divmod(total,len(ids));offset=(start.year*12+start.month)%len(ids)
            share=min(s['checks_per_month'],base+int((ids.index(pid)-offset)%len(ids)<extra))
            g=b.setdefault('products',{}).setdefault(pid,{'used':0})
            if not share or b['used']>=total or g['used']>=share:
                self.log('WARNING','budget_exhausted','Discovery budget exhausted; cached sellers retained',pid);return {'status':'budget_exhausted'}
            if not force and g.get('last') and (now()-datetime.fromisoformat(g['last'])).total_seconds()<(end-start).total_seconds()/share:
                return {'status':'cached_not_due'}
            b['used']+=1;g['used']+=1;g['last']=now().isoformat();await self.save()
            query=f'\"{p["ean"]}\" {p["name"]}' if p.get('ean') else p['name']
        self.log('INFO','discovery_start','One quota-reserved Shopping request',pid)
        try:
            data=await self.net.shopping({'engine':'google_shopping','q':query,'api_key':s['api_key'],'gl':s['country'],'hl':s['language']})
            results=data.get('shopping_results',[])
            if not isinstance(results,list):raise PriceError('Invalid shopping results')
            offers=[]
            for item in results[:40]:
                if not isinstance(item,dict):continue
                link=item.get('product_link') or item.get('link')
                if not isinstance(link,str) or urlsplit(link).scheme not in ('http','https'):link=''
                title=str(item.get('title',''))[:300]
                score,reason=offer_similarity(p,title)
                if score<=0:continue
                if reason!='ok':continue
                offers.append({'title':title,'seller':str(item.get('source',''))[:200],
                    'price_text':str(item.get('price',''))[:100],'url':link,'ean_verified':False,
                    'similarity':round(score,3)})
            offers.sort(key=lambda offer:offer.get('similarity',0),reverse=True)
            async with self.lock:
                p=self.product(pid);p['offers']=offers;p['discovered_at']=now().isoformat()
                self.log('INFO','discovery_done',f'{len(offers)} candidate sellers cached; exact variants unverified',pid);await self.save()
            return {'status':'ok','count':len(offers)}
        except Exception as err:
            message=str(err) if isinstance(err,PriceError) else f'Discovery failed ({type(err).__name__})'
            self.log('ERROR','discovery_failed',message,pid)
            async with self.lock:await self.save()
            return {'status':'failed','error':message}
    async def poll(self,force=False):
        if self.poll_lock.locked():return
        async with self.poll_lock:
            for product in list(self.data['products']):
                for seller in list(product['sellers']):
                    if not force and seller.get('checked_at') and (now()-datetime.fromisoformat(seller['checked_at'])).total_seconds()<self.data['settings']['interval']*60:continue
                    pid,sid=product['id'],seller['id']
                    try:
                        html=await self.net.html(seller['url'])
                        def read():
                            soup,products=parse(html);return extract(soup,products,seller)
                        result=await self.hass.async_add_executor_job(read)
                        async with self.lock:
                            p=self.product(pid);current=next((s for s in p['sellers'] if s['id']==sid),None)
                            if current is None:continue
                            previous=current.get('price');record(current,result['price'],now().isoformat())
                            self.log('INFO','price_checked',f'{result["price"]} {p["currency"]}',pid,sid);await self.save()
                            if previous is not None and result['price']<previous:
                                self.hass.bus.async_fire('price_monitor_price_drop',{'product_id':pid,'seller_id':sid,'name':p['name'],'price':result['price'],'previous_price':previous,'currency':p['currency'],'url':current['url']})
                    except Exception as err:
                        message=str(err) if isinstance(err,PriceError) else f'Price check failed ({type(err).__name__})'
                        self.log('ERROR','price_failed',message,pid,sid)
                        async with self.lock:
                            try:p=self.product(pid)
                            except PriceError:continue
                            current=next((s for s in p['sellers'] if s['id']==sid),None)
                            if current:current.update(status='error',error=message,checked_at=now().isoformat())
                            await self.save()
                if product['id'] in [p['id'] for p in self.data['products']]:await self.discover(product['id'])
    async def import_entry(self,entry):
        if entry.entry_id in self.data['imported']:return
        s={**entry.data,**entry.options}
        if s.get('mode')=='monitor':
            p={'id':uuid.uuid4().hex,'name':entry.title,'ean':s.get('ean',''),'currency':s.get('currency','EUR'),'offers':[],'sellers':[]}
            seller={'id':uuid.uuid4().hex,'url':s['url'],'store':urlsplit(s['url']).hostname,'selector':s.get('selector',''),
                    'attribute':s.get('attribute',''),'separator':s.get('decimal_separator','auto'),'currency':p['currency'],'ean':p['ean'],'status':'pending'}
            old=await Store(self.hass,1,f'price_monitor.{entry.entry_id}').async_load() or {}
            if isinstance(old.get('price'),(int,float)):
                seller['price']=old['price'];seller['legacy_minimum']=old.get('lowest')
            p['sellers'].append(seller);self.data['products'].append(p)
        elif s.get('mode')=='search' and s.get('api_key') and not self.data['settings']['api_key']:
            self.data['settings']['api_key']=s['api_key']
            for key in ('monthly_budget','reserve','checks_per_month','reset_day','country','language'):
                if key in s:self.data['settings'][key]=s[key]
        self.data['imported'].append(entry.entry_id)
        self.log('INFO','legacy_import','Legacy entry imported; historical averages not fabricated');await self.save()
