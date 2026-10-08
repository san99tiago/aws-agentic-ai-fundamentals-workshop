# %% [markdown]
# # 🚀 Módulo 07 - Strands Agents + Amazon Bedrock AgentCore Runtime
#
# **Objetivo:** escribir NUESTRO propio agente con **Strands Agents** (open source de AWS),
# probarlo localmente y desplegarlo en **AgentCore Runtime** (serverless, una microVM por sesión).
#
# ⏱️ Duración: 15 minutos
#
# ```mermaid
# flowchart LR
#     subgraph DEV["💻 Tu IDE"]
#         CODE["agent_v07.py<br/>Strands Agent + @tool"] --> LOCAL["🧪 Prueba local"]
#         CODE --> ZIP["🗜️ zip ARM64<br/>(sin Docker)"]
#     end
#     ZIP --> S3["S3 artifacts"] --> RT
#     subgraph RT["🚀 AgentCore Runtime"]
#         S1["microVM sesión A"]
#         S2["microVM sesión B"]
#     end
#     U["👤 InvokeAgentRuntime<br/>(SigV4)"] --> RT
#     RT --> BR["🧠 Bedrock (Claude)"]
#     RT --> OBS["📈 CloudWatch GenAI Observability<br/>(OpenTelemetry)"]
# ```
#
# **Anatomía de un agente (Strands):** `Agent(model, system_prompt, tools)` ✨
# El ciclo *razonar → herramienta → observar* lo ejecuta Strands. Tú decides todo lo demás.

# %%
import json
import sys
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop" / "common").exists())
sys.path.insert(0, str(ROOT / "workshop" / "common"))

import runtime_deployer
import workshop_kit as kit

kit.banner(7)
pack = kit.customer()
AGENT_FILE = ROOT / "workshop" / "07_runtime_strands" / "agent" / "agent_v07.py"
RUNTIME_NAME = kit.name("agent", sep="_")
ENV_VARS = {
    "AGENT_NAME": kit.agent_name(),
    "MODEL_ID": kit.config()["default_model_id"],
    "SYSTEM_PROMPT": pack["agent_persona"],
}

# %% [markdown]
# ## Paso 1: Mira el código del agente 👀
# Abre `agent/agent_v07.py`: dos herramientas Python (`@tool`) + un `Agent` de Strands +
# el wrapper `BedrockAgentCoreApp` que expone `/invocations` y `/ping`.

# %%
print(AGENT_FILE.read_text()[:2500])

# %% [markdown]
# ## Paso 2: Prueba LOCAL (antes de desplegar) 🧪
# Mismo código, corriendo en tu máquina con tus credenciales.

# %%
import os
import importlib.util

os.environ.update(ENV_VARS)
spec = importlib.util.spec_from_file_location("agent_v07", AGENT_FILE)
agent_v07 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent_v07)

local_agent = agent_v07.build_agent()
local_result = local_agent(pack["examples"]["m07_runtime"])
print(f"🤖 {local_result}\n\n🔧 Herramientas usadas: {list(local_result.metrics.tool_metrics.keys())}")

# %% [markdown]
# ## Paso 3: Desplegar en AgentCore Runtime (direct code deploy) 🚀
# Empaquetamos dependencias Linux ARM64 + el agente en un zip, lo subimos a S3 y creamos el Runtime.
# La primera vez tarda ~2-3 minutos.

# %%
runtime = runtime_deployer.deploy(
    AGENT_FILE, RUNTIME_NAME, ENV_VARS, description=f"{kit.agent_name()} v07 - Strands + tools locales"
)
kit.save_state(runtime_arn=runtime["arn"], runtime_id=runtime["id"])
print(f"🚀 Runtime listo: {runtime['arn']} (versión {runtime['version']})")

# %% [markdown]
# ## Paso 4: Invocar el agente en la nube ☁️

# %%
SESSION_ID = kit.new_session_id()
answer = runtime_deployer.invoke(runtime["arn"], pack["examples"]["m07_runtime"], SESSION_ID)
kit.show(kit.agent_name(), answer.get("result", json.dumps(answer)), "🚀")
print("🔧 Herramientas:", answer.get("tools_used"), "| 🪙", answer.get("usage"))

# %% [markdown]
# ## Paso 5: Multi-turno en la misma sesión (misma microVM = mismo agente en memoria)

# %%
answer = runtime_deployer.invoke(runtime["arn"], "Y si lo pago en 60 meses en vez de 36, cuanto mas pago de intereses en total?", SESSION_ID)
kit.show(kit.agent_name(), answer.get("result", json.dumps(answer)), "🚀")

# %% [markdown]
# ## Paso 6: Observabilidad 📈
# Abre la consola: **CloudWatch → GenAI Observability → Bedrock AgentCore** para ver trazas,
# spans de cada llamada al modelo y a las herramientas, latencias y tokens.
# (Requiere habilitar una sola vez *Transaction Search* en CloudWatch X-Ray).

# %%
print(f"🔗 https://{kit.region()}.console.aws.amazon.com/cloudwatch/home?region={kit.region()}#/gen-ai-observability/agent-core")
print(f"🪵 Logs: /aws/bedrock-agentcore/runtimes/{runtime['id']}-DEFAULT")

# %%
kit.level_up(7)
