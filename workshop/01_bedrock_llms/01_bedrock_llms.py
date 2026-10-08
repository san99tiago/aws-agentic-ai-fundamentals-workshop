# %% [markdown]
# # 🐣 Módulo 01 - Amazon Bedrock: Input / Output de un LLM
#
# **Objetivo:** entender qué entra y qué sale de un Large Language Model (LLM):
# mensajes, *system prompt*, parámetros de inferencia, tokens, latencia y costo.
#
# ⏱️ Duración: 10 minutos
#
# ```mermaid
# flowchart LR
#     U["👤 Usuario"] -->|"messages[] + system"| C["Converse API<br/>bedrock-runtime"]
#     P["⚙️ inferenceConfig<br/>maxTokens, temperature"] --> C
#     C --> M["🧠 LLM<br/>(Claude, OpenAI, Nova...)"]
#     M -->|"output.message"| R["📤 Respuesta"]
#     M -->|"usage: input/output tokens"| T["🪙 Tokens = $$"]
#     M -->|"metrics.latencyMs"| L["⏱️ Latencia"]
# ```
#
# **Conceptos clave**
# - **Token**: pedazo de texto (~3/4 de palabra). Pagas por tokens de entrada y de salida.
# - **System prompt**: la "personalidad" e instrucciones del agente.
# - **Temperature**: 0 = respuestas más deterministas, 1 = más creativas. (Ojo: algunos modelos
#   de razonamiento recientes, como Claude Sonnet/Opus 5.5, ya no aceptan `temperature`.)
# - **maxTokens**: SIEMPRE defínelo. Si no, reservas cuota de más (y te pueden *throttlear*).
# - **Converse API**: una sola forma de hablar con TODOS los modelos de Bedrock.

# %%
import json
import sys
import time
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop" / "common").exists())
sys.path.insert(0, str(ROOT / "workshop" / "common"))

import workshop_kit as kit

kit.banner(1)
bedrock = kit.client("bedrock-runtime")
MODEL_ID = kit.config()["fast_model_id"]
examples = kit.customer()["examples"]

# %% [markdown]
# ## Paso 1: Tu primera llamada (sin personalidad)

# %%
response = bedrock.converse(
    modelId=MODEL_ID,
    messages=[{"role": "user", "content": [{"text": examples["m01_hello"]}]}],
    inferenceConfig={"maxTokens": 400, "temperature": 0.3},
)
kit.show("Respuesta", kit.converse_text(response))
print("🪙 Uso de tokens:", response["usage"])
print("⏱️ Latencia (ms):", response["metrics"]["latencyMs"])
print("🛑 stopReason:", response["stopReason"])

# %% [markdown]
# ## Paso 2: Anatomía completa de la respuesta
# Mira el JSON crudo: `output.message`, `usage`, `metrics`, `stopReason`.

# %%
print(json.dumps({k: v for k, v in response.items() if k != "ResponseMetadata"}, indent=2, ensure_ascii=False))

# %% [markdown]
# ## Paso 3: Le damos personalidad con un *system prompt*
# Nace el agente: el **system prompt** define quién es, cómo habla y qué NO debe hacer.

# %%
SYSTEM_PROMPT = kit.customer()["agent_persona"]
print("📜 System prompt:\n", SYSTEM_PROMPT)

response = bedrock.converse(
    modelId=MODEL_ID,
    system=[{"text": SYSTEM_PROMPT}],
    messages=[{"role": "user", "content": [{"text": "Hola! Quién eres y en qué me puedes ayudar?"}]}],
    inferenceConfig={"maxTokens": 400, "temperature": 0.5},
)
kit.show(kit.agent_name(), kit.converse_text(response), "🐣")

# %% [markdown]
# ## Paso 4: Conversación multi-turno (el LLM NO tiene memoria)
# El modelo es *stateless*: para "recordar" debes reenviar el historial completo en `messages`.
# (Más adelante AgentCore se encarga de esto por ti 😉)

# %%
history = [
    {"role": "user", "content": [{"text": "Me llamo Camila y quiero ahorrar para un viaje a Cartagena."}]},
]
first = bedrock.converse(modelId=MODEL_ID, system=[{"text": SYSTEM_PROMPT}], messages=history, inferenceConfig={"maxTokens": 300})
history.append(first["output"]["message"])
history.append({"role": "user", "content": [{"text": "Cómo me llamo y para qué quiero ahorrar?"}]})
second = bedrock.converse(modelId=MODEL_ID, system=[{"text": SYSTEM_PROMPT}], messages=history, inferenceConfig={"maxTokens": 300})
kit.show("Turno 2 (con historial)", kit.converse_text(second), "🧠")
print(f"🪙 Tokens de entrada turno 1: {first['usage']['inputTokens']} | turno 2: {second['usage']['inputTokens']} (crece con el historial)")

# %% [markdown]
# ## Paso 5: Salida estructurada (JSON) para integrarse con sistemas
# Los agentes necesitan respuestas que una máquina pueda procesar.

# %%
response = bedrock.converse(
    modelId=MODEL_ID,
    system=[{"text": "Eres un clasificador de solicitudes bancarias. Responde UNICAMENTE con JSON valido, sin markdown."}],
    messages=[{"role": "user", "content": [{"text": examples["m01_structured"]}]}],
    inferenceConfig={"maxTokens": 200, "temperature": 0},
)
raw = kit.converse_text(response).strip().removeprefix("```json").removesuffix("```").strip()
print("📦 JSON:", json.dumps(json.loads(raw), indent=2, ensure_ascii=False))

# %% [markdown]
# ## Paso 6: Streaming (como ChatGPT, token a token)
# Para interfaces de chat usamos `converse_stream`: el usuario ve la respuesta mientras se genera.

# %%
start = time.time()
first_token_at = None
stream = bedrock.converse_stream(
    modelId=MODEL_ID,
    system=[{"text": SYSTEM_PROMPT}],
    messages=[{"role": "user", "content": [{"text": "Dame 3 tips cortos para cuidar mis finanzas personales."}]}],
    inferenceConfig={"maxTokens": 400},
)
for event in stream["stream"]:
    if "contentBlockDelta" in event and "text" in event["contentBlockDelta"]["delta"]:
        first_token_at = first_token_at or time.time()
        print(event["contentBlockDelta"]["delta"]["text"], end="", flush=True)
    if "metadata" in event:
        usage = event["metadata"]["usage"]
print(f"\n\n⚡ Primer token en {first_token_at - start:.2f}s | total {time.time() - start:.2f}s | tokens {usage}")

# %% [markdown]
# ## 🎯 Reto rápido
# 1. Cambia `temperature` a `1.0` en el Paso 3 y ejecuta 2 veces. ¿Cambia la respuesta?
# 2. Pon `maxTokens=20`. ¿Qué `stopReason` obtienes?

# %%
kit.level_up(1)
