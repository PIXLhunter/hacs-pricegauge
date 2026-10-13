import ast,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for p in root.rglob('*.py'):ast.parse(p.read_text())
for p in root.rglob('*.json'):json.loads(p.read_text())
comp=root/'custom_components/price_monitor'
manifest=json.loads((comp/'manifest.json').read_text())
assert manifest['version']=='0.3.0'
assert manifest['codeowners']==['@PIXLhunter']
assert manifest['documentation']=='https://github.com/PIXLhunter/hacs-pricegauge'
for n in ('__init__.py','api.py','manager.py','network.py','parser.py','sensor.py','config_flow.py','frontend/panel.js','brand/icon.png'):
    assert (comp/n).is_file(),n
assert len(list((root/'custom_components').iterdir()))==1
print('Offline release preflight passed; live HA/HACS validation remains outstanding')
