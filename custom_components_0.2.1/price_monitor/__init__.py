"""Price Monitor custom integration."""
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from .const import DOMAIN, PLATFORMS
from .coordinator import PriceCoordinator

async def async_setup(hass, config):
    from .panel import async_setup_panel_api
    await async_setup_panel_api(hass)
    return True

async def async_setup_entry(hass, entry):
    coordinator = PriceCoordinator(hass, entry, async_get_clientsession(hass))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_remove_entry(hass, entry):
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
    # Account usage/cache deliberately survives entry deletion, preventing quota reset abuse.

async def async_migrate_entry(hass, entry):
    if entry.version > 2:
        return False
    if entry.version == 1:
        data = dict(entry.data)
        options = dict(entry.options)
        if data.get("mode") == "search":
            # Preserve identities edited under 0.1.0 before making them immutable.
            for key in ("query", "ean", "country", "language"):
                if key in options:
                    data[key] = options.pop(key)
        hass.config_entries.async_update_entry(entry, data=data, options=options,
                                               unique_id=None, version=2)
    return True
