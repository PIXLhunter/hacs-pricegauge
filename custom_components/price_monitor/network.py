"""Public HTTP only, with DNS/redirect validation and bounded responses."""
import asyncio
import ipaddress
from urllib.parse import urlsplit,urljoin
import aiohttp
from aiohttp.resolver import DefaultResolver
from .parser import PriceError

def valid_url(url):
    p=urlsplit(url)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.port not in (None,80,443):
        raise PriceError('Use a public HTTP(S) product URL without credentials or custom port')
    try:ip=ipaddress.ip_address(p.hostname)
    except ValueError:ip=None
    if ip is not None and not ip.is_global:raise PriceError('Private/local addresses are not allowed')
    if p.hostname.lower()=='localhost' or p.hostname.lower().endswith(('.local','.localhost')):
        raise PriceError('Local addresses are not allowed')
    return url

class PublicResolver(DefaultResolver):
    async def resolve(self,host,port=0,family=0):
        results=await super().resolve(host,port,family)
        if any(not ipaddress.ip_address(r['host']).is_global for r in results):
            raise OSError('Non-public DNS address rejected')
        return results

class Network:
    def __init__(self):self.session=None;self.locks={};self.backoff={}
    async def start(self):
        self.session=aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=PublicResolver(),limit=8),
            timeout=aiohttp.ClientTimeout(total=35),headers={'User-Agent':'HomeAssistant-PriceGauge/0.3.1'})
    async def close(self):
        if self.session:await self.session.close()
    async def html(self,url):
        valid_url(url);host=urlsplit(url).hostname
        async with self.locks.setdefault(host,asyncio.Lock()):
            loop=asyncio.get_running_loop()
            if self.backoff.get(host,0)>loop.time():raise PriceError('Retailer is rate limited; retry later')
            for _ in range(6):
                valid_url(url)
                async with self.session.get(url,allow_redirects=False) as r:
                    if r.status in (301,302,303,307,308):
                        if not r.headers.get('Location'):raise PriceError('Invalid retailer redirect')
                        url=urljoin(url,r.headers['Location']);continue
                    if r.status==429:
                        try:delay=max(60,min(86400,int(r.headers.get('Retry-After','3600'))))
                        except ValueError:delay=3600
                        self.backoff[host]=loop.time()+delay
                        raise PriceError('Retailer rate limited (HTTP 429)')
                    if r.status!=200:raise PriceError(f'Retailer returned HTTP {r.status}')
                    raw=bytearray()
                    async for chunk in r.content.iter_chunked(65536):
                        raw.extend(chunk)
                        if len(raw)>4*1024*1024:raise PriceError('Page exceeds 4 MiB limit')
                    return raw.decode(r.charset or 'utf-8',errors='replace')
            raise PriceError('Too many retailer redirects')
    async def shopping(self,params):
        async with self.session.get('https://serpapi.com/search.json',params=params,allow_redirects=False) as r:
            if r.status in (401,403):raise PriceError('SerpApi key rejected; update it in GUI settings')
            if r.status!=200:raise PriceError(f'SerpApi returned HTTP {r.status}')
            raw=bytearray()
            async for chunk in r.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw)>4*1024*1024:raise PriceError('Discovery response too large')
            import json
            try:data=json.loads(raw)
            except ValueError as err:raise PriceError('Invalid discovery JSON') from err
            if not isinstance(data,dict) or data.get('error'):raise PriceError('SerpApi error; check account/quota')
            return data
