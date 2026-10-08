# %% [markdown]
# # 🧹 Módulo 99 - Limpieza
#
# Elimina los recursos de IA que creaste en los notebooks (Runtime, Harness, Gateway,
# Knowledge Base y Guardrail). La infraestructura base (CDK) se elimina con:
# `make destroy` (o `cd infrastructure && cdk destroy --all`).
#
# Para solo VER qué se eliminaría, define `DRY_RUN=true` como variable de entorno.

# %%
import os
import sys
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop" / "common").exists())
sys.path.insert(0, str(ROOT / "workshop" / "common"))

import workshop_kit as kit

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
control = kit.client("bedrock-agentcore-control")
bedrock = kit.client("bedrock")
agent_ctl = kit.client("bedrock-agent")
state = kit.load_state()
print(f"{'🔎 DRY RUN' if DRY_RUN else '🧹 Eliminando'} recursos de: {kit.config()['resource_prefix']}")


def step(label: str, func, *args, **kwargs) -> None:
    if DRY_RUN:
        print(f"   [dry-run] {label}")
        return
    try:
        func(*args, **kwargs)
        print(f"   ✅ {label}")
    except Exception as exc:  # noqa: BLE001 - keep cleaning even if one resource is already gone
        print(f"   ⚠️ {label}: {exc}")


# %% [markdown]
# ## 1. AgentCore Runtime (módulos 07-09)

# %%
if state.get("runtime_id"):
    step(f"Runtime {state['runtime_id']}", control.delete_agent_runtime, agentRuntimeId=state["runtime_id"])

# %% [markdown]
# ## 2. AgentCore Harness (módulos 05-06)

# %%
if state.get("harness_id"):
    step(f"Harness {state['harness_id']}", control.delete_harness, harnessId=state["harness_id"])

# %% [markdown]
# ## 3. AgentCore Gateway + targets (módulos 06, 08, 09)

# %%
if state.get("gateway_id"):
    gateway_id = state["gateway_id"]
    try:
        targets = control.list_gateway_targets(gatewayIdentifier=gateway_id)["items"]
    except control.exceptions.ResourceNotFoundException:
        targets = []
    for target in targets:
        step(f"Gateway target {target['name']}", control.delete_gateway_target, gatewayIdentifier=gateway_id, targetId=target["targetId"])
    if not DRY_RUN and targets:
        kit.wait_for(lambda: str(len(control.list_gateway_targets(gatewayIdentifier=gateway_id)["items"])), ("0",), label="Targets restantes", every=5)
    step(f"Gateway {gateway_id}", control.delete_gateway, gatewayIdentifier=gateway_id)

# %% [markdown]
# ## 4. Knowledge Base (módulo 04)

# %%
if state.get("kb_id"):
    if state.get("kb_data_source_id"):
        step(f"Data source {state['kb_data_source_id']}", agent_ctl.delete_data_source, knowledgeBaseId=state["kb_id"], dataSourceId=state["kb_data_source_id"])
    step(f"Knowledge Base {state['kb_id']}", agent_ctl.delete_knowledge_base, knowledgeBaseId=state["kb_id"])

# %% [markdown]
# ## 5. Guardrail (módulo 03)

# %%
if state.get("guardrail_id"):
    step(f"Guardrail {state['guardrail_id']}", bedrock.delete_guardrail, guardrailIdentifier=state["guardrail_id"])

# %%
if not DRY_RUN:
    kit.STATE_FILE.unlink(missing_ok=True)
    print("\n🧽 Estado local eliminado. ¡Gracias por participar! Para borrar la base: make destroy")
