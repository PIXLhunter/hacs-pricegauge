# Price Monitor for Home Assistant

Version **0.3.2**. A complete custom integration repository for HACS custom-repository
installation. Target baseline: Home Assistant **2026.7 or newer** (local brand images
and coordinator retry-delay API). This baseline is a declared target, not a tested
minimum. No live Home Assistant installation was available for validation.

## Prepare and publish

1. Extract this ZIP. Its contents belong at the GitHub repository root.
2. Run `python prepare_repository.py YOUR_GITHUB_USERNAME` (optional second argument:
   repository name; default `ha-price-monitor`). Your real owner cannot be inferred.
3. Run `python tools/check_release.py`.
4. Upload the contents to your GitHub repository. Keep `.github`, `custom_components`,
   `hacs.json`, README and license at the root. Do not add an extra enclosing folder.
5. Review the Validate workflow results. Create/push tag `v0.2.0` to run the included
   release workflow, which creates a GitHub release with a `price_monitor.zip` asset.
6. In HACS, open Custom repositories, add your repository URL, choose Integration,
   download Price Monitor and restart Home Assistant.
7. Settings > Devices & services > Add integration > Price Monitor.

The ZIP is a full repository, not an update patch. Publishing a custom repository is
not the same as approval for the HACS default catalog. This package does not publish
anything on your behalf. GitHub Actions workflows are included but have not run here.

## Monitor mode: routine retailer prices

Add one entry per retailer product URL. Default polling: 60 minutes; minimum: 15.
All entities share one HTTP fetch and one HTML parse per entry per poll. Distinct URLs
are independent. Requests to the same hostname are serialized, not globally throttled.

Leave selector empty for Product JSON-LD / price metadata extraction. When automatic
extraction finds multiple distinct prices, configure a CSS selector for the correct
variant. It must match exactly one element. Optional attribute can be `content` for
meta tags. Use browser Inspect to identify a selector, but remember this integration
fetches static HTML only. JavaScript-rendered prices, logged-in sessions and blocked
sites are unsupported. No CAPTCHA or anti-bot bypass is attempted.

Set the currency explicitly. Metadata and CSS modes trust that configured currency.
Automatic JSON-LD offers must match it. Optional EAN/GTIN requires a valid checksum;
automatic mode requires matching Product GTIN. Manual selectors override automatic
extraction and do not verify EAN. Stock is unknown unless structured data identifies it.

`1.299` / `1,299` are ambiguous in auto separator mode. Set the actual decimal separator
for the page. `1.299,99`, `1,299.99`, `129,99` and `129.99` are supported. A wrong selector
can still extract the wrong variant or installment: verify initial readings yourself.

Entities: Price, Lowest observed price, Target reached. Target 0 disables the indicator.
Target reached is price-only, not a stock guarantee. Lowest means lowest observed since
tracking began, not historical market minimum. Recorder history follows your retention.
No measurement state_class is set for monetary entities.

A successful decrease emits `price_monitor_price_drop` after saving its baseline.
First observation does not emit an event. Previous price means previous successful
poll. Failed checks do not store zero and make coordinator entities unavailable.
Retailer HTTP 429 respects a bounded numeric Retry-After delay; date-form headers use
one-hour fallback. See `examples/price_drop.yaml` for notifications.

## Search mode: occasional store discovery

SerpApi is OPTIONAL. Without a key, retailer monitoring works and discovery reports
`no_api_key`. You can add a key later through options. One discovery entry per product;
add any number of preferred retailer monitor entries separately.

Discovery is not routine price checking. It returns cached Shopping candidates with
seller/title/price/link. Results are not guaranteed EAN matches or complete seller
coverage. Links may lead to Google Shopping. Manually verify variant/EAN and add the
actual retailer URL. New stores are never enrolled automatically.

Default policy: 250 account requests per billing cycle, 25 reserved, desired maximum
4 discoveries per product per cycle. Set reserve 0 if all 250 are dedicated to this
integration. Account policies are shared across entries with the same API key; the
most conservative configured budget/reserve wins. Reset day must agree across entries.
Configure it to your account billing day. Boundaries use UTC midnight, not an exact
provider reset timestamp. Other applications' usage is not visible; reserve accordingly.

N = distinct discovery queries for the same key, not retailer URLs. Effective allowance
is budget minus reserve. Each product receives the smaller of its desired cap and a
fair share. Remainders rotate by cycle; if N exceeds allowance, some products receive
zero requests that cycle. Adding/removing products recalculates shares. Account totals
remain capped even after deletion. Counters and cached results persist across restarts.

Four discoveries per cycle are spaced across the actual month length (approximately
weekly). The hourly local eligibility check makes NO API call unless a request is due.
One discovery = one API request and one response parse, with no pagination/detail calls.
Up to 40 returned candidates are cached. Setup/options validation consumes no searches.
Manual Discover stores now bypasses spacing, not product/account caps. Failed/uncertain
requests count conservatively. Generic failures retain cached results. Authentication
failure triggers HA reauthentication; a replacement key is tested at the next eligible
request, not with a separate validation call. Rotating keys creates a separate local
budget; this is not provider-side quota enforcement.

Changing query/country/language requires recreating the entry. Budget, key and monitor
selectors are editable through options. Entry migration preserves entity IDs from 0.1.0.

## Tests and status

`python -m pip install -r requirements-dev.txt`
`python -m unittest discover -s tests -v`

Offline tests cover parsing, quota concurrency, persistence, caching, cycle reset,
mocked coordinator behavior, setup/unload/options reload and migration. These mocks do
NOT prove compatibility with a real HA runtime. No live retailer/SerpApi/HACS test was
performed. The included validation workflow is a further publication check, not a claim
that HACS has accepted this repository. Use a test HA instance before production.

## References

- [HACS integration requirements](https://hacs.xyz/docs/publish/integration/)
- [HACS custom repositories](https://hacs.xyz/docs/faq/custom_repositories/)
- [Home Assistant coordinators](https://developers.home-assistant.io/docs/integration_fetching_data/)
- [SerpApi Shopping API](https://serpapi.com/google-shopping-api)

Respect retailer terms, access restrictions and API quotas. Do not commit API keys.
