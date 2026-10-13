"""Independent retailer polling and quota-controlled cached discovery."""
from datetime import timedelta
import logging
import aiohttp
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from .client import fetch_price, search_offers, RateLimited
from .scraper import PriceError
from .budget import DiscoveryBudget
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class PriceCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, session):
        self.entry = entry
        self.settings = {**entry.data, **entry.options}
        self.session = session
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.saved = {}
        self.force_discovery = False
        self.budget = hass.data.setdefault("price_monitor_discovery_budget", DiscoveryBudget(hass))
        interval = 60 if self.settings["mode"] == "search" else self.settings.get("interval", 60)
        super().__init__(hass, _LOGGER, name=entry.title, config_entry=entry,
                         update_interval=timedelta(minutes=interval))

    async def _async_setup(self):
        self.saved = await self.store.async_load() or {}
        if self.saved.get("currency") != self.settings.get("currency", "EUR"):
            self.saved = {}

    async def _discovery(self):
        force, self.force_discovery = self.force_discovery, False
        status = await self.budget.reserve(self.settings, force=force)
        cache = status.pop("cache")
        if not status["allowed"]:
            return {**{"offers": [], "count": 0}, **cache, **status,
                    "discovery_status": status["reason"]}
        try:
            data = await search_offers(self.session, self.settings)
        except (aiohttp.ClientError, TimeoutError, PriceError):
            # Keep cached candidates visible; no repeated API retries within the allocation spacing.
            return {**{"offers": [], "count": 0}, **cache, **status,
                    "discovery_status": "request_failed_cache_retained"}
        data["checked_at"] = dt_util.utcnow().isoformat()
        await self.budget.save_cache(self.settings, data)
        return {**data, **status, "discovery_status": "updated"}

    async def _async_update_data(self):
        if self.settings["mode"] == "search":
            return await self._discovery()
        try:
            result = await fetch_price(self.hass, self.session, self.settings)
        except RateLimited as err:
            raise UpdateFailed("Retailer rate limited", retry_after=err.retry_after) from None
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            message = str(err) if isinstance(err, PriceError) else "HTTP request failed"
            raise UpdateFailed(message) from None
        price = result["price"]
        previous = self.saved.get("price")
        lowest = min(price, self.saved.get("lowest", price))
        changed = previous is not None and price != previous
        result.update(previous_price=previous, lowest_price=lowest,
                      change_percent=round((price-previous)/previous*100, 4) if previous else None,
                      target_price=self.settings.get("target", 0),
                      checked_at=dt_util.utcnow().isoformat(), url=self.settings["url"])
        if changed or previous is None:
            saved = {"price": price, "lowest": lowest, "currency": result["currency"]}
            await self.store.async_save(saved)
            self.saved = saved
        if changed and price < previous:
            self.hass.bus.async_fire("price_monitor_price_drop", {
                "entry_id": self.entry.entry_id, "name": self.entry.title,
                "price": price, "previous_price": previous, "currency": result["currency"],
                "url": self.settings["url"], "change_percent": result["change_percent"]})
        return result
