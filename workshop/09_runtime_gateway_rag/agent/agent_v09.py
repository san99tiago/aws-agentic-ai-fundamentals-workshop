"""
Agent v09 - the final agent: Strands on AgentCore Runtime + AgentCore Gateway
(Banking API + Web Search + Managed Knowledge Base) + Amazon Bedrock Guardrails.

New vs v08:
  * RAG through the Gateway: the Managed Knowledge Base is just another MCP tool
  * Bedrock Guardrails as an INDEPENDENT layer (ApplyGuardrail API): the user input
    is checked before the agent runs and the final answer before it is returned.
    Tool results (KB documents, API payloads) are not mistaken for user intent.
"""

import os

import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

AGENT_NAME = os.environ.get("AGENT_NAME", "AgentBot")
MODEL_ID = os.environ.get("MODEL_ID", "global.anthropic.claude-sonnet-5")
REGION = os.environ.get("AWS_REGION", "us-east-1")
GATEWAY_URL = os.environ["GATEWAY_URL"]
GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID")
GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "1")
SYSTEM_PROMPT = os.environ.get("SYSTEM_PROMPT", f"Eres {AGENT_NAME}, un asistente bancario amable.")
INSTRUCTIONS = """
Como elegir herramientas:
1. Productos, tasas, condiciones, seguridad o canales del banco -> busca SIEMPRE primero en la base de conocimiento (Retrieve) y cita el documento.
2. Datos del cliente (productos, saldos, transacciones) y simulaciones -> API bancaria.
3. Informacion publica y actual (TRM del dia, noticias) -> WebSearch, citando fuentes.
4. Calculos -> calcular_cuota_credito o razonamiento paso a paso.
Combina herramientas cuando la pregunta lo requiera. Nunca inventes datos."""

app = BedrockAgentCoreApp()


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
    return {"cuota_mensual": round(cuota, 2), "total_intereses": round(cuota * meses - monto, 2)}


BEDROCK = boto3.client("bedrock-runtime", region_name=REGION)


def _blocked(assessments: list) -> bool:
    """True if any policy BLOCKED the content (vs. only ANONYMIZED PII)."""
    for assessment in assessments:
        for policy, detail in assessment.items():
            if not isinstance(detail, dict):
                continue
            for findings in detail.values():
                if isinstance(findings, list) and any(f.get("action") == "BLOCKED" for f in findings if isinstance(f, dict)):
                    return True
    return False


def apply_guardrail(text: str, source: str) -> tuple[str, str]:
    """Returns (status, text) with status NONE | BLOCKED | ANONYMIZED."""
    if not GUARDRAIL_ID:
        return "NONE", text
    result = BEDROCK.apply_guardrail(
        guardrailIdentifier=GUARDRAIL_ID,
        guardrailVersion=GUARDRAIL_VERSION,
        source=source,
        content=[{"text": {"text": text}}],
    )
    if result["action"] != "GUARDRAIL_INTERVENED":
        return "NONE", text
    guarded_text = "".join(o["text"] for o in result.get("outputs", [])) or text
    return ("BLOCKED" if _blocked(result.get("assessments", [])) else "ANONYMIZED"), guarded_text


def build_model() -> BedrockModel:
    return BedrockModel(model_id=MODEL_ID, region_name=REGION, max_tokens=4096)


def build_agent() -> Agent:
    gateway = MCPClient(lambda: aws_iam_streamablehttp_client(GATEWAY_URL, aws_service="bedrock-agentcore", aws_region=REGION))
    return Agent(
        name=AGENT_NAME,
        model=build_model(),
        system_prompt=SYSTEM_PROMPT + INSTRUCTIONS,
        tools=[calcular_cuota_credito, gateway],
        callback_handler=None,
    )


AGENT = None


@app.entrypoint
def invoke(payload: dict, context=None) -> dict:
    global AGENT
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return {"error": "payload must be {'prompt': '<non-empty string>'}"}
    # 1) Guardrail on the USER INPUT (before spending tokens on the agent)
    input_status, safe_prompt = apply_guardrail(prompt[:4000], "INPUT")
    if input_status == "BLOCKED":
        return {"result": safe_prompt, "stop_reason": "guardrail_intervened", "guardrail": "INPUT_BLOCKED", "tools_used": []}

    AGENT = AGENT or build_agent()
    tools_before = set(AGENT.event_loop_metrics.tool_metrics)
    calls_before = {name: m.call_count for name, m in AGENT.event_loop_metrics.tool_metrics.items()}
    result = AGENT(safe_prompt)

    # 2) Guardrail on the FINAL ANSWER (PII masking, leaked secrets, unsafe content)
    output_status, safe_answer = apply_guardrail(str(result), "OUTPUT")
    tools_this_turn = sorted(
        name for name, m in result.metrics.tool_metrics.items()
        if name not in tools_before or m.call_count > calls_before.get(name, 0)
    )
    return {
        "result": safe_answer,
        "stop_reason": "guardrail_intervened" if output_status == "BLOCKED" else result.stop_reason,
        "guardrail": f"INPUT_{input_status}/OUTPUT_{output_status}",
        "tools_used": tools_this_turn,
        "usage": result.metrics.accumulated_usage,
    }


if __name__ == "__main__":
    app.run()
