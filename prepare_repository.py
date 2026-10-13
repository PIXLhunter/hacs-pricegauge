"""Set real GitHub owner and repository before publishing."""
import json
import re
import sys
from pathlib import Path
if len(sys.argv) not in (2, 3) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}",sys.argv[1]):
    raise SystemExit("Usage: python prepare_repository.py GITHUB_USERNAME [REPOSITORY_NAME]")
repo = sys.argv[2] if len(sys.argv)==3 else "ha-price-monitor"
if not re.fullmatch(r"[A-Za-z0-9_.-]+",repo): raise SystemExit("Invalid repository name")
p=Path(__file__).parent/"custom_components/price_monitor/manifest.json"
d=json.loads(p.read_text())
d.update(documentation=f"https://github.com/{sys.argv[1]}/{repo}",
         issue_tracker=f"https://github.com/{sys.argv[1]}/{repo}/issues",codeowners=["@"+sys.argv[1]])
p.write_text(json.dumps(d,indent=2)+"\n")
print("Manifest configured. Run python tools/check_release.py before upload.")
