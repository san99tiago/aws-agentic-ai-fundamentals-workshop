# %% [markdown]
# # 🤖 Módulo 05 - Amazon Bedrock AgentCore Harness
#
# **Objetivo:** crear un agente COMPLETO sin escribir el ciclo de orquestación:
# solo **configuración** (modelo + instrucciones + herramientas + memoria + límites).
#
# ⏱️ Duración: 15 minutos
#
# **¿Qué es un Harness de agente?** El sistema que permite que un agente realmente se ejecute:
# ciclo de orquestación (razonar → usar herramienta → observar → responder) + infraestructura
# de producción (entorno aislado, sesión, conexiones a herramientas, memoria, observabilidad).
#
# ```mermaid
# flowchart TB
#     U["👤 InvokeHarness<br/>(sessionId + messages)"] --> H
#     subgraph H["🤖 AgentCore Harness (gestionado)"]
#         direction TB
#         LOOP["🔁 Ciclo de orquestación<br/>(Strands, gestionado)"]
#         VM["🖥️ microVM aislada por sesión<br/>filesystem + shell"]
#         MEM["🧠 Memoria corto/largo plazo"]
#         LOOP --- VM
#         LOOP --- MEM
#     end
#     LOOP -->|"modelo (cambiable por invocación)"| M["Claude / OpenAI / Gemini..."]
#     LOOP -->|tools| CI["🧮 Code Interpreter"]
#     LOOP -.->|"módulo 06"| GW["🌐 AgentCore Gateway"]
#     H --> OBS["📈 Observabilidad (CloudWatch)"]
# ```
#
# | | **Harness** (este módulo) | **Runtime** (módulo 07) |
# |---|---|---|
# | Tú aportas | Configuración | Código + dependencias |
# | Ciclo del agente | Gestionado | Lo escribes tú (Strands, LangGraph...) |
# | Cambiar modelo/tool | Cambio de config | Cambio de código + redeploy |

# %%
import sys
import time
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop" / "common").exists())
sys.path.insert(0, str(ROOT / "workshop" / "common"))

import workshop_kit as kit

kit.banner(5)
control = kit.client("bedrock-agentcore-control")
data = kit.client("bedrock-agentcore")
pack = kit.customer()
HARNESS_NAME = kit.name("harness", sep="_")  # letters, digits and underscores only

# %% [markdown]
# ## Paso 1: Declarar el agente (¡esto es TODO el "código"!)

# %%
harness_config = dict(
    executionRoleArn=kit.outputs()["HarnessRoleArn"],
    model={"bedrockModelConfig": {"modelId": kit.config()["default_model_id"], "maxTokens": 4096}},
    systemPrompt=[{"text": pack["agent_persona"] + "\nCuando necesites hacer calculos, usa tu interprete de codigo y muestra el resultado de forma clara."}],
    tools=[{"type": "agentcore_code_interpreter", "name": "code_interpreter", "config": {"agentCoreCodeInterpreter": {}}}],
    maxIterations=15,
    maxTokens=8192,
    timeoutSeconds=300,
)



def find_harness(harness_name: str, include_deleting: bool = False) -> dict | None:
    for page in control.get_paginator("list_harnesses").paginate():
        for item in page.get("harnesses", []):
            if item["harnessName"] == harness_name and (include_deleting or item["status"] != "DELETING"):
                return item
    return None


existing = find_harness(HARNESS_NAME, include_deleting=True)
if existing and existing["status"] in ("DELETING", "CREATE_FAILED", "UPDATE_FAILED"):
    if existing["status"] != "DELETING":  # clean up a failed attempt and start fresh
        print(f"🧹 Eliminando harness fallido {existing['harnessId']}...")
        control.delete_harness(harnessId=existing["harnessId"])
    kit.wait_for(lambda: (find_harness(HARNESS_NAME, True) or {}).get("status", "DELETED"), ("DELETED",), label="Delete", every=15)
    time.sleep(30)  # the managed runtime behind the harness is released asynchronously
    existing = None

if existing:
    harness_id = existing["harnessId"]
    control.update_harness(harnessId=harness_id, **harness_config)
    print(f"♻️ Harness actualizado: {harness_id}")
else:
    harness_id = control.create_harness(harnessName=HARNESS_NAME, **harness_config)["harness"]["harnessId"]
    print(f"✅ Harness creado: {harness_id}")

kit.wait_for(
    lambda: control.get_harness(harnessId=harness_id)["harness"]["status"],
    ("READY",), ("CREATE_FAILED", "UPDATE_FAILED"), "Harness", every=10,
)
harness = control.get_harness(harnessId=harness_id)["harness"]
HARNESS_ARN = harness["arn"]
kit.save_state(harness_id=harness_id, harness_arn=HARNESS_ARN)
print(f"🤖 ARN: {HARNESS_ARN}")

# %% [markdown]
# ## Paso 2: ¡Hablemos con el agente gestionado!
# - `runtimeSessionId`: cada sesión es una microVM aislada con su propio estado.
# - `actorId`: identifica al USUARIO final. La memoria gestionada se separa por actor.

# %%
SESSION_ID = kit.new_session_id()
ACTOR_ID = f"camila-{SESSION_ID[:8]}"


def chat(text: str, session_id: str = SESSION_ID, actor_id: str = ACTOR_ID, **overrides) -> dict:
    print(f"\n👤 [{actor_id}] {text}\n🤖 ", end="")
    response = data.invoke_harness(
        harnessArn=HARNESS_ARN,
        runtimeSessionId=session_id,
        actorId=actor_id,
        messages=[{"role": "user", "content": [{"text": text}]}],
        **overrides,
    )
    return kit.print_stream(response["stream"])


chat("Hola! Soy Camila, de Medellin. En una frase: quien eres?")

# %% [markdown]
# ## Paso 3: El agente usa herramientas por su cuenta 🧮
# Le pedimos un cálculo: el ciclo decide usar el **Code Interpreter** (Python en sandbox).

# %%
result = chat(pack["examples"]["m05_harness"])
print(f"\n📊 Herramientas usadas: {result['tools']} | stopReason: {result['stop_reason']}")

# %% [markdown]
# ## Paso 4: Estado de la sesión 🧠 (misma sesión = recuerda)

# %%
chat("Como me llamo y de que ciudad soy? Y cual fue el total final que calculaste?")

# %% [markdown]
# ## Paso 5: Cambiar de modelo EN LA MISMA SESIÓN sin perder contexto 🔁
# Override por invocación: ahora responde **Claude Haiku 4.5** (más rápido y económico), sin redeploy.
# Patrón típico: planear con un modelo potente y ejecutar tareas simples con uno rápido.
#
# ⚠️ Al cambiar de *proveedor* a mitad de sesión, el historial debe ser compatible
# (p. ej. los bloques de razonamiento de Claude no son aceptados por otros proveedores).
# Para OpenAI usa una sesión nueva (Paso 6 bonus).

# %%
chat(
    "Resume en 2 lineas lo que hemos hablado hasta ahora.",
    model={"bedrockModelConfig": {"modelId": kit.config()["fast_model_id"], "maxTokens": 2048}},
)

# %% [markdown]
# ## Paso 5b: El mismo harness con OpenAI GPT-5.6 Sol (sesión nueva) ☀️

# %%
chat(
    "En una frase, que es un CDT?",
    session_id=kit.new_session_id(),
    model={"bedrockModelConfig": {"modelId": "us.openai.gpt-5.6-sol", "maxTokens": 2048}},
)

# %% [markdown]
# ## Paso 6: Aislamiento por usuario 🔒
# Otro usuario (`actorId` distinto) en otra sesión (otra microVM) NO ve nada de Camila.

# %%
chat("Como me llamo y de que ciudad soy?", session_id=kit.new_session_id(), actor_id="otro-usuario-anonimo")

# %% [markdown]
# ## Paso 7 (bonus): Memoria de largo plazo 🧠
# La memoria gestionada extrae hechos y preferencias en segundo plano (de 1 a ~4 minutos).
# Una sesión NUEVA del MISMO `actorId` recuerda a Camila cuando la extracción termina:
# esta celda reintenta hasta 4 veces.

# %%
for attempt in range(1, 5):
    time.sleep(45)
    print(f"\n🧠 Intento {attempt}/4 (sesión nueva, mismo actorId)")
    result = chat("Hola de nuevo! Te acuerdas de mi? Como me llamo?", session_id=kit.new_session_id())
    if "Camila" in result["text"]:
        print("✅ ¡Memoria de largo plazo funcionando!")
        break
else:
    print("⏳ La memoria aún se está consolidando: vuelve a ejecutar esta celda en un par de minutos.")

# %% [markdown]
# ## 💡 Lo que acabas de lograr
# Un agente con ciclo de razonamiento, herramienta de código, estado de sesión, aislamiento y
# cambio de modelo... **sin escribir el agente**. Si necesitas lógica propia, el harness se puede
# exportar a código Strands y desplegar en AgentCore Runtime (módulo 07).

# %%
kit.level_up(5)
