# PriceGauge 0.3.8

- Fixes false `identifier_mismatch` errors in direct-store resolution.
- Strict product matching remains on the original Google Shopping candidate. Once that candidate provides a `product_id` or `page_token`, the Google Product API response is tied to that identifier and a differently formatted resolved title is diagnostic rather than a second hard rejection.
- Successful Product API results, including zero-store results, are cached locally for one hour so repeated clicks do not repeatedly consume PriceGauge's local request allowance for the same SerpApi query.
- Resolver logs retain the resolved-title check as a warning for diagnostics.
