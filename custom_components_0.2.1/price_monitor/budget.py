"""Persisted account-wide discovery quotas. No network calls here."""
import asyncio
import calendar
import hashlib
from datetime import datetime, timezone, timedelta
from homeassistant.helpers.storage import Store

DOMAIN = "price_monitor"

def settings(entry):
    return {**entry.data, **entry.options}

def account_id(key):
    return hashlib.sha256(key.encode()).hexdigest()

def query_id(s):
    query = s.get("ean", "").strip() or s.get("query", "").strip()
    value = "|".join([query.casefold(), s.get("country", "nl"), s.get("language", "en")])
    return hashlib.sha256(value.encode()).hexdigest()

def cycle_bounds(now, reset_day):
    now = now.astimezone(timezone.utc)
    def boundary(year, month):
        day = min(reset_day, calendar.monthrange(year, month)[1])
        return datetime(year, month, day, tzinfo=timezone.utc)
    start = boundary(now.year, now.month)
    if now < start:
        year, month = (now.year-1, 12) if now.month == 1 else (now.year, now.month-1)
        start = boundary(year, month)
    year, month = (start.year+1, 1) if start.month == 12 else (start.year, start.month+1)
    return start, boundary(year, month)

def allocation(total, groups, group, cycle):
    """Fair remainder rotates each cycle; works even when groups exceed budget."""
    groups = sorted(groups)
    if group not in groups or not groups:
        return 0
    base, extra = divmod(total, len(groups))
    offset = (cycle.year*12 + cycle.month) % len(groups)
    rank = (groups.index(group)-offset) % len(groups)
    return base + int(rank < extra)

class DiscoveryBudget:
    def __init__(self, hass):
        self.hass = hass
        self.lock = asyncio.Lock()
        self.store = Store(hass, 1, "price_monitor.discovery_budget")
        self.state = None

    async def _load(self):
        if self.state is None:
            self.state = await self.store.async_load() or {}

    def _policy(self, s, now):
        key = s.get("api_key", "").strip()
        account = account_id(key)
        entries = [settings(e) for e in self.hass.config_entries.async_entries(DOMAIN)
                   if settings(e).get("mode") == "search"
                   and settings(e).get("api_key", "").strip() == key]
        if not entries:
            entries = [s]
        days = {int(e.get("reset_day", 1)) for e in entries}
        if len(days) != 1:
            return None, "reset_day_conflict"
        start, end = cycle_bounds(now, days.pop())
        # Most conservative configured account policy wins.
        total = min(max(0, int(e.get("monthly_budget", 250))-int(e.get("reserve", 25))) for e in entries)
        groups = {query_id(e) for e in entries}
        group = query_id(s)
        share = allocation(total, groups, group, start)
        cap = min(int(e.get("checks_per_month", 4)) for e in entries if query_id(e) == group)
        share = min(share, cap)
        return (account, group, start, end, total, share), None

    async def reserve(self, s, force=False, now=None):
        now = now or datetime.now(timezone.utc)
        async with self.lock:
            await self._load()
            if not s.get("api_key", "").strip():
                return {"allowed": False, "reason": "no_api_key", "cache": {}}
            policy, error = self._policy(s, now)
            if error:
                return {"allowed": False, "reason": error, "cache": {}}
            account, group, start, end, total, share = policy
            a = self.state.setdefault(account, {})
            if a.get("cycle") != start.isoformat():
                a.update(cycle=start.isoformat(), used=0, groups={})
            g = a.setdefault("groups", {}).setdefault(group, {"used": 0})
            cache = a.setdefault("cache", {}).get(group, {})
            result = {"allowed": False, "cache": cache, "budget_used": a["used"],
                      "budget_limit": total, "product_limit": share, "product_used": g["used"],
                      "cycle_end": end.isoformat()}
            if a["used"] >= total or g["used"] >= share or share == 0:
                return {**result, "reason": "budget_exhausted"}
            last = g.get("last_attempt")
            spacing = (end-start).total_seconds()/share
            if not force and last and (now-datetime.fromisoformat(last)).total_seconds() < spacing:
                return {**result, "reason": "cached_not_due"}
            a["used"] += 1
            g["used"] += 1
            g["last_attempt"] = now.isoformat()
            # Persist BEFORE the request. Failed/uncertain requests consume local allowance.
            await self.store.async_save(self.state)
            return {**result, "allowed": True, "reason": "reserved",
                    "budget_used": a["used"], "product_used": g["used"]}

    async def save_cache(self, s, data):
        async with self.lock:
            await self._load()
            a = self.state.setdefault(account_id(s["api_key"].strip()), {})
            a.setdefault("cache", {})[query_id(s)] = data
            await self.store.async_save(self.state)

    async def cache(self, s):
        async with self.lock:
            await self._load()
            return self.state.get(account_id(s.get("api_key", "").strip()), {}).get("cache", {}).get(query_id(s), {})
