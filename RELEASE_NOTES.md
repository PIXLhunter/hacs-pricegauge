# PriceGauge 0.3.4

- Adds visible color-swatch legends to historical price charts.
- Fixes resolved-store checkboxes by rendering stores as independent rows rather than nested labels.
- Product API resolution now validates the resolved product once, then accepts direct store offers belonging to that exact product even when store titles are abbreviated.
- Logs Product API response ID/status, raw store count, acceptance count and rejection reasons.
- Empty Product API results remain retryable; non-empty resolved stores are cached.
- The GUI explicitly notes that SerpApi may serve identical cached searches without charging the monthly search count.
