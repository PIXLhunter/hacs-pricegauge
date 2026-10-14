# PriceGauge 0.3.4

Home Assistant GUI-first product price tracking. Products are collapsible; retailer rows show current prices, while product summaries expose current-retailer average, minimum and maximum. Expanded products include per-retailer history plots with colored legends.

Seller discovery uses strict Shopping-title matching. Google Shopping candidates can be resolved on demand through SerpApi's Google Product API. One locally budgeted request is reserved before an uncached lookup. Direct retailer offers are read from the exact resolved product's store list and can then be selected independently in the GUI. Successful non-empty results are cached. Empty results are retryable.

The PriceGauge panel is available to authenticated Home Assistant users, including non-admin users. Keep `price_monitor: {}` at the top level of `configuration.yaml`; no manual PriceGauge `panel_custom` entry is needed.

For verbose backend logs:

```yaml
logger:
  logs:
    custom_components.price_monitor: debug
```

Tests are mocked/synthetic. Validate on your Home Assistant instance before relying on a new release.
