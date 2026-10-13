"""Conservative static HTML price parser."""
import json
import re
from decimal import Decimal, InvalidOperation
from bs4 import BeautifulSoup

class PriceError(ValueError):
    """Missing, ambiguous or invalid price."""

def parse_price(value, decimal_separator="auto"):
    text = str(value).replace("\u00a0", " ").replace("\u202f", " ").strip()
    matches = re.findall(r"(?<!\w)[+-]?\d[\d., '\u2019]*(?!\w)", text)
    if len(matches) != 1:
        raise PriceError("Expected exactly one money value")
    raw = matches[0].strip().replace(" ", "").replace("'", "").replace("\u2019", "")
    if decimal_separator in (".", ","):
        other = "," if decimal_separator == "." else "."
        integer = raw.split(decimal_separator, 1)[0]
        if other in raw:
            groups = integer.split(other)
            if other in raw[len(integer):] or not (1 <= len(groups[0]) <= 3) or any(len(g) != 3 for g in groups[1:]):
                raise PriceError("Invalid thousands grouping for configured separator")
        raw = raw.replace(other, "").replace(decimal_separator, ".")
    elif "." in raw and "," in raw:
        decimal = "." if raw.rfind(".") > raw.rfind(",") else ","
        raw = raw.replace("," if decimal == "." else ".", "").replace(decimal, ".")
    elif "." in raw or "," in raw:
        separator = "." if "." in raw else ","
        parts = raw.split(separator)
        if len(parts) != 2 or len(parts[1]) not in (1, 2):
            raise PriceError("Ambiguous separator; configure decimal separator")
        raw = raw.replace(separator, ".")
    try:
        price = Decimal(raw)
    except InvalidOperation as err:
        raise PriceError("Invalid money value") from err
    if not price.is_finite() or price < 0:
        raise PriceError("Price must be non-negative and finite")
    return price

def nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from nodes(child)

def type_is(obj, expected):
    types = obj.get("@type", [])
    if isinstance(types, str): types = [types]
    return isinstance(types, list) and any(str(t).split("/")[-1] == expected for t in types)

def extract_price(html, settings):
    soup = BeautifulSoup(html, "html.parser")
    currency = settings.get("currency", "EUR").upper()
    selector = settings.get("selector", "").strip()
    separator = settings.get("decimal_separator", "auto")
    if selector:
        try: selected = soup.select(selector)
        except Exception as err: raise PriceError("Invalid CSS selector") from err
        if len(selected) != 1: raise PriceError("CSS selector must match exactly one element")
        attribute = settings.get("attribute", "").strip()
        value = selected[0].get(attribute) if attribute else selected[0].get_text(" ", strip=True)
        if value is None: raise PriceError("Selected attribute missing")
        return {"price": float(parse_price(value, separator)), "currency": currency,
                "source": "css", "available": None, "ean_verified": False}
    products = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try: data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError): continue
        products.extend(n for n in nodes(data) if type_is(n, "Product"))
    ean = settings.get("ean", "").strip()
    if ean:
        products = [p for p in products if any(str(p.get(k, "")) == ean
                    for k in ("gtin", "gtin8", "gtin12", "gtin13", "gtin14"))]
        if not products: raise PriceError("No structured Product matching EAN")
    candidates = []
    saw_offers = False
    for product in products:
        for offer in nodes(product.get("offers", [])):
            if "price" not in offer: continue
            saw_offers = True
            if type_is(offer, "AggregateOffer"): continue
            if str(offer.get("priceCurrency", "")).upper() != currency: continue
            try: price = float(parse_price(offer["price"], "."))
            except PriceError: continue
            stock = str(offer.get("availability", "")).split("/")[-1]
            available = True if stock == "InStock" else False if stock in ("OutOfStock", "SoldOut", "Discontinued") else None
            candidates.append({"price": price, "currency": currency, "source": "json_ld",
                               "available": available, "ean_verified": bool(ean)})
    if not candidates and not ean and not saw_offers:
        for sel in ('meta[property="product:price:amount"]', '[itemprop="price"]'):
            for element in soup.select(sel):
                value = element.get("content") or element.get_text(" ", strip=True)
                try: price = float(parse_price(value, separator))
                except PriceError: continue
                candidates.append({"price": price, "currency": currency, "source": "metadata",
                                   "available": None, "ean_verified": False})
            if candidates: break
    if not candidates: raise PriceError("No unambiguous price in downloaded HTML")
    if len({c["price"] for c in candidates}) != 1:
        raise PriceError("Multiple prices; configure exact CSS selector")
    result = candidates[0]
    if len({c["available"] for c in candidates}) > 1: result["available"] = None
    return result
