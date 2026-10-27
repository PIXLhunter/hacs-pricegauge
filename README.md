# PriceGauge 0.4.0

GUI-first Home Assistant price tracking with retailer discovery, normalized pricing, historical charts, market reports and Home Assistant notifications.

## Packs and sizes

Each retailer can specify **Units in this webshop pack** and **Millilitres per unit**. A product comparison mode chooses either **Price per item** or **Price per 100 ml**. Raw retailer pack prices remain visible, while product Min/Avg/Max and the graph are normalized. Example: a pack of 3 tubes costing EUR 12 becomes EUR 4/item. If each tube is 50 ml and the product is set to `/100 ml`, that same pack becomes EUR 8/100 ml. A retailer without an ml value is excluded from `/100 ml` aggregates until its ml value is configured.

## Reports

The new Reports tab stores market snapshots. Defaults are **every 3 days** and **also whenever a normalized product minimum changes by at least 10%** versus the latest report. Both values are configurable in Settings. Reports show Min/Avg/Max, shop count and the minimum percentage change from the prior report. Up to 50 snapshots are retained in PriceGauge storage.

## Notifications

Settings lists modern `notify.*` entities and legacy `notify.mobile_app_*` Home Assistant actions. Configure global percentage-drop notifications or a normalized target price inside an individual product.

## Retailer compatibility

PriceGauge uses a persistent browser-compatible request profile, with one fresh-session simpler compatibility retry when recognizable Client Challenge HTML is returned. Challenge scripts and CAPTCHAs are not executed or bypassed.

Keep `price_monitor: {}` at the top level of Home Assistant `configuration.yaml`. Tests are mocked/synthetic; validate on the actual Home Assistant instance before relying on a release.


## 0.3.8 direct-store fix

Strict identity filtering is applied before a Shopping candidate is offered in the GUI. Direct-store resolution then follows that candidate product_id/page_token. The Product API title is retained as a diagnostic warning but is no longer a second hard identity gate because Google can normalize model punctuation/naming. Successful zero-store Product API responses are cached for one hour to avoid repeated local-budget consumption on repeated clicks.


## Version diagnostics

The currently running PriceGauge version is shown in the top-right of the GUI. New GUI/backend log entries carry the same version so screenshots and downloaded logs identify which code produced an event.


## Notification shortlist

Settings discovers available Home Assistant notification destinations. Select the destinations that belong in the PriceGauge shortlist, for example your phone and a second household phone. Each product card then selects one destination from only that shortlist, or `No notifications`. Product price drops, target alerts and product reports go only to the product-selected destination. Removing a destination from the shortlist clears any product assignment to it.
