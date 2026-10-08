"""
Workshop configuration loader.

Precedence (highest wins):
    1. Environment variables / local ``.env`` file at the repo root
       (KEY in UPPER_CASE == app_config key in lower_case)
    2. Generic defaults in ``infrastructure/cdk.json`` -> context.app_config.<env>

This keeps ``cdk.json`` generic (safe to share for ANY customer) while every
customer-specific value lives in the git-ignored ``.env`` file.
"""

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CUSTOMERS_DIR = REPO_ROOT / "customers"


def load_dotenv_file(env_file: Path = REPO_ROOT / ".env") -> dict:
    """Minimal .env parser (KEY=VALUE, '#' comments, optional quotes)."""
    values = {}
    if not env_file.exists():
        return values
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_app_config(cdk_app_config: dict) -> dict:
    """Merge generic cdk.json defaults with .env / environment overrides."""
    dotenv_values = load_dotenv_file()
    resolved = dict(cdk_app_config)
    for key in cdk_app_config:
        env_key = key.upper()
        override = os.environ.get(env_key, dotenv_values.get(env_key))
        if override not in (None, ""):
            resolved[key] = override

    prefix = resolved["resource_prefix"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,30}", prefix):
        raise ValueError(
            f"RESOURCE_PREFIX '{prefix}' must be 3-31 chars: lowercase letters, digits, hyphens."
        )

    customer_dir = CUSTOMERS_DIR / resolved["customer_id"]
    if not customer_dir.is_dir():
        raise ValueError(
            f"Customer pack '{customer_dir}' not found. Create it (see docs/customization.md)."
        )
    resolved["customer_dir"] = str(customer_dir)
    resolved["deploy_frontend"] = str(resolved.get("deploy_frontend", "true")).lower() == "true"
    return resolved
