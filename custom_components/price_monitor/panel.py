"""Admin-only diagnostics independent of successful entry setup."""
import asyncio
from pathlib import Path
from urllib.parse import urlsplit
import aiohttp
import voluptuous as vol
from bs4 import BeautifulSoup
from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .scraper import PriceError, extract_price, parse_price

DOMAIN = 'price_monitor'
MAX_HTML = 4 * 1024 * 1024

async def async_setup_panel_api(hass):
    if hass.data.get('price_monitor_panel_registered'):
        return
    await hass.http.async_register_static_paths([
        StaticPathConfig('/price_monitor_frontend', str(Path(__file__).parent/'frontend'), False)])
    for command in (ws_list, ws_test, ws_save):
        websocket_api.async_register_command(hass, command)
    hass.data['price_monitor_panel_registered'] = True

def get_entry(hass, entry_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.data.get('mode') != 'monitor':
        raise ValueError('Retailer entry not found')
    return entry

def diagnose(html, settings):
    selector = settings.get('selector', '').strip()
    if not selector:
        try:
            return {'ok': True, 'price': extract_price(html, settings), 'matches': None, 'candidates': []}
        except PriceError as err:
            return {'ok': False, 'error': str(err), 'matches': None, 'candidates': []}
    soup = BeautifulSoup(html, 'html.parser')
    try:
        elements = soup.select(selector)
    except Exception:
        return {'ok': False, 'error': 'Invalid CSS selector', 'matches': None, 'candidates': []}
    attribute = settings.get('attribute', '').strip()
    candidates = []
    for index, element in enumerate(elements[:20]):
        value = element.get(attribute) if attribute else element.get_text(' ', strip=True)
        candidates.append({'index': index, 'value': str(value)[:300] if value is not None else None,
                           'tag': element.name})
    result = {'ok': False, 'matches': len(elements), 'candidates': candidates}
    if len(elements) != 1:
        result['error'] = f'Selector matched {len(elements)} elements; expected exactly one'
        return result
    value = elements[0].get(attribute) if attribute else elements[0].get_text(' ', strip=True)
    if value is None:
        return {**result, 'error': 'Selected attribute is missing'}
    try:
        price = float(parse_price(value, settings.get('decimal_separator', 'auto')))
    except PriceError as err:
        return {**result, 'error': str(err)}
    return {**result, 'ok': True, 'price': {'price': price, 'currency': settings.get('currency', 'EUR'),
            'source': 'css', 'ean_verified': False, 'available': None}}

@websocket_api.websocket_command({vol.Required('type'): 'price_monitor/panel_list'})
@callback
def ws_list(hass, connection, msg):
    connection.require_admin()
    result = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get('mode') != 'monitor':
            continue
        s = {**entry.data, **entry.options}
        runtime = getattr(entry, 'runtime_data', None)
        data = getattr(runtime, 'data', None) or {}
        result.append({'entry_id': entry.entry_id, 'title': entry.title,
                       'state': entry.state.value, 'price': data.get('price'),
                       'url': s.get('url'), 'currency': s.get('currency', 'EUR'),
                       'selector': s.get('selector', ''), 'attribute': s.get('attribute', ''),
                       'decimal_separator': s.get('decimal_separator', 'auto')})
    connection.send_result(msg['id'], result)

@websocket_api.websocket_command({vol.Required('type'): 'price_monitor/panel_test',
    vol.Required('entry_id'): str, vol.Required('selector'): str,
    vol.Required('attribute'): str, vol.Required('decimal_separator'): vol.In(['auto', '.', ','])})
@websocket_api.async_response
async def ws_test(hass, connection, msg):
    connection.require_admin()
    try:
        entry = get_entry(hass, msg['entry_id'])
        s = {**entry.data, **entry.options, **{k: msg[k] for k in ('selector','attribute','decimal_separator')}}
        url = s['url']
        parsed = urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Invalid configured retailer URL')
        locks = hass.data.setdefault('price_monitor_host_locks', {})
        lock = locks.setdefault(parsed.hostname, asyncio.Lock())
        async with lock:
            async with asyncio.timeout(30):
                async with async_get_clientsession(hass).get(url, headers={'User-Agent':'HomeAssistant-PriceMonitor/0.2.1'}) as response:
                    if response.status != 200:
                        connection.send_result(msg['id'], {'ok':False,'error':f'Retailer returned HTTP {response.status}'})
                        return
                    content = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        content.extend(chunk)
                        if len(content)>MAX_HTML:
                            raise ValueError('HTML exceeds 4 MiB')
                    html = content.decode(response.charset or 'utf-8', errors='replace')
            result = await hass.async_add_executor_job(diagnose, html, s)
        connection.send_result(msg['id'], result)
    except (ValueError, aiohttp.ClientError, TimeoutError):
        connection.send_error(msg['id'], 'test_failed', 'Could not test the configured retailer page')

@websocket_api.websocket_command({vol.Required('type'): 'price_monitor/panel_save',
    vol.Required('entry_id'): str, vol.Required('selector'): str,
    vol.Required('attribute'): str, vol.Required('decimal_separator'): vol.In(['auto', '.', ','])})
@websocket_api.async_response
async def ws_save(hass, connection, msg):
    connection.require_admin()
    try:
        entry = get_entry(hass, msg['entry_id'])
    except ValueError:
        connection.send_error(msg['id'], 'not_found', 'Retailer entry not found')
        return
    options = {**entry.options, **{k: msg[k] for k in ('selector','attribute','decimal_separator')}}
    # Successful entries already have an options listener; failed entries do not.
    loaded = entry.state.value == "loaded"
    hass.config_entries.async_update_entry(entry, options=options)
    # Explicit reload also recovers entries whose failed setup never registered an options listener.
    if not loaded:
        await hass.config_entries.async_reload(entry.entry_id)
    connection.send_result(msg['id'], {'saved': True})
