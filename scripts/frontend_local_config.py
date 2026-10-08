"""Write frontend/public/config.json from cdk.json + .env (local `npm run dev` only)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infrastructure"))

from helpers.config import resolve_app_config  # noqa: E402
from stacks.frontend_stack import PUBLIC_CONFIG_KEYS  # noqa: E402

cdk_json = json.loads((ROOT / "infrastructure" / "cdk.json").read_text())
cfg = resolve_app_config(cdk_json["context"]["app_config"]["dev"])
out = ROOT / "frontend" / "public" / "config.json"
out.write_text(json.dumps({k: cfg.get(k, "") for k in PUBLIC_CONFIG_KEYS}, indent=2, ensure_ascii=False))
print(f"✅ {out.relative_to(ROOT)} generated for {cfg['customer_name']}")
