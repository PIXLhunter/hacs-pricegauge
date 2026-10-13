"""One HTML fetch/parse per poll; one Shopping request per discovery."""
import asyncio
from urllib.parse import urlsplit
import aiohttp
from homeassistant.exceptions import ConfigEntryAuthFailed
from .scraper import extract_price, PriceError

MAX_HTML = 4*1024*1024

class RateLimited(PriceError):
    def __init__(self, retry_after=3600):
        self.retry_after = retry_after
        super().__init__("Rate limited")

def validate_url(url):
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise PriceError("Use an HTTP(S) URL without credentials")
    return url

def backoff(response):
    try:
        return max(60, min(86400, int(response.headers.get("Retry-After", "3600"))))
    except ValueError:
        return 3600

async def fetch_price(hass, session, s):
    url = validate_url(s["url"])
    host = urlsplit(url).hostname
    locks = hass.data.setdefault("price_monitor_host_locks", {})
    lock = locks.setdefault(host, asyncio.Lock())
    async with lock:
        async with asyncio.timeout(30):
            async with session.get(url, headers={"User-Agent": "HomeAssistant-PriceMonitor/0.2"}) as response:
                if response.status == 429:
                    raise RateLimited(backoff(response))
                if response.status in (401, 403):
                    raise PriceError("Retailer blocked access; no bypass attempted")
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    content.extend(chunk)
                    if len(content) > MAX_HTML:
                        raise PriceError("HTML exceeds 4 MiB")
                html = content.decode(response.charset or "utf-8", errors="replace")
        return await hass.async_add_executor_job(extract_price, html, s)

async def search_offers(session, s):
    params = {"engine": "google_shopping", "q": s.get("ean", "").strip() or s.get("query", "").strip(),
              "api_key": s["api_key"].strip(), "gl": s.get("country", "nl"), "hl": s.get("language", "en"), "safe": "active"}
    async with asyncio.timeout(60):
        async with session.get("https://serpapi.com/search.json", params=params) as response:
            if response.status in (401, 403):
                raise ConfigEntryAuthFailed("SerpApi authentication failed")
            if response.status == 429:
                raise RateLimited(backoff(response))
            if response.status != 200:
                raise PriceError(f"Shopping API returned HTTP {response.status}")
            raw = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                raw.extend(chunk)
                if len(raw) > MAX_HTML:
                    raise PriceError("Shopping response too large")
            import json
            try:
                data = json.loads(raw)
            except (ValueError, UnicodeDecodeError) as err:
                raise PriceError("Invalid Shopping response") from err
    if not isinstance(data, dict) or data.get("error"):
        raise PriceError("Shopping API error; check account and quota")
    results = data.get("shopping_results", [])
    if not isinstance(results, list):
        raise PriceError("Invalid shopping_results")
    offers = []
    for item in results[:40]:
        if not isinstance(item, dict):
            continue
        link = item.get("product_link") or item.get("link")
        if not isinstance(link, str) or urlsplit(link).scheme not in ("http", "https"):
            link = None
        offers.append({"title": item.get("title"), "seller": item.get("source"),
                       "price_text": item.get("price"), "price": item.get("extracted_price"),
                       "link": link, "delivery": item.get("delivery"), "ean_verified": False})
    return {"offers": offers, "count": len(offers), "query": params["q"],
            "notice": "Discovery candidates only. Verify product/variant and manually add preferred retailer URLs."}
