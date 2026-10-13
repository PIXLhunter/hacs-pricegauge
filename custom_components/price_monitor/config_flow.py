"""No network calls in setup/options validation; initial coordinator fetch does the work."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import DOMAIN
from .client import validate_url
from .budget import query_id

# Common currencies supported by this integration. Deliberately reject arbitrary AAA codes.
CURRENCIES = ["EUR", "USD", "GBP", "CHF", "CAD", "AUD", "NZD", "JPY", "CNY", "INR", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "RON", "BRL", "ZAR", "KRW", "SGD", "HKD", "AED"]

def schema(mode, defaults=None, options=False):
    d = defaults or {}
    f = {}
    if mode == "monitor":
        if not options:
            f[vol.Required("url", default=d.get("url", ""))] = str
        f[vol.Required("currency", default=d.get("currency", "EUR"))] = vol.In(CURRENCIES)
        f[vol.Optional("selector", default=d.get("selector", ""))] = str
        f[vol.Optional("attribute", default=d.get("attribute", ""))] = str
        f[vol.Required("decimal_separator", default=d.get("decimal_separator", "auto"))] = vol.In(["auto", ".", ","])
        f[vol.Optional("target", default=d.get("target", 0))] = vol.All(vol.Coerce(float), vol.Range(min=0))
        f[vol.Required("interval", default=d.get("interval", 60))] = vol.All(vol.Coerce(int), vol.Range(min=15, max=10080))
        f[vol.Optional("ean", default=d.get("ean", ""))] = str
    else:
        if not options:
            f[vol.Optional("query", default=d.get("query", ""))] = str
            f[vol.Optional("ean", default=d.get("ean", ""))] = str
            f[vol.Required("country", default=d.get("country", "nl"))] = vol.All(str, vol.Match(r"^[a-z]{2}$"))
            f[vol.Required("language", default=d.get("language", "en"))] = str
        f[vol.Optional("api_key", default=d.get("api_key", ""))] = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))
        f[vol.Required("monthly_budget", default=d.get("monthly_budget", 250))] = vol.All(vol.Coerce(int), vol.Range(min=0, max=100000))
        f[vol.Required("reserve", default=d.get("reserve", 25))] = vol.All(vol.Coerce(int), vol.Range(min=0, max=100000))
        f[vol.Required("reset_day", default=d.get("reset_day", 1))] = vol.All(vol.Coerce(int), vol.Range(min=1, max=31))
        f[vol.Required("checks_per_month", default=d.get("checks_per_month", 4))] = vol.All(vol.Coerce(int), vol.Range(min=0, max=100000))
    return vol.Schema(f)

def validate(s):
    import math
    ean = s.get("ean", "").strip()
    if ean:
        if not ean.isdigit() or len(ean) not in (8, 12, 13, 14):
            raise ValueError("Invalid GTIN")
        digits = [int(c) for c in ean]
        total = sum(n*(3 if i%2 == 0 else 1) for i,n in enumerate(reversed(digits[:-1])))
        if (10-total%10)%10 != digits[-1]:
            raise ValueError("Invalid GTIN checksum")
    if s["mode"] == "monitor":
        validate_url(s["url"])
        if not math.isfinite(s.get("target", 0)):
            raise ValueError("Invalid target")
    elif not (ean or s.get("query", "").strip()):
        raise ValueError("Enter name or EAN")
    elif s.get("reserve", 25) > s.get("monthly_budget", 250):
        raise ValueError("Reserve exceeds budget")

class PriceMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._name = user_input["name"]
            self._mode = user_input["mode"]
            return await self.async_step_details()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("name"): str,
            vol.Required("mode", default="monitor"): vol.In(["monitor", "search"])}))

    async def async_step_details(self, user_input=None):
        errors = {}
        if user_input is not None:
            s = {**user_input, "mode": self._mode}
            try:
                validate(s)
            except ValueError:
                errors["base"] = "invalid_settings"
            else:
                for entry in self._async_current_entries():
                    other = {**entry.data, **entry.options}
                    if other.get("mode") != self._mode:
                        continue
                    duplicate = other.get("url") == s.get("url") if self._mode == "monitor" else query_id(other) == query_id(s)
                    if duplicate:
                        return self.async_abort(reason="already_configured")
                # Entry ID is stable; URLs/queries are checked for duplicates, not used as unique IDs.
                return self.async_create_entry(title=self._name, data=s)
        return self.async_show_form(step_id="details", data_schema=schema(self._mode, user_input), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        if user_input is not None:
            entry = self._get_reauth_entry()
            if not user_input["api_key"].strip():
                return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({vol.Required("api_key"): str}), errors={"base": "invalid_settings"})
            # Key is tested by the next quota-controlled discovery, not by an extra validation request.
            self.hass.config_entries.async_update_entry(entry, options={**entry.options, "api_key": user_input["api_key"].strip()})
            # Options update listener schedules the reload once.
            return self.async_abort(reason="reauth_successful")
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({
            vol.Required("api_key"): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PriceMonitorOptionsFlow()

class PriceMonitorOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        mode = self.config_entry.data["mode"]
        defaults = {**self.config_entry.data, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            try:
                validate({**defaults, **user_input})
            except ValueError:
                errors["base"] = "invalid_settings"
            else:
                return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=schema(mode, {**defaults, **(user_input or {})}, options=True), errors=errors)
