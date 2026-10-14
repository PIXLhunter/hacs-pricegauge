"""GUI-first initialization independent of retailer availability."""
from datetime import timedelta
import logging
import voluptuous as vol
from pathlib import Path
from homeassistant.components import frontend,websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.event import async_track_time_interval
from .const import DOMAIN,VERSION
from .manager import Manager
from .api import command

_LOGGER=logging.getLogger(__name__)
CONFIG_SCHEMA=vol.Schema({vol.Optional(DOMAIN):vol.Schema({})},extra=vol.ALLOW_EXTRA)

async def async_setup(hass,config):
    if DOMAIN in hass.data:return True
    manager=Manager(hass)
    try:
        await manager.start();hass.data[DOMAIN]=manager
        await hass.http.async_register_static_paths([StaticPathConfig('/pricegauge-ui',str(Path(__file__).parent/'frontend'),False)])
        websocket_api.async_register_command(hass,command)
        frontend.async_register_built_in_panel(hass,'custom',sidebar_title='PriceGauge',sidebar_icon='mdi:tag-outline',
            frontend_url_path='pricegauge',require_admin=False,config={'_panel_custom':{
                'name':'pricegauge-panel','module_url':f'/pricegauge-ui/panel.js?v={VERSION}',
                'embed_iframe':False,'trust_external':False}})
        async def tick(_):
            try:await manager.poll()
            except Exception as err:manager.log('ERROR','poll_unhandled',f'Polling failed ({type(err).__name__})')
        cancel=async_track_time_interval(hass,tick,timedelta(minutes=1))
        async def stop(_):cancel();await manager.net.close()
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP,stop)
        # One internal entry owns dynamic sensors. No user configuration flow is needed.
        hass.async_create_task(hass.config_entries.flow.async_init(DOMAIN,context={'source':'import'},data={'gui_manager':True}))
        manager.log('INFO','panel_registered','Sidebar/API registered; retailer failures cannot block the panel')
        return True
    except Exception:
        _LOGGER.exception('PriceGauge initialization failed')
        await manager.net.close();hass.data.pop(DOMAIN,None)
        return False

async def async_setup_entry(hass,entry):
    manager=hass.data[DOMAIN]
    if entry.data.get('gui_manager'):
        entry.runtime_data=manager
        await hass.config_entries.async_forward_entry_setups(entry,['sensor'])
    else:
        await manager.import_entry(entry)
    return True

async def async_unload_entry(hass,entry):
    if entry.data.get('gui_manager'):return await hass.config_entries.async_unload_platforms(entry,['sensor'])
    return True

async def async_migrate_entry(hass,entry):
    if entry.version>3:return False
    if entry.version<3:hass.config_entries.async_update_entry(entry,version=3)
    return True
