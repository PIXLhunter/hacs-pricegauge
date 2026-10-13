"""Offline repository preflight; does not replace live HA/HACS validation."""
import ast
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
comp=root/"custom_components/price_monitor"
for p in root.rglob("*.py"): ast.parse(p.read_text())
for p in root.rglob("*.json"): json.loads(p.read_text())
d=json.loads((comp/"manifest.json").read_text())
assert d["version"]=="0.2.1"
assert "YOUR_GITHUB_USERNAME" not in json.dumps(d), "Run prepare_repository.py first"
assert d["codeowners"] and d["documentation"].startswith("https://github.com/")
assert (comp/"brand/icon.png").is_file()
for n in ("__init__.py","config_flow.py","coordinator.py","sensor.py","binary_sensor.py","button.py","scraper.py","budget.py","client.py","strings.json","translations/en.json"):
    assert (comp/n).is_file(),n
assert len(list((root/"custom_components").iterdir()))==1
print("Offline release preflight passed")
