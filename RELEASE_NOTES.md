# Price Monitor 0.2.0

- Complete UI-configurable custom integration, including local brand assets.
- Static retailer HTML prices via Product JSON-LD, metadata or exact CSS selectors.
- Current price, lowest observed price and target reached entities.
- Price-drop events, persistent minimum and unavailable states on failed retailer checks.
- Optional SerpApi discovery, separate from retailer price polling.
- Shared persisted account budget, fair per-product allocation and cached candidates.
- Manual discovery button subject to the same budget caps.
- API-key recovery, entry migration, host serialization and retailer rate-limit backoff.

This is a pre-live-validation release candidate. Offline tests use synthetic HTML and
mocked Home Assistant interfaces. No real Home Assistant lifecycle, live retailer or
SerpApi account test was performed. Run a test-instance installation before production.
