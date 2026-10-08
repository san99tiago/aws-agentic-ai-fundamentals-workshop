# %% [markdown]
# # 🧠 Módulo 02 - Batalla de Cerebros: OpenAI vs Claude en Amazon Bedrock
#
# **Objetivo:** comparar 6 modelos con la MISMA pregunta usando la MISMA API (Converse):
# - OpenAI en Bedrock: **GPT-5.6 Luna** (rápido), **Terra** (balanceado), **Sol** (máximo razonamiento)
# - Anthropic en Bedrock: **Claude Haiku** (rápido), **Sonnet** (balanceado), **Opus** (máximo),
#   según `FAST_MODEL_ID`, `DEFAULT_MODEL_ID` y `TOP_MODEL_ID` del archivo `.env`
#
# ⏱️ Duración: 10 minutos
#
# ```mermaid
# flowchart TB
#     Q["❓ Misma pregunta"] --> CV["Converse API (una sola interfaz)"]
#     CV --> L["🌙 GPT-5.6 Luna"] & T["🌍 GPT-5.6 Terra"] & S["☀️ GPT-5.6 Sol"]
#     CV --> H["🍃 Claude Haiku"] & SO["🎼 Claude Sonnet"] & O["🎭 Claude Opus"]
#     L & T & S & H & SO & O --> J["⚖️ Juez: LLM-as-a-Judge"]
#     J --> W["🏆 Tabla: calidad vs latencia vs tokens"]
# ```
#
# **Lección clave:** no existe "el mejor modelo". Existe el mejor modelo **para cada tarea**
# (calidad vs latencia vs costo). Con Bedrock cambiar de modelo es cambiar un string. 🔁
#
# 💲 Precios: consulta https://aws.amazon.com/bedrock/pricing/ (cambian con frecuencia).

# %%
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop" / "common").exists())
sys.path.insert(0, str(ROOT / "workshop" / "common"))

import workshop_kit as kit

kit.banner(2)
bedrock = kit.client("bedrock-runtime")
QUESTION = kit.customer()["examples"]["m02_battle"]
SYSTEM = kit.customer()["agent_persona"]

CFG = kit.config()


def claude_label(emoji: str, model_id: str) -> str:
    """'us.anthropic.claude-opus-5' -> '🎭 Claude Opus 5'"""
    name = model_id.split("claude-", 1)[-1].split("-2025")[0].split("-v1")[0]
    family, *version = name.split("-")
    return f"{emoji} Claude {family.capitalize()} {'.'.join(version)}".strip()


CONTENDERS = {
    "🌙 GPT-5.6 Luna": "us.openai.gpt-5.6-luna",
    "🌍 GPT-5.6 Terra": "us.openai.gpt-5.6-terra",
    "☀️ GPT-5.6 Sol": "us.openai.gpt-5.6-sol",
    claude_label("🍃", CFG["fast_model_id"]): CFG["fast_model_id"],
    claude_label("🎼", CFG["default_model_id"]): CFG["default_model_id"],
    claude_label("🎭", CFG["top_model_id"]): CFG["top_model_id"],
}
print("❓ Pregunta de la batalla:\n", QUESTION)

# %% [markdown]
# ## Paso 1: ¡Que empiece la batalla! (6 modelos en paralelo)
# Nota: los modelos de razonamiento (Sol/Terra/Opus) "piensan" antes de responder:
# esos tokens de razonamiento también cuentan como tokens de salida.

# %%
def ask(label_model):
    label, model_id = label_model
    start = time.time()
    try:
        response = bedrock.converse(
            modelId=model_id,
            system=[{"text": SYSTEM}],
            messages=[{"role": "user", "content": [{"text": QUESTION}]}],
            inferenceConfig={"maxTokens": 2500},
        )
        return {
            "label": label,
            "model_id": model_id,
            "answer": kit.converse_text(response),
            "input_tokens": response["usage"]["inputTokens"],
            "output_tokens": response["usage"]["outputTokens"],
            "latency_s": round(response["metrics"]["latencyMs"] / 1000, 2),
            "wall_s": round(time.time() - start, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {"label": label, "model_id": model_id, "error": str(exc)}


with ThreadPoolExecutor(max_workers=6) as pool:
    results = list(pool.map(ask, CONTENDERS.items()))

for r in results:
    if "error" in r:
        print(f"\n❌ {r['label']}: {r['error']}")
        continue
    print(f"\n{'=' * 70}\n{r['label']}  ({r['latency_s']}s | out {r['output_tokens']} tokens)\n{'-' * 70}\n{r['answer'][:1200]}")

# %% [markdown]
# ## Paso 2: El juez ⚖️ (LLM-as-a-Judge)
# Usamos un modelo como evaluador con una rúbrica. Esta misma técnica es la base de
# **AgentCore Evaluations** para medir calidad de agentes en producción.

# %%
JUDGE_MODEL = CFG["top_model_id"]
valid = [r for r in results if "error" not in r]
answers_block = "\n\n".join(f"<respuesta id='{i}'>\n{r['answer']}\n</respuesta>" for i, r in enumerate(valid))
judge_prompt = f"""Evalua cada respuesta a la pregunta de un cliente bancario.
Pregunta: {QUESTION}

Rubrica (0-10): exactitud financiera, claridad para un cliente no experto, cumplimiento del formato pedido (max 5 bullets) y tono.
Responde SOLO JSON valido: {{"scores": [{{"id": 0, "score": 0, "reason": "max 15 palabras"}}]}}

{answers_block}"""

judge = bedrock.converse(
    modelId=JUDGE_MODEL,
    messages=[{"role": "user", "content": [{"text": judge_prompt}]}],
    inferenceConfig={"maxTokens": 3000},
)
raw = kit.converse_text(judge).strip().removeprefix("```json").removesuffix("```").strip()
scores = {s["id"]: s for s in json.loads(raw)["scores"]}

# %% [markdown]
# ## Paso 3: 🏆 Tabla de resultados

# %%
print(f"{'Modelo':<22} {'Score':>5} {'Latencia':>9} {'Tok out':>8} {'Tok/s':>6}  Razón del juez")
print("-" * 100)
ranking = sorted(enumerate(valid), key=lambda x: -scores.get(x[0], {}).get("score", 0))
for i, r in ranking:
    tps = r["output_tokens"] / r["latency_s"] if r["latency_s"] else 0
    s = scores.get(i, {})
    print(f"{r['label']:<22} {s.get('score', '-'):>5} {r['latency_s']:>8}s {r['output_tokens']:>8} {tps:>6.0f}  {s.get('reason', '')}")

(ROOT / "workshop" / "02_model_battle" / "battle_results.json").write_text(
    json.dumps({"question": QUESTION, "results": valid, "scores": scores}, indent=2, ensure_ascii=False)
)

# %% [markdown]
# ## 🎯 Reflexión
# - ¿Para un chatbot de preguntas frecuentes con millones de usuarios, cuál elegirías?
# - ¿Y para analizar un contrato de crédito complejo?
# - Patrón común en producción: **router de modelos** (rápido para lo simple, potente para lo complejo).

# %%
kit.level_up(2)
