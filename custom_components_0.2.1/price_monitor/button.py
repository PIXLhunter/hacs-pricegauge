"""Manual discovery consumes the same shared budget as scheduled discovery."""
from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data["mode"] == "search":
        async_add_entities([DiscoveryButton(entry.runtime_data)])

class DiscoveryButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Discover stores now"
    _attr_icon = "mdi:shopping-search"
    _attr_entity_category = EntityCategory.CONFIG
    def __init__(self, coordinator):
        self.coordinator = coordinator
        entry = coordinator.entry
        self._attr_unique_id = f"{entry.entry_id}_discover"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}

    async def async_press(self):
        self.coordinator.force_discovery = True
        await self.coordinator.async_request_refresh()
