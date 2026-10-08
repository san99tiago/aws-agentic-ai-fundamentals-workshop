# %% [markdown]
# # 🦸 Módulo 09 - El agente completo: Runtime + Gateway + RAG + Guardrails
#
# **Objetivo:** integrar TODO lo aprendido en un agente de nivel productivo.
#
# ⏱️ Duración: 10 minutos
#
# ```mermaid
# flowchart LR
#     U["👤 Cliente"] -->|SigV4 / JWT| RT
#     subgraph RT["🚀 AgentCore Runtime - Strands v09"]
#         GI["🛡️ ApplyGuardrail<br/>INPUT"] --> AG["🧠 Agent loop"] --> GO["🛡️ ApplyGuardrail<br/>OUTPUT"]
#     end
#     AG -->|"MCP (SigV4)"| GW
#     subgraph GW["🌐 AgentCore Gateway"]
#         T1["🔎 Web Search"]
#         T2["🏦 API bancaria<br/>API GW + Lambda"]
#         T3["📚 Managed Knowledge Base<br/>(Retrieve)"]
#     end
#     AG --> M["Claude Sonnet (DEFAULT_MODEL_ID)"]
#     RT --> OBS["📈 Observabilidad"]
# ```
#
# **La evolución completa:**
# 🥚 → 🐣 LLM → 🧠 multi-modelo → 🛡️ Guardrails → 📚 RAG → 🤖 Harness → 🌐 Web → 🚀 Runtime → 🏦 APIs → 🦸 **¡Todo integrado!**

# %%
import json
import sys
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop" / "common").exists())
sys.path.insert(0, str(ROOT / "workshop" / "common"))

import runtime_deployer
import workshop_kit as kit

kit.banner(9)
control = kit.client("bedrock-agentcore-control")
pack = kit.customer()
GATEWAY_ID = kit.require_state("gateway_id", "06")
GATEWAY_URL = kit.require_state("gateway_url", "06")
KB_ID = kit.require_state("kb_id", "04")
GUARDRAIL_ID = kit.require_state("guardrail_id", "03")
GUARDRAIL_VERSION = kit.require_state("guardrail_version", "03")

# %% [markdown]
# ## Paso 1: La Knowledge Base como herramienta MCP del Gateway 📚🔌
# Target tipo **connector** `bedrock-knowledge-bases` (solo para Managed KB).
# - `parameterValues`: lo fija el administrador (el ID de la KB, el agente NO lo ve).
# - `parameterOverrides`: qué campos SÍ puede llenar el agente (la consulta y cuántos resultados).

# %%
kb_target_configuration = {
    "mcp": {
        "connector": {
            "source": {"connectorId": "bedrock-knowledge-bases"},
            "configurations": [
                {
                    "name": "Retrieve",
                    "description": pack["knowledge_base_description"],
                    "parameterValues": {
                        "knowledgeBaseId": KB_ID,
                        "retrievalConfiguration": {"managedSearchConfiguration": {"numberOfResults": 4}},
                    },
                    "parameterOverrides": [
                        {"path": "$.retrievalQuery.text", "description": "Pregunta o palabras clave a buscar en la base de conocimiento.", "visible": True},
                        {"path": "$.retrievalConfiguration.managedSearchConfiguration.numberOfResults", "description": "Numero de resultados (1-10).", "visible": True},
                    ],
                }
            ],
        }
    }
}

targets = control.list_gateway_targets(gatewayIdentifier=GATEWAY_ID)["items"]
match = next((t for t in targets if t["name"] == "knowledge-base"), None)
kwargs = dict(
    gatewayIdentifier=GATEWAY_ID,
    name="knowledge-base",
    description="Managed Knowledge Base con FAQs del banco",
    targetConfiguration=kb_target_configuration,
    credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
)
target_id = control.update_gateway_target(targetId=match["targetId"], **kwargs)["targetId"] if match else control.create_gateway_target(**kwargs)["targetId"]
kit.wait_for(
    lambda: control.get_gateway_target(gatewayIdentifier=GATEWAY_ID, targetId=target_id)["status"],
    ("READY",), ("FAILED", "UPDATE_UNSUCCESSFUL"), "Target knowledge-base", every=5,
)
kit.save_state(kb_target_id=target_id)

# %% [markdown]
# ## Paso 2: Todas las herramientas del agente en UN endpoint MCP 🧰

# %%
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands.tools.mcp import MCPClient

with MCPClient(lambda: aws_iam_streamablehttp_client(GATEWAY_URL, aws_service="bedrock-agentcore", aws_region=kit.region())) as mcp:
    for t in mcp.list_tools_sync():
        print(f"🔧 {t.tool_name}")

# %% [markdown]
# ## Paso 3: Desplegar el agente final v09 (con Guardrails) 🦸
# Patrón: el guardrail es una **capa independiente** (`ApplyGuardrail`) que revisa la entrada del
# usuario ANTES del agente y la respuesta final DESPUÉS. Así los documentos de la KB o los JSON de
# las APIs (resultados de herramientas) no se confunden con la intención del usuario.

# %%
runtime = runtime_deployer.deploy(
    ROOT / "workshop" / "09_runtime_gateway_rag" / "agent" / "agent_v09.py",
    kit.name("agent", sep="_"),
    {
        "AGENT_NAME": kit.agent_name(),
        "MODEL_ID": kit.config()["default_model_id"],
        "SYSTEM_PROMPT": pack["agent_persona"],
        "GATEWAY_URL": GATEWAY_URL,
        "GUARDRAIL_ID": GUARDRAIL_ID,
        "GUARDRAIL_VERSION": GUARDRAIL_VERSION,
    },
    description=f"{kit.agent_name()} v09 - Runtime + Gateway (API, Web, KB) + Guardrails",
)
kit.save_state(runtime_arn=runtime["arn"], runtime_id=runtime["id"])
print(f"🚀 Versión desplegada: {runtime['version']}")

# %% [markdown]
# ## Paso 4: La pregunta final 🏆 (API + RAG + Web en una sola respuesta)

# %%
SESSION_ID = kit.new_session_id()


def ask(question: str, session_id: str = SESSION_ID) -> dict:
    answer = runtime_deployer.invoke(runtime["arn"], question, session_id)
    print(f"\n👤 {question}")
    kit.show(kit.agent_name(), answer.get("result", json.dumps(answer)), "🦸")
    print(f"🔧 Herramientas: {answer.get('tools_used')} | stop: {answer.get('stop_reason')} | 🛡️ {answer.get('guardrail')}")
    return answer


ask(pack["examples"]["m09_final"])

# %% [markdown]
# ## Paso 5: RAG vía Gateway 📚

# %%
ask(pack["examples"]["m04_rag"][2])

# %% [markdown]
# ## Paso 6: ¿Y la seguridad? 🛡️ Los ataques siguen bloqueados en producción

# %%
for attack in pack["examples"]["m03_attacks"][:3]:
    ask(attack, session_id=kit.new_session_id())

# %% [markdown]
# ## 🎓 ¡Felicitaciones!
# Construiste un agente con: modelo fundacional, Guardrails, RAG gestionado, herramientas MCP
# gobernadas (APIs + web), código propio en Strands y despliegue serverless aislado por sesión.
#
# **Siguientes pasos para producción:** AgentCore Identity (OAuth / JWT de usuario final),
# AgentCore Policy (Cedar sobre tools del Gateway), AgentCore Memory, Evaluations,
# VPC + PrivateLink y CI/CD con CDK.
#
# 🧹 Al terminar ejecuta `99_cleanup` para eliminar lo que creaste.

# %%
kit.level_up(9)
