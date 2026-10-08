# %% [markdown]
# # 🏦 Módulo 08 - Runtime + Gateway + API Backend (API Gateway + Lambda)
#
# **Objetivo:** convertir una API REST existente del "banco" en **herramientas MCP** sin escribir
# código adicional, y que nuestro agente en Runtime las use para consultar datos EN TIEMPO REAL.
#
# ⏱️ Duración: 10 minutos
#
# ```mermaid
# sequenceDiagram
#     autonumber
#     actor U as 👤 Cliente
#     participant R as 🚀 Runtime (Strands v08)
#     participant G as 🌐 AgentCore Gateway
#     participant A as 🔐 API Gateway (AWS_IAM)
#     participant L as λ Lambda (API bancaria)
#     U->>R: "Soy el cliente 1001, cuál es mi saldo?"
#     R->>G: MCP tools/list (SigV4)
#     G-->>R: getCustomerProducts, simulateCdt, WebSearch...
#     R->>G: tools/call consultar_productos_cliente(1001)
#     G->>A: GET /customers/1001/products (SigV4 rol del Gateway)
#     A->>L: invoke
#     L-->>R: JSON productos
#     R-->>U: Respuesta en lenguaje natural
# ```
#
# **Seguridad:** la API NO es pública: exige firma IAM. Solo el rol del Gateway puede invocarla.
# El agente nunca ve credenciales de la API. ✅

# %%
import json
import sys
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop" / "common").exists())
sys.path.insert(0, str(ROOT / "workshop" / "common"))

import runtime_deployer
import workshop_kit as kit

kit.banner(8)
control = kit.client("bedrock-agentcore-control")
pack = kit.customer()
out = kit.outputs()
GATEWAY_ID = kit.require_state("gateway_id", "06")
GATEWAY_URL = kit.require_state("gateway_url", "06")

# %% [markdown]
# ## Paso 1: La API del banco ya existe (desplegada con CDK)
# Probamos que está protegida: una llamada SIN firma IAM es rechazada.

# %%
import urllib.error
import urllib.request

try:
    urllib.request.urlopen(f"{out['BankingApiUrl']}customers/1001/products", timeout=10)
except urllib.error.HTTPError as exc:
    print(f"🔐 Sin firma IAM -> HTTP {exc.code} (¡bien! la API no es pública)")

# %% [markdown]
# ## Paso 2: Registrar la API como target del Gateway 🎯
# Target tipo **API Gateway stage**: el Gateway lee el contrato de la API (OpenAPI) y crea
# una herramienta MCP por operación. Con `toolOverrides` damos nombres y descripciones claras
# (¡la descripción es lo que el LLM lee para decidir qué herramienta usar!).

# %%
TOOLS = [
    ("/customers/{customer_id}/products", "GET", "consultar_productos_cliente",
     "Consulta los productos (cuentas, tarjetas, CDT, creditos) y saldos de un cliente por su customer_id."),
    ("/customers/{customer_id}/transactions", "GET", "consultar_transacciones_cliente",
     "Consulta las ultimas transacciones de un cliente por su customer_id. Parametro opcional limit."),
    ("/simulations/cdt", "POST", "simular_cdt",
     "Simula un CDT: recibe amount (COP) y term_days (90, 180, 360 o 540) y retorna intereses y neto al vencimiento."),
    ("/simulations/loan", "POST", "simular_credito",
     "Simula un credito: recibe amount (COP), months y rate_ea (porcentaje) y retorna la cuota mensual."),
    ("/exchange-rates", "GET", "consultar_tasas_de_cambio_referencia",
     "Tasas de cambio de REFERENCIA estaticas del banco (no en vivo)."),
]

target_configuration = {
    "mcp": {
        "apiGateway": {
            "restApiId": out["BankingApiId"],
            "stage": out["BankingApiStage"],
            "apiGatewayToolConfiguration": {
                "toolFilters": [{"filterPath": path, "methods": [method]} for path, method, _, _ in TOOLS],
                "toolOverrides": [
                    {"path": path, "method": method, "name": name, "description": description}
                    for path, method, name, description in TOOLS
                ],
            },
        }
    }
}

targets = control.list_gateway_targets(gatewayIdentifier=GATEWAY_ID)["items"]
match = next((t for t in targets if t["name"] == "banking-api"), None)
kwargs = dict(
    gatewayIdentifier=GATEWAY_ID,
    name="banking-api",
    description="API bancaria ficticia (API Gateway + Lambda, AWS_IAM)",
    targetConfiguration=target_configuration,
    credentialProviderConfigurations=[{"credentialProviderType": "GATEWAY_IAM_ROLE"}],
)
target_id = control.update_gateway_target(targetId=match["targetId"], **kwargs)["targetId"] if match else control.create_gateway_target(**kwargs)["targetId"]
kit.wait_for(
    lambda: control.get_gateway_target(gatewayIdentifier=GATEWAY_ID, targetId=target_id)["status"],
    ("READY",), ("FAILED", "UPDATE_UNSUCCESSFUL"), "Target banking-api", every=5,
)
kit.save_state(banking_target_id=target_id)

# %% [markdown]
# ## Paso 3: Descubrir las nuevas herramientas MCP 🔍

# %%
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands.tools.mcp import MCPClient

with MCPClient(lambda: aws_iam_streamablehttp_client(GATEWAY_URL, aws_service="bedrock-agentcore", aws_region=kit.region())) as mcp:
    for t in mcp.list_tools_sync():
        print(f"🔧 {t.tool_name}")
    direct = mcp.call_tool_sync("demo-api", "banking-api___consultar_productos_cliente", {"customer_id": "1001"})
    print("\n📦 Llamada directa:", json.dumps(direct, ensure_ascii=False, default=str)[:600])

# %% [markdown]
# ## Paso 4: Desplegar el agente v08 (mismo Runtime, nueva versión) 🚀
# Solo cambia `main.py` (las dependencias ya están en caché) y agregamos `GATEWAY_URL`.
# Mira `agent/agent_v08.py`: el `MCPClient` se pasa como una herramienta más.

# %%
runtime = runtime_deployer.deploy(
    ROOT / "workshop" / "08_runtime_gateway_api" / "agent" / "agent_v08.py",
    kit.name("agent", sep="_"),
    {"AGENT_NAME": kit.agent_name(), "MODEL_ID": kit.config()["default_model_id"], "SYSTEM_PROMPT": pack["agent_persona"], "GATEWAY_URL": GATEWAY_URL},
    description=f"{kit.agent_name()} v08 - Strands + Gateway (API bancaria + WebSearch)",
)
kit.save_state(runtime_arn=runtime["arn"], runtime_id=runtime["id"])
print(f"🚀 Versión desplegada: {runtime['version']}")

# %% [markdown]
# ## Paso 5: ¡El agente consulta la API del banco! 🏦

# %%
SESSION_ID = kit.new_session_id()
for question in (pack["examples"]["m08_api"], pack["examples"]["m08_api_2"]):
    answer = runtime_deployer.invoke(runtime["arn"], question, SESSION_ID)
    print(f"\n👤 {question}")
    kit.show(kit.agent_name(), answer.get("result", json.dumps(answer)), "🏦")
    print("🔧 Herramientas:", answer.get("tools_used"))

# %%
kit.level_up(8)
