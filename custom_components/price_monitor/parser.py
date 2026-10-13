"""One soup per download. Inspection is inert text/structure, never remote HTML."""
import json
import re
import math
from decimal import Decimal, InvalidOperation
from bs4 import BeautifulSoup, Tag, NavigableString, Comment

class PriceError(ValueError): pass

def money(value, separator="auto"):
    text = str(value).replace("\u00a0", " ").replace("\u202f", " ")
    values = re.findall(r"(?<!\w)[+-]?\d[\d., '\u2019]*(?!\w)", text)
    if len(values) != 1: raise PriceError("Selected element must contain exactly one price")
    raw = values[0].strip().replace(" ", "").replace("'", "").replace("\u2019", "")
    if separator == "auto":
        if "." in raw and "," in raw: separator = "." if raw.rfind(".") > raw.rfind(",") else ","
        elif "." in raw or "," in raw:
            separator = "." if "." in raw else ","
            parts = raw.split(separator)
            if len(parts) != 2 or len(parts[-1]) not in (1,2):
                raise PriceError("Ambiguous separator; choose decimal comma or dot")
        else: separator = "."
    other = "," if separator == "." else "."
    integer = raw.split(separator,1)[0]
    if other in raw:
        groups = integer.split(other)
        if other in raw[len(integer):] or not 1 <= len(groups[0]) <= 3 or any(len(g)!=3 for g in groups[1:]):
            raise PriceError("Invalid thousands grouping")
    raw = raw.replace(other, "").replace(separator, ".")
    try: value = Decimal(raw)
    except InvalidOperation as err: raise PriceError("Invalid price") from err
    if not value.is_finite() or value < 0 or not math.isfinite(float(value)):
        raise PriceError("Invalid non-finite or negative price")
    return float(value)

def walk(value):
    if isinstance(value,dict):
        yield value
        for v in value.values(): yield from walk(v)
    elif isinstance(value,list):
        for v in value: yield from walk(v)

def kind(obj,name):
    v=obj.get('@type',[])
    if isinstance(v,str):v=[v]
    return isinstance(v,list) and any(str(t).split('/')[-1]==name for t in v)

def parse(html):
    soup=BeautifulSoup(html,'html.parser')
    products=[]
    for script in soup.find_all('script',attrs={'type':'application/ld+json'}):
        try: data=json.loads(script.string or script.get_text())
        except (ValueError,TypeError):continue
        products.extend(n for n in walk(data) if kind(n,'Product'))
    return soup,products

def metadata(soup,products):
    p=products[0] if len(products)==1 else {}
    name=p.get('name') or (soup.title.get_text(' ',strip=True) if soup.title else '')
    ean=next((str(p[k]) for k in ('gtin13','gtin14','gtin12','gtin8','gtin') if p.get(k)), '')
    return {'name':str(name)[:200],'ean':ean}

def extract(soup,products,s):
    selector=s.get('selector','').strip();currency=s.get('currency','EUR')
    if selector:
        try: nodes=soup.select(selector)
        except Exception as err:raise PriceError('Invalid CSS selector') from err
        if len(nodes)!=1:raise PriceError(f'CSS selector matched {len(nodes)} elements; expected one')
        attr=s.get('attribute','')
        value=nodes[0].get(attr) if attr else nodes[0].get_text(' ',strip=True)
        if value is None:raise PriceError('Selected attribute missing')
        return {'price':money(value,s.get('separator','auto')),'source':'css','currency':currency}
    ean=s.get('ean','')
    if ean:
        products=[p for p in products if any(str(p.get(k,''))==ean for k in ('gtin','gtin8','gtin12','gtin13','gtin14'))]
        if not products:raise PriceError('No Product matching the requested EAN; inspect the exact variant')
    values=[];saw_offer=False
    for p in products:
        for offer in walk(p.get('offers',[])):
            if kind(offer,'AggregateOffer'):saw_offer=True;continue
            if 'price' not in offer:continue
            saw_offer=True
            if offer.get('priceCurrency')!=currency:continue
            try:values.append(money(offer['price'],'.'))
            except PriceError:continue
    if not values and not ean and not saw_offer:
        for sel in ('meta[property="product:price:amount"]','[itemprop="price"]'):
            for el in soup.select(sel):
                try:values.append(money(el.get('content') or el.get_text(' ',strip=True),s.get('separator','auto')))
                except PriceError:continue
            if values:break
    if not values:raise PriceError('No price in static HTML; use inspection or a supported retailer')
    if len(set(values))!=1:raise PriceError('Multiple prices found; click the exact product price')
    return {'price':values[0],'source':'structured','currency':currency}

def path_for(el):
    parts=[]
    while isinstance(el,Tag) and el.name!='[document]':
        siblings=[n for n in el.parent.children if isinstance(n,Tag) and n.name==el.name] if el.parent else [el]
        index=next(i for i,n in enumerate(siblings,1) if n is el)
        parts.append(f'{el.name}:nth-of-type({index})');el=el.parent
    return ' > '.join(reversed(parts))

ALLOWED={'div','span','p','b','strong','em','i','small','h1','h2','h3','h4','ul','ol','li','table','thead','tbody','tr','td','th','section','article','main','header','footer','br','dl','dt','dd','label'}
SKIP={'script','style','iframe','object','embed','svg','canvas','template','noscript','link','base'}

def preview(soup,limit=6000):
    mapping={};counter=0;truncated=False
    def node(el):
        nonlocal counter,truncated
        if isinstance(el,Comment):return None
        if isinstance(el,NavigableString):return str(el)[:500] if str(el).strip() else None
        if not isinstance(el,Tag) or el.name in SKIP:return None
        if el.has_attr('hidden') or el.get('aria-hidden')=='true' or 'display:none' in str(el.get('style','')).replace(' ','').lower():return None
        if counter>=limit:truncated=True;return None
        counter+=1;key=str(counter)
        mapping[key]={'selector':path_for(el),'attribute':'content' if el.name=='meta' and el.get('content') else ''}
        if el.name=='meta':
            if el.get('itemprop')!='price' and el.get('property')!='product:price:amount':return None
            children=[str(el.get('content',''))]
        else:children=[v for child in el.children if (v:=node(child)) is not None]
        if not children:return None
        return {'tag':el.name if el.name in ALLOWED else 'div','id':key,'children':children}
    tree=[v for el in soup.children if (v:=node(el)) is not None]
    return {'tree':tree,'truncated':truncated},mapping
