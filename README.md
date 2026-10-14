# PriceGauge for Home Assistant

Version **0.3.1**. GUI-first price tracking for Home Assistant.

## 0.3.1 behavior

Products are collapsed by default. Each product summary shows the arithmetic average, minimum and maximum of the **current successful retailer prices**. Expanding a product shows each retailer's **current price only**, plus website management and seller discovery. Failed retailer readings are excluded from product aggregates until that retailer produces a successful current value.

Retailer sensors expose current price. Product sensors expose current average, minimum and maximum. Old 0.3.0 retailer average/minimum entities are no longer created and may remain as unavailable historical registry entries until removed manually.

The PriceGauge panel is available to authenticated non-admin Home Assistant users. The GUI command no longer uses the incompatible `connection.require_admin()` call. Anyone with access to the Home Assistant instance and PriceGauge panel can add/remove products, change settings, and enter/replace the SerpApi key.

Shopping discovery is deliberately conservative: exact model-like identifiers from the tracked product title are required in candidates, obvious English/Dutch accessory terms are rejected, significant product-name token coverage and title similarity thresholds are applied, then accepted candidates are ranked by similarity. If an EAN is available, the Shopping query contains both the EAN and product name. This reduces false positives but can also reject valid retailers with abbreviated titles. Discovery is still candidate generation, not proof of product identity. The retailer page must pass price validation before tracking.

## Initialization

Keep `price_monitor: {}` at the top level of `configuration.yaml`. The integration registers PriceGauge in the sidebar automatically; do not keep the old manual `price-monitor-panel` `panel_custom` entry. Restart Home Assistant after a HACS upgrade and hard refresh the browser.

## SerpApi budget

Retailer price polling never consumes SerpApi quota. Seller discovery uses the persisted shared budget configured in GUI Settings: monthly budget, reserve, per-product cap and reset day. One eligible discovery makes one Shopping request; no pagination/detail calls are performed.

## Static inspection limitation

Price selection works against sanitized static HTML downloaded by Home Assistant. JavaScript-only prices, bot-blocked pages, CAPTCHAs and signed-in pages remain unsupported. A Shopping result can be an aggregator URL rather than an actual retailer product page; use the actual retailer URL before tracking.

## Logging

The Logs tab shows structured PriceGauge events. For verbose Home Assistant logs, merge this into your existing configuration:

```yaml
logger:
  logs:
    custom_components.price_monitor: debug
```

## Validation

```text
python -m pip install -r requirements-dev.txt
python tools/check_release.py
python -m unittest discover -s tests -v
node --check custom_components/price_monitor/frontend/panel.js
node tests/frontend_smoke.cjs
```

The included tests are synthetic/mocked. Test the release on your Home Assistant instance before relying on it.
