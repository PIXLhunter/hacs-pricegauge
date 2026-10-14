# PriceGauge 0.3.1

- Products are collapsed by default; expand a product to manage its retailers.
- Product headline and HA entities expose current-retailer average, minimum and maximum.
- Retailer HA entities expose current price only. Historical retailer samples remain stored internally but are not used for product aggregates.
- Sidebar and GUI WebSocket operations no longer require Home Assistant administrator access. They remain available only through an authenticated Home Assistant session.
- Shopping discovery now rejects obvious accessory results, requires exact model-like identifiers, applies strict title-token similarity, and sorts accepted candidates by similarity. EAN products use EAN plus product name in the search query.
- Removed the obsolete custom_components_0.2.1 backup tree from the repository.

All discovered sellers remain candidates only and must still pass retailer-page price validation.
