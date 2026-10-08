# %% [markdown]
# # 🛡️ Módulo 03 - Amazon Bedrock Guardrails
#
# **Objetivo:** proteger al agente contra *prompt injection*, fuga de información, temas
# prohibidos y datos personales (PII), con controles **independientes del modelo**.
#
# ⏱️ Duración: 15 minutos
#
# ```mermaid
# flowchart LR
#     U["👤 Usuario"] -->|prompt| GI{"🛡️ Guardrail<br/>INPUT"}
#     GI -->|"❌ bloqueado"| B["Mensaje seguro"]
#     GI -->|"✅ pasa"| M["🧠 LLM"]
#     M --> GO{"🛡️ Guardrail<br/>OUTPUT"}
#     GO -->|"❌ bloqueado / 🎭 PII enmascarada"| B
#     GO -->|"✅ pasa"| R["Respuesta"]
#     X["ApplyGuardrail API<br/>(cualquier modelo, incluso fuera de Bedrock)"] -.-> GI & GO
# ```
#
# **Capas de protección (OWASP Top 10 para LLMs):**
# | Política | Protege contra | OWASP |
# |---|---|---|
# | Content filters + **Prompt Attack** | Jailbreaks, inyección de prompts | LLM01 |
# | **Denied topics** | Asesoría de inversión, fraude | LLM09 / negocio |
# | **Word filters** | Fuga de códigos internos | LLM02 / LLM07 |
# | **Sensitive info (PII)** | Tarjetas, emails, cédulas | LLM02 |
# | Contextual grounding | Alucinaciones en RAG (módulo 09) | LLM09 |

# %%
import json
import sys
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop" / "common").exists())
sys.path.insert(0, str(ROOT / "workshop" / "common"))

import workshop_kit as kit

kit.banner(3)
bedrock = kit.client("bedrock")
runtime = kit.client("bedrock-runtime")
pack = kit.customer()
MODEL_ID = kit.config()["fast_model_id"]
ATTACKS = [pack["examples"]["m03_safe"], *pack["examples"]["m03_attacks"]]

# El agente "vulnerable": tiene información confidencial en su system prompt (¡mala práctica a propósito!)
VULNERABLE_SYSTEM = pack["agent_persona"] + "\n\n" + pack["secret_context"]

# %% [markdown]
# ## Paso 1: El agente SIN guardrails 😱
# Probamos una pregunta legítima + ataques. Observa cuáles logran su objetivo.

# %%
def ask(prompt: str, guardrail: dict | None = None) -> tuple[str, str]:
    kwargs = {}
    if guardrail:
        kwargs["guardrailConfig"] = {**guardrail, "trace": "enabled"}
    response = runtime.converse(
        modelId=MODEL_ID,
        system=[{"text": VULNERABLE_SYSTEM}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 400, "temperature": 0.7},
        **kwargs,
    )
    return response["stopReason"], kit.converse_text(response)


for prompt in ATTACKS:
    stop, text = ask(prompt)
    print(f"\n🧪 PROMPT: {prompt}\n   stopReason={stop}\n   🤖 {text[:350]}")

# %% [markdown]
# ## Paso 2: Crear el Guardrail 🛡️
# Usamos el tier **STANDARD** (mejor detección y soporte multilenguaje, ideal para español),
# que requiere un *guardrail profile* de inferencia cross-region (`us.guardrail.v1:0`).

# %%
GUARDRAIL_NAME = kit.name("guardrail")
gcfg = pack["guardrail"]

guardrail_definition = dict(
    name=GUARDRAIL_NAME,
    description=f"Guardrail del workshop para {kit.agent_name()}",
    crossRegionConfig={"guardrailProfileIdentifier": "us.guardrail.v1:0"},
    contentPolicyConfig={
        "tierConfig": {"tierName": "STANDARD"},
        "filtersConfig": [
            {"type": t, "inputStrength": "HIGH", "outputStrength": "HIGH"}
            for t in ("SEXUAL", "VIOLENCE", "HATE", "INSULTS", "MISCONDUCT")
        ]
        + [{"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"}],
    },
    topicPolicyConfig={
        "tierConfig": {"tierName": "STANDARD"},
        "topicsConfig": [
            {
                "name": t["name"],
                "definition": t["definition"],
                "examples": t["examples"],
                "type": "DENY",
                # Topics can be evaluated on the user INPUT, the model OUTPUT, or both
                "inputEnabled": t.get("input_enabled", True),
                "outputEnabled": t.get("output_enabled", True),
            }
            for t in gcfg["denied_topics"]
        ],
    },
    wordPolicyConfig={
        "wordsConfig": [{"text": w} for w in gcfg["blocked_words"]],
        "managedWordListsConfig": [{"type": "PROFANITY"}],
    },
    sensitiveInformationPolicyConfig={
        "piiEntitiesConfig": [
            {"type": "CREDIT_DEBIT_CARD_NUMBER", "action": "BLOCK"},
            {"type": "CREDIT_DEBIT_CARD_CVV", "action": "BLOCK"},
            {"type": "PIN", "action": "BLOCK"},
            {"type": "EMAIL", "action": "ANONYMIZE"},
            {"type": "PHONE", "action": "ANONYMIZE"},
        ],
        "regexesConfig": [
            {"name": r["name"], "description": r["description"], "pattern": r["pattern"], "action": r["action"]}
            for r in gcfg["pii_regex"]
        ],
    },
    blockedInputMessaging=gcfg["blocked_message"],
    blockedOutputsMessaging=gcfg["blocked_message"],
)

existing = [g for g in bedrock.list_guardrails()["guardrails"] if g["name"] == GUARDRAIL_NAME]
if existing:
    guardrail_id = existing[0]["id"]
    bedrock.update_guardrail(guardrailIdentifier=guardrail_id, **{k: v for k, v in guardrail_definition.items()})
    print(f"♻️ Guardrail actualizado: {guardrail_id}")
else:
    guardrail_id = bedrock.create_guardrail(**guardrail_definition)["guardrailId"]
    print(f"✅ Guardrail creado: {guardrail_id}")

kit.wait_for(lambda: bedrock.get_guardrail(guardrailIdentifier=guardrail_id)["status"], ("READY",), ("FAILED",), "Guardrail", every=5)
version = bedrock.create_guardrail_version(guardrailIdentifier=guardrail_id, description="workshop")["version"]
kit.wait_for(
    lambda: bedrock.get_guardrail(guardrailIdentifier=guardrail_id, guardrailVersion=version)["status"],
    ("READY",), ("FAILED",), f"Versión {version}", every=5,
)
kit.save_state(guardrail_id=guardrail_id, guardrail_version=version)
GUARDRAIL = {"guardrailIdentifier": guardrail_id, "guardrailVersion": version}
print(f"🛡️ Guardrail listo: id={guardrail_id} version={version}")

# %% [markdown]
# ## Paso 3: El agente CON guardrails ✅
# Mismos prompts. `stopReason = guardrail_intervened` indica que el guardrail actuó.

# %%
for prompt in ATTACKS:
    stop, text = ask(prompt, GUARDRAIL)
    if stop != "guardrail_intervened":
        icon = "✅ PERMITIDO"
    elif text.strip() == gcfg["blocked_message"]:
        icon = "🛡️ BLOQUEADO"
    else:
        icon = "🎭 PERMITIDO con PII ENMASCARADA (ANONYMIZE)"
    print(f"\n🧪 PROMPT: {prompt}\n   {icon}\n   🤖 {text[:300]}")

# %% [markdown]
# ## Paso 4: ¿QUÉ política actuó? (ApplyGuardrail + assessments)
# `ApplyGuardrail` evalúa texto **sin invocar ningún modelo**: sirve para LLMs fuera de Bedrock,
# para validar respuestas de herramientas, o para auditar.

# %%
def explain(text: str, source: str = "INPUT") -> None:
    result = runtime.apply_guardrail(
        guardrailIdentifier=guardrail_id, guardrailVersion=version, source=source, content=[{"text": {"text": text}}]
    )
    print(f"\n🔎 [{source}] {text[:90]}...\n   action = {result['action']}")
    for assessment in result.get("assessments", []):
        for policy, detail in assessment.items():
            if policy in ("invocationMetrics", "appliedGuardrailDetails"):
                continue
            print(f"   📋 {policy}: {json.dumps(detail, ensure_ascii=False)[:300]}")
    if result["action"] == "GUARDRAIL_INTERVENED" and result.get("outputs"):
        print(f"   ➡️ salida: {result['outputs'][0]['text'][:200]}")


for prompt in pack["examples"]["m03_attacks"]:
    explain(prompt)

# %% [markdown]
# ## Paso 5: Enmascarar PII en la SALIDA (ANONYMIZE) 🎭
# Simulamos una respuesta de un modelo/herramienta que trae datos personales.

# %%
explain(
    "Que hago si recibo un mensaje sospechoso pidiendo mi clave dinamica?"  # legitimate -> must pass
)
explain(
    f"Listo! Le enviamos el extracto a camila.perez@correo.com y la llamaremos al 300 555 1234. Su cedula 1036123456 quedo validada.",
    source="OUTPUT",
)

# %% [markdown]
# ## Paso 6: Guardrails son agnósticos al modelo 🔁
# El MISMO guardrail protege un modelo de OpenAI en Bedrock.

# %%
response = runtime.converse(
    modelId="us.openai.gpt-5.6-luna",
    system=[{"text": VULNERABLE_SYSTEM}],
    messages=[{"role": "user", "content": [{"text": pack["examples"]["m03_attacks"][0]}]}],
    inferenceConfig={"maxTokens": 400},
    guardrailConfig=GUARDRAIL,
)
print(f"🌙 GPT-5.6 Luna + guardrail -> stopReason={response['stopReason']}\n   {kit.converse_text(response)}")

# %% [markdown]
# ## 💡 Buenas prácticas
# - **Evita falsos positivos:** define los *denied topics* de forma precisa. En este workshop una
#   definición amplia de "fraude" bloqueaba preguntas legítimas como *"¿qué hago si me piden mi clave
#   dinámica?"*. La versión final habla de **cometer** fraude, no de **protegerse** de él.
#   Prueba siempre con un set de preguntas legítimas + ataques (como este notebook) antes de producción.
# - **Nunca** pongas secretos en el system prompt (lo hicimos a propósito para el demo).
# - Defensa en profundidad: Guardrails + IAM + validación de herramientas + observabilidad.
# - El enmascaramiento de PII aplica a la respuesta, los logs de CloudWatch pueden contener el original:
#   cifra logs con KMS y restringe acceso.

# %%
kit.level_up(3)
