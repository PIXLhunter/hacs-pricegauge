# PriceGauge 0.3.5

- Refreshed visual design with a cleaner app shell, navigation, product cards, responsive layout, polished forms and seller cards.
- Historical charts keep color-matched legends with clearer range/date context.
- Detects known Client Challenge HTML before it can enter the price picker.
- When a retailer returns a Client Challenge to the browser-shaped server request, PriceGauge retries once with a simpler compatibility request profile. It does not execute or solve challenge JavaScript.
- If both profiles receive the challenge, PriceGauge reports an explicit retailer challenge error.
- Existing direct-store resolver diagnostics and selectable store rows remain intact.
