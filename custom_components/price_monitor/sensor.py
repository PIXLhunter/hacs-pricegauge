"""Current retailer-price sensors plus current product market aggregate sensors."""
from homeassistant.core import callback
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, SIGNAL
PARALLEL_UPDATES = 0

async def async_setup_entry(hass, entry, async_add_entities):
    manager = entry.runtime_data
    known = set()

    @callback
    def sync():
        new = []
        for product in manager.data['products']:
            for key in ('average', 'minimum', 'maximum'):
                uid = f"{product['id']}_{key}"
                if uid not in known:
                    known.add(uid)
                    new.append(ProductPriceSensor(manager, product['id'], key))
            for seller in product['sellers']:
                # Seller entities intentionally expose current price only.
                uid = f"{seller['id']}_price"
                if uid not in known:
                    known.add(uid)
                    new.append(RetailerPriceSensor(manager, product['id'], seller['id']))
        if new:
            async_add_entities(new)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL, sync))
    sync()

class MonetarySensor(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL, self.async_write_ha_state))

class RetailerPriceSensor(MonetarySensor):
    def __init__(self, manager, pid, sid):
        self.manager, self.pid, self.sid = manager, pid, sid
        product = manager.product(pid)
        seller = next(s for s in product['sellers'] if s['id'] == sid)
        self._attr_unique_id = f'{sid}_price'
        self._attr_name = f'{seller["store"]} price'
        self._attr_native_unit_of_measurement = product['currency']
        self._attr_device_info = {'identifiers': {(DOMAIN, pid)}, 'name': product['name'], 'manufacturer': 'PriceGauge'}

    def seller(self):
        try:
            product = self.manager.product(self.pid)
        except ValueError:
            return None
        return next((s for s in product['sellers'] if s['id'] == self.sid), None)

    @property
    def available(self):
        seller = self.seller()
        return bool(seller and seller.get('status') == 'ok')

    @property
    def native_value(self):
        seller = self.seller()
        return seller.get('price') if seller else None

class ProductPriceSensor(MonetarySensor):
    def __init__(self, manager, pid, key):
        self.manager, self.pid, self.key = manager, pid, key
        product = manager.product(pid)
        self._attr_unique_id = f'{pid}_{key}'
        self._attr_name = f'Product {key}'
        self._attr_native_unit_of_measurement = product['currency']
        self._attr_device_info = {'identifiers': {(DOMAIN, pid)}, 'name': product['name'], 'manufacturer': 'PriceGauge'}

    @property
    def native_value(self):
        try:
            return self.manager.view_product_summary(self.pid).get(self.key)
        except ValueError:
            return None
