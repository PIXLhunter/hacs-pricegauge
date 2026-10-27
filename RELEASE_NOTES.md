# PriceGauge 0.3.9

- Shows the running PriceGauge software version as a small note in the top-right header.
- Adds the software version to every PriceGauge structured log entry.
- Home Assistant backend log messages are also prefixed with the running PriceGauge version.
- Older persisted log entries without a stored version are displayed using the current running version fallback in the GUI.
