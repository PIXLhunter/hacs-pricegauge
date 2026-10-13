"""Price-only target indicator."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
PARALLEL_UPDATES = 0

async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data["mode"] == "monitor": async_add_entities([TargetSensor(entry.runtime_data)])

class TargetSensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Target reached"
    _attr_icon = "mdi:tag-check"
    def __init__(self, coordinator):
        super().__init__(coordinator)
        entry = coordinator.entry
        self._attr_unique_id = f"{entry.entry_id}_target"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}
    @property
    def is_on(self):
        price = (self.coordinator.data or {}).get("price")
        target = self.coordinator.settings.get("target", 0)
        return bool(target > 0 and price is not None and price <= target)
