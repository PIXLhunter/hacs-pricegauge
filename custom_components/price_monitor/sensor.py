"""Dynamic seller sensors managed by the GUI."""
from homeassistant.core import callback
from homeassistant.components.sensor import SensorEntity,SensorDeviceClass
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN,SIGNAL
PARALLEL_UPDATES=0

async def async_setup_entry(hass,entry,async_add_entities):
    manager=entry.runtime_data;known=set()
    @callback
    def sync():
        new=[]
        for p in manager.data['products']:
            for key in ('average','minimum','maximum'):
                uid=f'{p["id"]}_{key}'
                if uid not in known:known.add(uid);new.append(ProductSensor(manager,p['id'],key))
            for s in p['sellers']:
                for key in ('price',):
                    uid=f'{s["id"]}_{key}'
                    if uid not in known:known.add(uid);new.append(PriceSensor(manager,p['id'],s['id'],key))
        if new:async_add_entities(new)
    entry.async_on_unload(async_dispatcher_connect(hass,SIGNAL,sync));sync()

class PriceSensor(SensorEntity):
    _attr_should_poll=False
    _attr_has_entity_name=True
    _attr_device_class=SensorDeviceClass.MONETARY
    _attr_suggested_display_precision=2
    def __init__(self,manager,pid,sid,key):
        self.manager=manager;self.pid=pid;self.sid=sid;self.key=key
        p=manager.product(pid);s=next(s for s in p['sellers'] if s['id']==sid)
        self._attr_unique_id=f'{sid}_{key}';self._attr_name=f'{s["store"]} {key}'
        self._attr_native_unit_of_measurement=p['currency']
        self._attr_device_info={'identifiers':{(DOMAIN,pid)},'name':p['name'],'manufacturer':'PriceGauge'}
    def seller(self):
        try:p=self.manager.product(self.pid)
        except ValueError:return None
        return next((s for s in p['sellers'] if s['id']==self.sid),None)
    @property
    def available(self):
        s=self.seller();return bool(s and s.get('status')=='ok')
    @property
    def native_value(self):
        s=self.seller()
        if not s:return None
        return s.get('price')
    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass,SIGNAL,self.async_write_ha_state))

class ProductSensor(SensorEntity):
    _attr_should_poll=False
    _attr_has_entity_name=True
    _attr_device_class=SensorDeviceClass.MONETARY
    _attr_suggested_display_precision=2
    def __init__(self,manager,pid,key):
        self.manager,self.pid,self.key=manager,pid,key;p=manager.product(pid);self._attr_unique_id=f'{pid}_{key}';self._attr_name=f'Product {key}';self._attr_native_unit_of_measurement=p['currency'];self._attr_device_info={'identifiers':{(DOMAIN,pid)},'name':p['name'],'manufacturer':'PriceGauge'}
    @property
    def native_value(self):
        try:return self.manager.view_product_summary(self.pid).get(self.key)
        except ValueError:return None
    async def async_added_to_hass(self):self.async_on_remove(async_dispatcher_connect(self.hass,SIGNAL,self.async_write_ha_state))
