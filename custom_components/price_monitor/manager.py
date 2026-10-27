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

def normalized_price(product,seller):
    if seller.get('status')!='ok' or not isinstance(seller.get('price'),(int,float)):return None
    count=float(seller.get('pack_count') or 1)
    if count<=0:return None
    raw=float(seller['price'])
    mode=product.get('comparison_unit','each')
    if mode=='100ml':
        ml=float(seller.get('unit_ml') or 0)
        if ml<=0:return None
        return raw/(count*ml)*100
    return raw/count

def summary(product):
    prices=[value for seller in product.get('sellers',[]) if (value:=normalized_price(product,seller)) is not None]
    return {'retailers':len(prices),'average':sum(prices)/len(prices) if prices else None,
            'minimum':min(prices) if prices else None,'maximum':max(prices) if prices else None,
            'unit':'/100 ml' if product.get('comparison_unit')=='100ml' else '/item'}
BAD_WORDS={'case','cover','cable','adapter','charger','stand','mount','holder','strap','protector','replacement','earpad','earpads','sleeve','dock','bag','pouch','battery','remote','filter','refurbished','renewed','used','bundle','bundel','pack','set','kit','industrial','hoes','hoesje','kabel','lader','houder','standaard','bandje','beschermer','vervanging','oorkussen','oorkussens','tas','etui','accu','afstandsbediening'}
STOP={'the','and','with','for','van','met','een','de','het','voor','new','nieuw','wireless','draadloos'}
def toks(text):return re.findall(r'[a-z0-9]+',str(text).casefold())
def identifiers(text):
    ids=set()
    for v in re.findall(r'(?i)\b(?=[a-z0-9-]{4,}\b)(?=[a-z0-9-]*[a-z])(?=[a-z0-9-]*\d)[a-z0-9]+(?:-[a-z0-9]+)*\b',str(text)):ids.add(' '.join(toks(v)))
    for v in re.findall(r'(?i)\b[a-z]{2,}(?:-[a-z0-9]{2,})+\b',str(text)):ids.add(' '.join(toks(v)))
    return ids
def offer_similarity(product,title):
    wanted=toks(product.get('name',''));found=toks(title);ws=set(wanted);fs=set(found)
    if not wanted or not found:return 0.0,'empty'
    if ' '.join(wanted)==' '.join(found):return 1.0,'ok'
    if (fs & BAD_WORDS)-ws:return 0.0,'variant_or_accessory'
    ids=identifiers(product.get('name',''));normalized=' '.join(found)
    if ids and not all(i in normalized for i in ids):return 0.0,'identifier_mismatch'
    significant=[t for t in wanted if len(t)>=3 and t not in STOP]
    if not significant:return 0.0,'insufficient_identity'
    coverage=sum(t in fs for t in significant)/len(significant)
    key=[t for t in significant if t not in {'ubiquiti','unifi','cloud','gateway','network','networks'}]
    if key and not all(t in fs for t in key):return 0.0,'key_term_mismatch'
    score=.75*coverage+.25*SequenceMatcher(None,' '.join(wanted),' '.join(found)).ratio()
    return (score,'ok') if coverage>=.80 and score>=.78 else (0.0,'low_similarity')

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
        settings=self.data.setdefault('settings',{})
        settings.setdefault('notify_entity','');settings.setdefault('notify_price_drop',False);settings.setdefault('notify_drop_percent',5.0)
        settings.setdefault('report_major_percent',10.0);settings.setdefault('report_interval_days',3)
        self.data.setdefault('reports',[])
        for product in self.data.setdefault('products',[]):
            product.setdefault('notify_enabled',True);product.setdefault('target_price',None);product.setdefault('target_notified',False)
            product.setdefault('comparison_unit','each')
            for seller in product.get('sellers',[]):seller.setdefault('pack_count',1);seller.setdefault('unit_ml',None)
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
        d['settings']['notify_entities']=self.notification_entities()
        d['logs']=list(self.logs)
        for p in d['products']:
            p['summary']=summary(p)
            for seller in p['sellers']:
                seller['history']=seller.get('history',[])[-200:]
                seller['normalized_price']=normalized_price(p,seller)
        return d
    def notification_entities(self):
        items={}
        for state in self.hass.states.async_all('notify'):
            items[state.entity_id]={'entity_id':state.entity_id,'name':f"{state.attributes.get('friendly_name') or state.entity_id} (entity)"}
        # Companion apps can still expose legacy notify.mobile_app_* actions instead of notify entities.
        services=self.hass.services.async_services().get('notify',{})
        for service in services:
            full=f'notify.{service}'
            if service not in ('send_message','notify','persistent_notification') and full not in items:
                items[full]={'entity_id':full,'name':f'{full} (action)'}
        return sorted(items.values(),key=lambda item:item['name'].casefold())

    def _notification_target_available(self,target):
        if not target.startswith('notify.'):return False
        if self.hass.states.get(target) is not None:return True
        return target.split('.',1)[1] in self.hass.services.async_services().get('notify',{})

    async def notify(self,title,message,product_id=None):
        target=self.data['settings'].get('notify_entity','')
        if not target:return False
        if not self._notification_target_available(target):
            self.log('WARNING','notification_skipped','Configured notification destination is unavailable',product_id);return False
        try:
            if self.hass.states.get(target) is not None:
                await self.hass.services.async_call('notify','send_message',{'title':title,'message':message},target={'entity_id':target},blocking=True)
            else:
                await self.hass.services.async_call('notify',target.split('.',1)[1],{'title':title,'message':message},blocking=True)
            self.log('INFO','notification_sent',title,product_id);return True
        except Exception as err:
            self.log('ERROR','notification_failed',f'Notification failed ({type(err).__name__})',product_id);return False

    async def test_notification(self):
        if not self.data['settings'].get('notify_entity'):raise PriceError('Select a notification destination first')
        return {'sent':await self.notify('PriceGauge','Test notification from PriceGauge')}

    async def product_settings(self,pid,values):
        async with self.lock:
            product=self.product(pid)
            if 'notify_enabled' in values:product['notify_enabled']=bool(values['notify_enabled'])
            if 'comparison_unit' in values:
                if values['comparison_unit'] not in ('each','100ml'):raise PriceError('Invalid comparison unit')
                product['comparison_unit']=values['comparison_unit']
            if 'target_price' in values:
                target=values['target_price']
                if target in ('',None):product['target_price']=None;product['target_notified']=False
                else:
                    target=float(target)
                    if target<0 or target>10000000:raise PriceError('Invalid target price')
                    if product.get('target_price')!=target:product['target_notified']=False
                    product['target_price']=target
            await self.save()
        return {'saved':True}

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
                p={'id':uuid.uuid4().hex,'name':name[:200],'ean':payload.get('ean','').strip() or snap['metadata']['ean'],'currency':snap['currency'],'comparison_unit':payload.get('comparison_unit','each') if payload.get('comparison_unit','each') in ('each','100ml') else 'each','sellers':[],'offers':[]}
                self.data['products'].append(p)
            replace_id=payload.get('replace_id','')
            existing=next((s for s in p['sellers'] if s['id']==replace_id),None) if replace_id else None
            if replace_id and not existing:raise PriceError('Seller to edit not found')
            if any(s['url']==snap['url'] and s['id']!=replace_id for s in p['sellers']):raise PriceError('This seller URL is already tracked')
            if existing and existing['url']!=snap['url']:raise PriceError('Editing a selector cannot change the seller URL; add a new website')
            seller={'id':uuid.uuid4().hex,'url':snap['url'],'store':urlsplit(snap['url']).hostname,
                    'selector':result['selector'],'attribute':result['attribute'],'separator':result['separator'],'currency':p['currency'],'ean':p['ean'],'status':'ok',
                    'pack_count':max(1,int(payload.get('pack_count') or 1)),'unit_ml':float(payload['unit_ml']) if payload.get('unit_ml') not in ('',None) else None}
            if existing:
                existing.update(selector=result['selector'],attribute=result['attribute'],separator=result['separator'],
                    pack_count=max(1,int(payload.get('pack_count') or existing.get('pack_count') or 1)),
                    unit_ml=float(payload['unit_ml']) if payload.get('unit_ml') not in ('',None) else None)
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
            for key in ('api_key','country','language','notify_entity'):
                if not isinstance(updated[key],str):raise PriceError(f'Invalid {key}')
            if len(updated['country'])!=2 or not updated['country'].isalpha():raise PriceError('Use a two-letter country code')
            updated['notify_price_drop']=bool(updated.get('notify_price_drop',False))
            updated['notify_drop_percent']=float(updated.get('notify_drop_percent',5.0))
            if not 0<=updated['notify_drop_percent']<=100:raise PriceError('Invalid drop percentage')
            updated['report_major_percent']=float(updated.get('report_major_percent',10.0))
            updated['report_interval_days']=int(updated.get('report_interval_days',3))
            if not 0<updated['report_major_percent']<=100:raise PriceError('Invalid report change percentage')
            if not 1<=updated['report_interval_days']<=30:raise PriceError('Invalid report interval')
            if updated['notify_entity'] and not self._notification_target_available(updated['notify_entity']):raise PriceError('Selected notification destination is unavailable')
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
                title=str(item.get('title',''))[:300];score,reason=offer_similarity(p,title)
                if reason!='ok':continue
                direct=link if link and urlsplit(link).hostname and 'google.' not in urlsplit(link).hostname.lower() else ''
                candidate_id=str(item.get('product_id') or item.get('immersive_product_page_token') or uuid.uuid4().hex)
                offers.append({'id':candidate_id,'title':title,'seller':str(item.get('source',''))[:200],
                    'price_text':str(item.get('price',''))[:100],'url':direct,'ean_verified':False,'similarity':round(score,3),
                    'needs_retailer_url':not bool(direct),'product_id':str(item.get('product_id') or ''),
                    'page_token':str(item.get('immersive_product_page_token') or ''),'stores':[]})
            offers.sort(key=lambda o:o.get('similarity',0),reverse=True)
            async with self.lock:
                p=self.product(pid);p['offers']=offers;p['discovered_at']=now().isoformat()
                self.log('INFO','discovery_done',f'{len(offers)} candidate sellers cached; exact variants unverified',pid);await self.save()
            return {'status':'ok','count':len(offers)}
        except Exception as err:
            message=str(err) if isinstance(err,PriceError) else f'Discovery failed ({type(err).__name__})'
            self.log('ERROR','discovery_failed',message,pid)
            async with self.lock:await self.save()
            return {'status':'failed','error':message}
    async def resolve_offer(self,pid,candidate_id):
        """Resolve one strict Shopping candidate to direct retailer offers."""
        async with self.lock:
            product=self.product(pid);settings=copy.deepcopy(self.data['settings'])
            offer=next((o for o in product.get('offers',[]) if o.get('id')==candidate_id),None)
            if not offer:raise PriceError('Discovery candidate not found; run discovery again')
            # Reuse any successful Product API response for one hour, including zero-store responses.
            resolved_at=offer.get('resolved_at')
            if resolved_at:
                try:fresh=(now()-datetime.fromisoformat(resolved_at))<timedelta(hours=1)
                except (ValueError,TypeError):fresh=False
                if fresh:
                    self.log('INFO','offer_resolution_cache',f"Using cached Product API result with {len(offer.get('stores',[]))} direct stores",pid)
                    return {'status':'cached','count':len(offer.get('stores',[])),'diagnostics':offer.get('resolve_diagnostics',{})}
            if not settings.get('api_key'):raise PriceError('No SerpApi key configured')
            identifier=('page_token',offer.get('page_token')) if offer.get('page_token') else ('product_id',offer.get('product_id'))
            if not identifier[1]:raise PriceError('Candidate has no Product API identifier')
            start,end=cycle(now(),settings['reset_day']);account=hashlib.sha256(settings['api_key'].encode()).hexdigest();budget=self.data['budget'].setdefault(account,{})
            if budget.get('cycle')!=start.isoformat():budget.update(cycle=start.isoformat(),used=0,products={})
            total=max(0,settings['monthly_budget']-settings['reserve']);group=budget.setdefault('products',{}).setdefault(pid,{'used':0})
            if budget['used']>=total:raise PriceError('SerpApi account budget exhausted')
            budget['used']+=1;group['used']=group.get('used',0)+1
            await self.save()  # Reserve before I/O. Failed/uncertain requests remain counted locally.
        self.log('INFO','offer_resolution_request',f'Calling google_product using {identifier[0]}; local account usage now {budget["used"]}/{total}',pid)
        params={'engine':'google_product',identifier[0]:identifier[1],'offer_view':'true','api_key':settings['api_key'],'gl':settings['country'],'hl':settings['language']}
        try:data=await self.net.serpapi(params)
        except Exception as err:
            message=str(err) if isinstance(err,PriceError) else f'Offer resolution failed ({type(err).__name__})';self.log('ERROR','offer_resolution_failed',message,pid);raise PriceError(message) from None
        metadata=data.get('search_metadata',{}) if isinstance(data.get('search_metadata',{}),dict) else {}
        results=data.get('product_results',{})
        if not isinstance(results,dict):raise PriceError('Invalid Google Product response')
        resolved_title=str(results.get('title') or offer.get('title') or '')
        product_score,product_reason=offer_similarity(product,resolved_title)
        raw_stores=results.get('stores',[]) if isinstance(results.get('stores',[]),list) else []
        search_id=str(metadata.get('id',''))[:80];search_status=str(metadata.get('status',''))[:40]
        # The strict identity gate already ran on the Shopping candidate which supplied this product_id/page_token.
        # SerpApi documents those values as identifiers of the Google product / exact offer. Resolved Product API
        # titles can normalize or omit model punctuation, so a second hard title gate produced false mismatches.
        self.log('INFO','offer_resolution_response',f'Product API response id={search_id or "unknown"} status={search_status or "unknown"}; resolved_title_check={product_reason}; raw_stores={len(raw_stores)}',pid)
        if product_reason!='ok':self.log('WARNING','offer_resolution_title_variation',f'Resolved title differs from tracked naming ({product_reason}); trusting identifier from already-validated Shopping candidate',pid)
        stores=[];reject={'invalid_link':0,'google_link':0,'condition':0}
        for store in raw_stores:
            if not isinstance(store,dict):continue
            link=store.get('link');title=str(store.get('title') or resolved_title)[:300]
            if not isinstance(link,str) or urlsplit(link).scheme not in ('http','https'):
                reject['invalid_link']+=1;continue
            host=(urlsplit(link).hostname or '').lower()
            if host=='google.com' or host.endswith('.google.com') or host=='serpapi.com' or host.endswith('.serpapi.com'):
                reject['google_link']+=1;continue
            condition=str(store.get('condition','')).casefold().strip()
            if any(word in condition for word in ('refurbished','used','pre-owned','preowned','second-hand','renewed')):
                reject['condition']+=1;continue
            # Product API stores belong to the already-validated product. Store titles are often abbreviated,
            # so repeating the strict Shopping-title matcher here incorrectly removes valid offers.
            stores.append({'name':str(store.get('name',''))[:200] or host,'title':title,'url':link,
                'price_text':str(store.get('price',''))[:100],'price':store.get('extracted_price'),
                'condition':str(store.get('condition',''))[:80]})
        unique={}
        for store in stores:unique.setdefault(store['url'],store)
        stores=list(unique.values())[:40]
        async with self.lock:
            current=next((o for o in self.product(pid).get('offers',[]) if o.get('id')==candidate_id),None)
            if current is not None:
                current['stores']=stores;current['resolved_at']=now().isoformat();current['resolve_diagnostics']={'search_id':search_id,'status':search_status,'raw_stores':len(raw_stores),'accepted':len(stores),'rejected':reject}
            self.log('INFO','offer_resolution_done',f'{len(stores)}/{len(raw_stores)} direct stores accepted; rejected invalid={reject["invalid_link"]}, google={reject["google_link"]}, condition={reject["condition"]}',pid);await self.save()
        return {'status':'ok','count':len(stores),'raw_count':len(raw_stores),'search_id':search_id,'search_status':search_status}

    def _report_snapshot(self,reason):
        products=[];previous={p['id']:p for p in (self.data.get('reports',[])[-1].get('products',[]) if self.data.get('reports') else [])}
        for product in self.data['products']:
            sm=summary(product);old_min=previous.get(product['id'],{}).get('minimum')
            delta=((sm['minimum']-old_min)/old_min*100) if sm['minimum'] is not None and old_min not in (None,0) else None
            products.append({'id':product['id'],'name':product['name'],'currency':product['currency'],'unit':sm['unit'],
                'average':sm['average'],'minimum':sm['minimum'],'maximum':sm['maximum'],'minimum_change_percent':delta,'retailers':sm['retailers'],
                'stores':[{'name':seller['store'],'price':seller.get('price'),'normalized_price':normalized_price(product,seller),
                    'pack_count':seller.get('pack_count',1),'unit_ml':seller.get('unit_ml')} for seller in product.get('sellers',[])]})
        return {'id':uuid.uuid4().hex,'generated_at':now().isoformat(),'reason':reason,'products':products}

    async def update_report_if_due(self):
        reports=self.data.setdefault('reports',[]);latest=reports[-1] if reports else None
        reason=None
        if latest:
            previous={p['id']:p for p in latest.get('products',[])}
            threshold=float(self.data['settings'].get('report_major_percent',10.0))
            for product in self.data['products']:
                current=summary(product).get('minimum');old=previous.get(product['id'],{}).get('minimum')
                if current is not None and old not in (None,0) and abs(current-old)/old*100>=threshold:
                    reason=f'major minimum change ({product["name"]})';break
            if reason is None:
                age=now()-datetime.fromisoformat(latest['generated_at'])
                if age>=timedelta(days=int(self.data['settings'].get('report_interval_days',3))):reason='scheduled'
        elif self.data['products']:reason='initial'
        if reason:
            reports.append(self._report_snapshot(reason));del reports[:-50]
            self.log('INFO','report_updated',f'Product report updated: {reason}');await self.save()
            return True
        return False

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
                            target=p.get('target_price');comparison_price=normalized_price(p,current)
                            target_crossed=bool(target is not None and comparison_price is not None and comparison_price<=target and not p.get('target_notified',False))
                            if target is not None and comparison_price is not None and comparison_price>target:p['target_notified']=False
                            if target_crossed:p['target_notified']=True
                            self.log('INFO','price_checked',f'{result["price"]} {p["currency"]}',pid,sid);await self.save()
                            if previous is not None and result['price']<previous:
                                self.hass.bus.async_fire('price_monitor_price_drop',{'product_id':pid,'seller_id':sid,'name':p['name'],'price':result['price'],'previous_price':previous,'currency':p['currency'],'url':current['url']})
                            should_drop=bool(previous and previous>0 and result['price']<previous and (previous-result['price'])/previous*100>=self.data['settings'].get('notify_drop_percent',5.0))
                            if p.get('notify_enabled',True) and self.data['settings'].get('notify_price_drop') and should_drop:
                                await self.notify('Price drop',f'{p["name"]}: {previous:.2f} → {result["price"]:.2f} {p["currency"]} at {current["store"]}',pid)
                            if p.get('notify_enabled',True) and target_crossed:
                                await self.notify('Target price reached',f'{p["name"]}: {comparison_price:.2f} {p["currency"]}{summary(p)["unit"]} at {current["store"]} (target {target:.2f})',pid)
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
            await self.update_report_if_due()
    async def import_entry(self,entry):
        if entry.entry_id in self.data['imported']:return
        s={**entry.data,**entry.options}
        if s.get('mode')=='monitor':
            p={'id':uuid.uuid4().hex,'name':entry.title,'ean':s.get('ean',''),'currency':s.get('currency','EUR'),'comparison_unit':'each','offers':[],'sellers':[]}
            seller={'id':uuid.uuid4().hex,'url':s['url'],'store':urlsplit(s['url']).hostname,'selector':s.get('selector',''),
                    'attribute':s.get('attribute',''),'separator':s.get('decimal_separator','auto'),'currency':p['currency'],'ean':p['ean'],'status':'pending','pack_count':1,'unit_ml':None}
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
