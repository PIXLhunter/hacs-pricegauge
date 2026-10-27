# PriceGauge 0.3.7

- Adds durable market reports in a Reports tab. A report is refreshed after the configurable interval (default 3 days), or sooner when a product minimum moves by the configurable major-change threshold (default 10%).
- Reports preserve product min/average/max, shop count, store snapshots and minimum percentage change versus the previous report; the last 50 reports are retained.
- Adds package normalization: webshop pack count plus optional millilitres per item. Products can compare in `/item` or `/100 ml`.
- A 3-pack priced at EUR 12 compares as EUR 4/item. A 3 x 50 ml pack priced at EUR 12 compares as EUR 8/100 ml.
- Product cards, reports, target-price alerts and graph values use normalized comparison prices. Retailer rows continue to show the raw pack price as well.
- Keeps 0.3.6 phone notifications and the HORNBACH Client Challenge compatibility retry.
