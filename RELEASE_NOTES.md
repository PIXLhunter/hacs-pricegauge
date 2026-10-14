# PriceGauge 0.3.2

- Persistent retailer HTTP session now sends ordinary browser-compatible content headers and retains cookies between requests. It does not bypass CAPTCHA/challenge pages.
- Product cards are collapsible and display current-retailer average/minimum/maximum. Retailers show current price only.
- Added per-retailer historical price lines to the expanded product GUI using the stored recent price samples.
- Fixed `undefined shops` by always exposing `summary.retailers` and rendering a singular/plural shop count.
- Seller discovery is stricter: model identifiers and product-defining terms must match; bundles, packs, refurbished/used goods, accessories, Max/Pro/Industrial substitutions for an Ultra product are rejected by identity terms.
- Google Shopping `product_link` values are no longer labelled as retailer URLs. Candidates without a direct non-Google URL are displayed as unavailable for automatic enrollment.
- Authenticated non-admin users can use PriceGauge.
