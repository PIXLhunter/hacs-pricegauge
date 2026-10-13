"""Price entities and cached discovery overview."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
PARALLEL_UPDATES = 0

async def async_setup_entry(hass, entry, async_add_entities):
    keys = ["count"] if entry.data["mode"] == "search" else ["price", "lowest_price"]
    async_add_entities(PriceSensor(entry.runtime_data, key) for key in keys)

class PriceSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.key = key
        entry = coordinator.entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = {"price": "Price", "lowest_price": "Lowest observed price", "count": "Shopping candidates"}[key]
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": entry.title,
                                  "manufacturer": "Price Monitor"}
        if key != "count":
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_suggested_display_precision = 2
        self._attr_icon = "mdi:shopping-search" if key == "count" else "mdi:tag-outline"

    @property
    def native_value(self): return (self.coordinator.data or {}).get(self.key)

    @property
    def native_unit_of_measurement(self):
        return None if self.key == "count" else self.coordinator.settings["currency"]

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        if self.key == "count":
            return {k: data.get(k) for k in ("offers", "query", "notice", "checked_at", "discovery_status",
                    "budget_used", "budget_limit", "product_used", "product_limit", "cycle_end")}
        if self.key == "lowest_price":
            return {"meaning": "Lowest observed since tracking began; not historical market minimum"}
        return {k: data.get(k) for k in ("previous_price", "lowest_price", "change_percent", "target_price",
                "url", "source", "available", "ean_verified", "checked_at")}
