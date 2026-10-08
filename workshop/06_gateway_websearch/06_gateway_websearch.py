# %% [markdown]
# # 🌐 Módulo 06 - AgentCore Gateway (MCP) + Web Search
#
# **Objetivo:** darle al agente información EN TIEMPO REAL de internet, a través de un
# **AgentCore Gateway**: un punto único y gobernado que expone herramientas vía **MCP**.
#
# ⏱️ Duración: 10 minutos
#
# **MCP (Model Context Protocol):** protocolo estándar para conectar agentes con herramientas
# (APIs, bases de datos, otros servicios). "El USB-C de los agentes". 🔌
#
# ```mermaid
# flowchart LR
#     A["🤖 Agente<br/>(Harness / Runtime / IDE)"] -->|"MCP tools/list<br/>tools/call (SigV4)"| G
#     subgraph G["🌐 AgentCore Gateway"]
#         AUTH["🔐 Inbound auth<br/>AWS_IAM / JWT"]
#         POL["📜 Políticas + auditoría"]
#         T1["🎯 Target: Web Search<br/>(connector gestionado)"]
#         T2["🎯 Target: API bancaria<br/>(módulo 08)"]
#         T3["🎯 Target: Knowledge Base<br/>(módulo 09)"]
#     end
#     T1 --> W["🔎 Índice web gestionado<br/>(dentro de AWS)"]
# ```
#
# **¿Por qué un Gateway y no conectar cada tool directo?**
# - Un solo endpoint MCP para N herramientas → descubrimiento dinámico.
# - Autenticación de entrada y salida centralizada (sin llaves en el agente).
# - Gobernanza: quién usa qué herramienta, filtros de dominios, políticas Cedar, logs.

# %%
import json
import sys
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop" / "common").exists())
sys.path.insert(0, str(ROOT / "workshop" / "common"))

import workshop_kit as kit

kit.banner(6)
control = kit.client("bedrock-agentcore-control")
data = kit.client("bedrock-agentcore")
pack = kit.customer()
GATEWAY_NAME = kit.name("gateway")

# %% [markdown]
# ## Paso 1: Crear el Gateway (protocolo MCP, autenticación AWS_IAM)

# %%
def find_gateway(gateway_name: str) -> dict | None:
    for page in control.get_paginator("list_gateways").paginate():
        for item in page.get("items", []):
            if item["name"] == gateway_name:
                return item
    return None


existing = find_gateway(GATEWAY_NAME)
if existing:
    gateway_id = existing["gatewayId"]
    print(f"♻️ Gateway existente: {gateway_id}")
else:
    gateway_id = control.create_gateway(
        name=GATEWAY_NAME,
        description=f"Gateway MCP de herramientas para {kit.agent_name()}",
        roleArn=kit.outputs()["GatewayRoleArn"],
        protocolType="MCP",
        protocolConfiguration={"mcp": {"searchType": "SEMANTIC"}},
        authorizerType="AWS_IAM",
        exceptionLevel="DEBUG",
    )["gatewayId"]
    print(f"✅ Gateway creado: {gateway_id}")

kit.wait_for(lambda: control.get_gateway(gatewayIdentifier=gateway_id)["status"], ("READY",), ("FAILED",), "Gateway", every=5)
gateway = control.get_gateway(gatewayIdentifier=gateway_id)
GATEWAY_ARN, GATEWAY_URL = gateway["gatewayArn"], gateway["gatewayUrl"]
kit.save_state(gateway_id=gateway_id, gateway_arn=GATEWAY_ARN, gateway_url=GATEWAY_URL)
print(f"🌐 MCP endpoint: {GATEWAY_URL}")

# %% [markdown]
# ## Paso 2: Agregar el target **Web Search** (connector gestionado, sin API keys)
# Opcional: `domainFilter` para excluir/incluir dominios (gobernanza de fuentes).

# %%
def upsert_target(name: str, target_configuration: dict) -> str:
    targets = control.list_gateway_targets(gatewayIdentifier=gateway_id)["items"]
    match = next((t for t in targets if t["name"] == name), None)
    kwargs = dict(
        gatewayIdentifier=gateway_id,
        name=name,
        targetConfiguration=target_configuration,
        credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
    )
    if match:
        target_id = match["targetId"]
        control.update_gateway_target(targetId=target_id, **kwargs)
    else:
        target_id = control.create_gateway_target(**kwargs)["targetId"]
    kit.wait_for(
        lambda: control.get_gateway_target(gatewayIdentifier=gateway_id, targetId=target_id)["status"],
        ("READY",), ("FAILED", "UPDATE_UNSUCCESSFUL"), f"Target {name}", every=5,
    )
    return target_id


web_params = {"domainFilter": {"exclude": pack["websearch_domains_exclude"]}} if pack["websearch_domains_exclude"] else {}
websearch_target_id = upsert_target(
    "web-search",
    {"mcp": {"connector": {"source": {"connectorId": "web-search"}, "configurations": [{"name": "WebSearch", "parameterValues": web_params}]}}},
)
kit.save_state(websearch_target_id=websearch_target_id)

# %% [markdown]
# ## Paso 3: Hablar MCP "a mano" con el Gateway 🔌
# Usamos el cliente MCP de Strands + firma SigV4 (`mcp-proxy-for-aws`).
# `tools/list` descubre herramientas; `tools/call` las ejecuta.

# %%
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands.tools.mcp import MCPClient

mcp_client = MCPClient(lambda: aws_iam_streamablehttp_client(GATEWAY_URL, aws_service="bedrock-agentcore", aws_region=kit.region()))
with mcp_client:
    tools = mcp_client.list_tools_sync()
    for tool in tools:
        spec = tool.tool_spec
        print(f"🔧 {spec['name']}: {spec['description'][:120]}")
    websearch_tool = next(t.tool_name for t in tools if t.tool_name.endswith("WebSearch"))
    result = mcp_client.call_tool_sync(
        tool_use_id="demo-1", name=websearch_tool, arguments={"query": f"{kit.config()['customer_name']} noticias"}
    )
    print("\n📰 Resultado (recortado):\n", json.dumps(result, ensure_ascii=False, default=str)[:1500])

# %% [markdown]
# ## Paso 4: Conectar el Gateway al Harness (¡solo configuración!) 🤖➕🌐
# Agregamos el Gateway como herramienta del harness del módulo 05.

# %%
HARNESS_ID = kit.require_state("harness_id", "05")
HARNESS_ARN = kit.require_state("harness_arn", "05")
current = control.get_harness(harnessId=HARNESS_ID)["harness"]
tools = [t for t in current.get("tools", []) if t.get("type") != "agentcore_gateway"]
tools.append({"type": "agentcore_gateway", "name": "herramientas", "config": {"agentCoreGateway": {"gatewayArn": GATEWAY_ARN, "outboundAuth": {"awsIam": {}}}}})
control.update_harness(harnessId=HARNESS_ID, tools=tools)
kit.wait_for(lambda: control.get_harness(harnessId=HARNESS_ID)["harness"]["status"], ("READY",), ("UPDATE_FAILED",), "Harness", every=10)

# %% [markdown]
# ## Paso 5: ¡El agente ahora busca en la web! 🔎

# %%
print(f"👤 {pack['examples']['m06_websearch']}\n🤖 ", end="")
response = data.invoke_harness(
    harnessArn=HARNESS_ARN,
    runtimeSessionId=kit.new_session_id(),
    messages=[{"role": "user", "content": [{"text": pack["examples"]["m06_websearch"]}]}],
)
summary = kit.print_stream(response["stream"])
print(f"\n📊 Herramientas usadas: {summary['tools']}")

# %% [markdown]
# ## 💡 Para llevar
# El mismo endpoint MCP del Gateway lo pueden usar: este Harness, un agente en Runtime (módulo 08),
# o incluso tu IDE (Kiro, VS Code, Claude Code) como servidor MCP remoto.

# %%
kit.level_up(6)
