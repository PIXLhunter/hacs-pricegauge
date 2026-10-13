# Price Monitor sidebar patch 0.2.1

This is a patch for the full 0.2.0 repository, not a standalone integration.
The original archive is not present in this execution session. Existing parser,
price polling, budget and entities are preserved. No SerpApi requests are added.

1. Extract this patch separately from your full repository.
2. Run `python apply_sidebar.py PATH_TO_REPOSITORY` from the patch folder.
3. Publish the changed repository as 0.2.1 or copy its integration folder to HA.
4. Add the following to Home Assistant configuration.yaml. If panel_custom already
   exists, append this item to its existing list; do not create a duplicate key.

```yaml
panel_custom:
  - name: price-monitor-panel
    sidebar_title: Price Monitor
    sidebar_icon: mdi:tag-outline
    url_path: price-monitor
    module_url: /price_monitor_frontend/price-monitor-panel.js?v=0.2.1
    require_admin: true
```

5. Restart HA and refresh the browser. Open Price Monitor in the left sidebar.
6. Failed retailer entries appear because the API registers during integration
   setup, before any individual product fetch. Open actual website launches a new
   tab, not an embedded browser. The panel cannot inspect a cross-origin browser DOM.
7. Edit selector/attribute/decimal separator, press Test selector, inspect match
   count and previews. A successful test enables Save and retry setup. A changed
   field requires a new test. The test does not alter prices, minima or alert events.
8. Save retains all other options, and retries the failed entry. Refresh overview.

Zero matches: selector absent from downloaded HTML, changed markup, wrong page or
JavaScript-only content. Multiple matches: selector too broad (possibly old price,
variants or recommended products). Select the exact current product price, not
simply the first result. Clearing the selector tests automatic structured extraction.

Each test downloads the retailer page once and parses it once. It does not consume
SerpApi allowance. It uses the existing per-host lock. Test requests do not persist
HTTP 429 backoff; avoid repeatedly testing a rate-limited shop. Previews are text,
not raw HTML; fetched scripts never execute in the HA panel. API keys are not returned.
All panel commands require admin privileges.

No live Home Assistant, browser UI or retailer testing performed. Python and JS
syntax checks plus mocked diagnostic tests are not live compatibility validation.
The existing test suite/preflight should be rerun after applying. Release metadata
must reflect 0.2.1; this patch does not publish your repository or edit old release notes.
