"""
Agent v08 - Strands on AgentCore Runtime + AgentCore Gateway (MCP).

New vs v07: the agent discovers REMOTE tools through the AgentCore Gateway MCP
endpoint (Web Search + the Banking API exposed from Amazon API Gateway).
Auth: the Runtime execution role signs MCP requests with SigV4 (no API keys).
"""

import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands import Agent, tool
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

AGENT_NAME = os.environ.get("AGENT_NAME", "AgentBot")
MODEL_ID = os.environ.get("MODEL_ID", "global.anthropic.claude-sonnet-5")
REGION = os.environ.get("AWS_REGION", "us-east-1")
GATEWAY_URL = os.environ["GATEWAY_URL"]
SYSTEM_PROMPT = os.environ.get("SYSTEM_PROMPT", f"Eres {AGENT_NAME}, un asistente bancario amable.")
INSTRUCTIONS = """
Herramientas disponibles:
- API bancaria (productos, transacciones, simulaciones de CDT y credito, tasas de referencia): usala para datos del cliente.
- WebSearch: solo para informacion publica y actual (noticias, TRM del dia). Cita las fuentes.
- calcular_cuota_credito: calculos locales rapidos.
Nunca inventes saldos ni movimientos: consulta siempre la API."""

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


def gateway_client() -> MCPClient:
    """MCP client to the AgentCore Gateway, signed with SigV4 using the runtime role."""
    return MCPClient(lambda: aws_iam_streamablehttp_client(GATEWAY_URL, aws_service="bedrock-agentcore", aws_region=REGION))


def build_agent() -> Agent:
    return Agent(
        name=AGENT_NAME,
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION, max_tokens=4096),
        system_prompt=SYSTEM_PROMPT + INSTRUCTIONS,
        tools=[calcular_cuota_credito, gateway_client()],  # Strands manages the MCP session lifecycle
        callback_handler=None,
    )


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
