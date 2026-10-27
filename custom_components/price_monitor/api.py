"""Authenticated GUI commands with visible, redacted failures."""
import voluptuous as vol
from homeassistant.components import websocket_api
from .const import DOMAIN
from .parser import PriceError

@websocket_api.websocket_command({vol.Required('type'):'pricegauge/command',vol.Required('action'):str,
                                 vol.Optional('payload',default={}):dict})
@websocket_api.async_response
async def command(hass,connection,msg):
    manager=hass.data.get(DOMAIN)
    if not manager:
        connection.send_error(msg['id'],'not_initialized','PriceGauge backend not initialized; check HA startup logs')
        return
    action=msg['action'];p=msg['payload']
    try:
        if action=='state':result=manager.view()
        elif action=='inspect':
            currency=p.get('currency','EUR')
            if currency not in ('EUR','USD','GBP','CHF','CAD','AUD','JPY','SEK','NOK','DKK','PLN'):raise PriceError('Unsupported currency')
            result=await manager.inspect(p['url'],currency,p.get('ean',''))
        elif action=='select':
            if p.get('separator','auto') not in ('auto','.',','):raise PriceError('Invalid decimal separator')
            result=await manager.select(p['token'],p.get('node',''),p.get('separator','auto'))
        elif action=='add':
            pid=await manager.add(p)
            result={'product_id':pid,'discovery':await manager.discover(pid,force=True) if not p.get('product_id') else {'status':'cached_not_due'}}
        elif action=='remove':await manager.remove(p['product_id'],p.get('seller_id'));result={'removed':True}
        elif action=='settings':
            allowed={'api_key','monthly_budget','reserve','checks_per_month','reset_day','interval','country','language','notify_entity','notify_price_drop','notify_drop_percent','report_major_percent','report_interval_days'}
            if set(p)-allowed:raise PriceError('Unknown setting')
            await manager.settings(p);result={'saved':True}
        elif action=='discover':result=await manager.discover(p['product_id'],force=True)
        elif action=='product_settings':result=await manager.product_settings(p['product_id'],p.get('values',{}))
        elif action=='test_notification':result=await manager.test_notification()
        elif action=='resolve_offer':result=await manager.resolve_offer(p['product_id'],p['candidate_id'])
        elif action=='check':await manager.poll(force=True);result={'checked':True}
        elif action=='client_error':
            # Client diagnostics contain fixed stage/type only; no URLs, page text or secrets.
            stage=p.get('stage','frontend')
            if stage not in ('inspect','select','add','remove','settings','product_settings','test_notification','discover','resolve_offer','check','frontend'):stage='frontend'
            manager.log('ERROR','frontend_error',f'Frontend operation failed: {stage}')
            result={'logged':True}
        else:raise PriceError('Unknown GUI action')
        connection.send_result(msg['id'],result)
    except Exception as err:
        message=str(err) if isinstance(err,PriceError) else f'Operation failed ({type(err).__name__}); see GUI logs'
        manager.log('ERROR','gui_'+action[:40],message)
        connection.send_error(msg['id'],'pricegauge_error',message)
