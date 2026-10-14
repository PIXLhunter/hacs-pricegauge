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
                uid=f"{p['id']}_{key}"
                if uid not in known:known.add(uid);new.append(ProductSensor(manager,p['id'],key))
            for s in p['sellers']:
                uid=f"{s['id']}_price"
                if uid not in known:known.add(uid);new.append(RetailerSensor(manager,p['id'],s['id']))
        if new:async_add_entities(new)
    entry.async_on_unload(async_dispatcher_connect(hass,SIGNAL,sync));sync()
class Base(SensorEntity):
    _attr_should_poll=False;_attr_has_entity_name=True;_attr_device_class=SensorDeviceClass.MONETARY;_attr_suggested_display_precision=2
    async def async_added_to_hass(self):self.async_on_remove(async_dispatcher_connect(self.hass,SIGNAL,self.async_write_ha_state))
class RetailerSensor(Base):
    def __init__(self,m,pid,sid):
        self.m,self.pid,self.sid=m,pid,sid;p=m.product(pid);s=next(x for x in p['sellers'] if x['id']==sid)
        self._attr_unique_id=f'{sid}_price';self._attr_name=f'{s["store"]} price';self._attr_native_unit_of_measurement=p['currency'];self._attr_device_info={'identifiers':{(DOMAIN,pid)},'name':p['name'],'manufacturer':'PriceGauge'}
    def seller(self):
        try:p=self.m.product(self.pid)
        except ValueError:return None
        return next((s for s in p['sellers'] if s['id']==self.sid),None)
    @property
    def available(self):s=self.seller();return bool(s and s.get('status')=='ok')
    @property
    def native_value(self):s=self.seller();return s.get('price') if s else None
class ProductSensor(Base):
    def __init__(self,m,pid,key):
        self.m,self.pid,self.key=m,pid,key;p=m.product(pid);self._attr_unique_id=f'{pid}_{key}';self._attr_name=f'Product {key}';self._attr_native_unit_of_measurement=p['currency'];self._attr_device_info={'identifiers':{(DOMAIN,pid)},'name':p['name'],'manufacturer':'PriceGauge'}
    @property
    def native_value(self):
        try:return self.m.view_product_summary(self.pid).get(self.key)
        except ValueError:return None
