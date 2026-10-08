"""
Agent v07 - Strands Agents on Amazon Bedrock AgentCore Runtime.

Our OWN agent code (vs. the managed Harness): we decide the loop, the tools and
the logic. AgentCore Runtime runs it serverless, one isolated microVM per session.

Contract (HTTP protocol): POST /invocations  {"prompt": "..."}  ->  {"result": "..."}
The BedrockAgentCoreApp wrapper implements /invocations and /ping for us.
"""

import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent, tool
from strands.models import BedrockModel

AGENT_NAME = os.environ.get("AGENT_NAME", "AgentBot")
MODEL_ID = os.environ.get("MODEL_ID", "global.anthropic.claude-sonnet-5")
REGION = os.environ.get("AWS_REGION", "us-east-1")
SYSTEM_PROMPT = os.environ.get("SYSTEM_PROMPT", f"Eres {AGENT_NAME}, un asistente bancario amable.")

app = BedrockAgentCoreApp()


# --------------------------------------------------------------------------
# Local tools: plain Python functions the LLM can decide to call
# --------------------------------------------------------------------------
@tool
def calcular_cuota_credito(monto: float, meses: int, tasa_ea: float) -> dict:
    """Calcula la cuota mensual fija de un credito (sistema frances / anualidad).

    Args:
        monto: Monto del credito en COP.
        meses: Plazo en meses.
        tasa_ea: Tasa efectiva anual en porcentaje, por ejemplo 18.0
    """
    tasa_mensual = (1 + tasa_ea / 100) ** (1 / 12) - 1
    cuota = monto * tasa_mensual / (1 - (1 + tasa_mensual) ** -meses)
    return {
        "cuota_mensual": round(cuota, 2),
        "tasa_mensual_pct": round(tasa_mensual * 100, 4),
        "total_pagado": round(cuota * meses, 2),
        "total_intereses": round(cuota * meses - monto, 2),
    }


@tool
def convertir_tasa_ea_a_mensual(tasa_ea: float) -> float:
    """Convierte una tasa efectiva anual (porcentaje) a tasa mensual equivalente (porcentaje).

    Args:
        tasa_ea: Tasa efectiva anual en porcentaje, por ejemplo 9.5
    """
    return round(((1 + tasa_ea / 100) ** (1 / 12) - 1) * 100, 4)


LOCAL_TOOLS = [calcular_cuota_credito, convertir_tasa_ea_a_mensual]


def build_agent() -> Agent:
    return Agent(
        name=AGENT_NAME,
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION, max_tokens=4096),
        system_prompt=SYSTEM_PROMPT + "\nUsa tus herramientas para cualquier calculo financiero.",
        tools=LOCAL_TOOLS,
        callback_handler=None,
    )


# One microVM per session => a module-level agent keeps the conversation of THIS session
AGENT = None


@app.entrypoint
def invoke(payload: dict, context=None) -> dict:
    global AGENT
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return {"error": "payload must be {'prompt': '<non-empty string>'}"}
    AGENT = AGENT or build_agent()
    result = AGENT(prompt[:4000])
    return {
        "result": str(result),
        "tools_used": sorted(result.metrics.tool_metrics.keys()),
        "usage": result.metrics.accumulated_usage,
    }


if __name__ == "__main__":
    app.run()
