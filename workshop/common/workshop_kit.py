"""
workshop_kit - shared helpers for every workshop module.

* Loads the SAME parameters used by CDK: generic defaults from
  infrastructure/cdk.json overridden by the local .env file.
* Loads the customer pack (customers/<CUSTOMER_ID>/customer.json).
* Reads the outputs of the foundation stack (buckets, roles, banking API).
* Persists the IDs of the resources you create in workshop/.state.json so the
  next module can reuse them (and 99_cleanup can delete them).
* Small pretty-print helpers so outputs look fun in Jupyter and terminals.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import boto3
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "workshop" / ".state.json"
BOTO_CONFIG = Config(retries={"max_attempts": 6, "mode": "adaptive"}, read_timeout=900, connect_timeout=30)

# ----------------------------------------------------------------------------
# The agent EVOLVES in every module (fun gamification for participants)
# ----------------------------------------------------------------------------
LEVELS = {
    0: ("🥚", "Huevo", "Preparando el entorno"),
    1: ("🐣", "Bebé", "Aprende a hablar: LLM input/output con Amazon Bedrock"),
    2: ("🧠", "Explorador", "Compara cerebros: OpenAI vs Claude en Bedrock"),
    3: ("🛡️", "Guardián", "Se protege con Amazon Bedrock Guardrails"),
    4: ("📚", "Sabio", "Aprende de documentos con RAG (Knowledge Bases)"),
    5: ("🤖", "Autónomo", "Agente gestionado con AgentCore Harness"),
    6: ("🌐", "Conectado", "Busca en la web con AgentCore Gateway (MCP)"),
    7: ("🚀", "Productivo", "Código propio con Strands en AgentCore Runtime"),
    8: ("🏦", "Banquero", "Usa APIs del banco vía Gateway (API GW + Lambda)"),
    9: ("🦸", "Leyenda", "Runtime + Gateway + RAG + Guardrails integrados"),
}


# ----------------------------------------------------------------------------
# Configuration (cdk.json defaults  <  .env  <  environment variables)
# ----------------------------------------------------------------------------
def _read_dotenv() -> dict:
    values = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@lru_cache(maxsize=1)
def config() -> dict:
    cdk_json = json.loads((ROOT / "infrastructure" / "cdk.json").read_text(encoding="utf-8"))
    env_name = os.environ.get("DEPLOYMENT_ENVIRONMENT", _read_dotenv().get("DEPLOYMENT_ENVIRONMENT", "dev"))
    defaults = cdk_json["context"]["app_config"][env_name]
    dotenv = _read_dotenv()
    cfg = {k: os.environ.get(k.upper(), dotenv.get(k.upper(), v)) or v for k, v in defaults.items()}
    cfg["stack_name"] = f"{cfg['resource_prefix']}-foundation-{cfg['deployment_environment']}"
    return cfg


@lru_cache(maxsize=1)
def customer() -> dict:
    """Customer pack with {agent_name}/{customer_brand}/{customer_name} placeholders resolved."""
    cfg = config()
    raw = (ROOT / "customers" / cfg["customer_id"] / "customer.json").read_text(encoding="utf-8")
    for key in ("agent_name", "customer_brand", "customer_name"):
        raw = raw.replace("{" + key + "}", cfg[key])
    return json.loads(raw)


def agent_name() -> str:
    return config()["agent_name"]


def region() -> str:
    return config()["aws_region"]


def client(service: str):
    return boto3.client(service, region_name=region(), config=BOTO_CONFIG)


def account_id() -> str:
    return client("sts").get_caller_identity()["Account"]


def name(kind: str, sep: str = "-") -> str:
    """Deterministic resource names, e.g. name('guardrail') -> 'acme-agentic-guardrail'."""
    base = f"{config()['resource_prefix']}{sep}{kind}"
    return base.replace("-", "_") if sep == "_" else base


@lru_cache(maxsize=1)
def outputs() -> dict:
    """Outputs of the foundation stack deployed with CDK."""
    stack = client("cloudformation").describe_stacks(StackName=config()["stack_name"])["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}


# ----------------------------------------------------------------------------
# State shared between modules
# ----------------------------------------------------------------------------
def load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def save_state(**values: Any) -> dict:
    state = load_state()
    state.update(values)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    return state


def require_state(key: str, module_hint: str) -> Any:
    value = load_state().get(key)
    if not value:
        raise RuntimeError(f"'{key}' not found in {STATE_FILE.name}. Run module {module_hint} first.")
    return value


def new_session_id() -> str:
    """AgentCore session ids must be >= 33 chars (a UUID with hyphens is 36)."""
    return str(uuid.uuid4())


def wait_for(fetch: Callable[[], str], ready: tuple, failed: tuple = (), label: str = "", timeout: int = 900, every: int = 10) -> str:
    start = time.time()
    status = ""
    while time.time() - start < timeout:
        status = fetch()
        print(f"   ⏳ {label}: {status} ({int(time.time() - start)}s)")
        if status in ready:
            return status
        if status in failed:
            raise RuntimeError(f"{label} ended in status {status}")
        time.sleep(every)
    raise TimeoutError(f"{label} still {status} after {timeout}s")


# ----------------------------------------------------------------------------
# Pretty printing
# ----------------------------------------------------------------------------
def banner(level: int) -> None:
    emoji, title, desc = LEVELS[level]
    line = "═" * 70
    print(f"{line}\n  {emoji}  {agent_name()} v{level} - {title}\n  {desc}\n  Cliente: {config()['customer_name']} | Región: {region()}\n{line}")


def section(title: str) -> None:
    print(f"\n── {title} " + "─" * max(4, 66 - len(title)))


def show(label: str, text: str, emoji: str = "💬") -> None:
    print(f"\n{emoji} {label}:\n{text.strip()}\n")


def converse_text(response: dict) -> str:
    """Extract only the final text from a Converse response (skips reasoning blocks)."""
    blocks = response["output"]["message"]["content"]
    return "\n".join(b["text"] for b in blocks if "text" in b)


def print_stream(stream, show_tools: bool = True) -> dict:
    """Print a Converse-style event stream (InvokeHarness) and return a summary."""
    text, tools, usage, stop = [], [], {}, None
    for event in stream:
        if "contentBlockStart" in event:
            tool = event["contentBlockStart"].get("start", {}).get("toolUse")
            if tool and show_tools:
                tools.append(tool.get("name"))
                print(f"\n   🔧 Herramienta: {tool.get('name')}", flush=True)
        elif "contentBlockDelta" in event:
            delta = event["contentBlockDelta"].get("delta", {})
            if "text" in delta:
                text.append(delta["text"])
                print(delta["text"], end="", flush=True)
        elif "messageStop" in event:
            stop = event["messageStop"].get("stopReason")
        elif "metadata" in event:
            usage = event["metadata"].get("usage", usage)
        else:
            for error_key in ("validationException", "internalServerException", "runtimeClientError"):
                if error_key in event:
                    print(f"\n   ❌ {error_key}: {event[error_key]}")
    print()
    return {"text": "".join(text), "tools": tools, "usage": usage, "stop_reason": stop}


def level_up(level: int) -> None:
    emoji, title, _ = LEVELS[level]
    print(f"\n🎉 ¡{agent_name()} evolucionó a v{level} {emoji} {title}! Siguiente módulo 👉")
