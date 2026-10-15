# PriceGauge 0.3.5

A GUI-first Home Assistant price tracker with collapsible product cards, product-level current average/minimum/maximum, retailer current prices, historical charts, seller discovery and direct-store resolution.

## Retailer compatibility

Normal requests use a persistent cookie session with browser-compatible headers. If a retailer returns recognizable `Client Challenge` HTML with HTTP 200, PriceGauge retries that page once with a simpler compatibility request profile similar to earlier releases. Challenge HTML is never offered in the click-to-select price preview. PriceGauge does not execute, solve or bypass retailer challenge scripts. If both normal profiles are rejected, the retailer is reported as unavailable.

## GUI

The panel uses Home Assistant theme colors and now has a compact navigation header, responsive product summary cards, clearer actions, polished forms, seller rows, strict-match discovery cards and color-matched chart legends. The panel remains accessible to authenticated non-admin Home Assistant users.

Keep `price_monitor: {}` at the top level of `configuration.yaml`. No manual PriceGauge `panel_custom` entry is needed.

## Diagnostics

Enable verbose backend logging with:

```yaml
logger:
  logs:
    custom_components.price_monitor: debug
```

Tests are mocked/synthetic; validate the release on your Home Assistant instance and target retailers.
