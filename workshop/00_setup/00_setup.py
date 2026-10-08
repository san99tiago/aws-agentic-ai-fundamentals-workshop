# %% [markdown]
# # 🥚 Módulo 00 - Preparar el entorno
#
# **Objetivo:** validar que tu IDE (VS Code o SageMaker Studio) tiene credenciales de AWS,
# acceso a los modelos de Amazon Bedrock y que la infraestructura base del workshop está desplegada.
#
# ⏱️ Duración: 5 minutos
#
# ```mermaid
# flowchart LR
#     IDE["💻 Tu IDE<br/>(VS Code / SageMaker Studio)"] -->|boto3 + credenciales| STS["AWS STS"]
#     IDE --> BR["Amazon Bedrock<br/>Modelos"]
#     IDE --> CFN["CloudFormation<br/>stack foundation"]
#     CFN --> S3["S3 docs RAG"]
#     CFN --> API["API Gateway + Lambda<br/>(API bancaria ficticia)"]
#     CFN --> IAM["Roles IAM<br/>KB / Gateway / Harness / Runtime"]
# ```

# %%
import sys
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop" / "common").exists())
sys.path.insert(0, str(ROOT / "workshop" / "common"))

import workshop_kit as kit

kit.banner(0)

# %% [markdown]
# ## Paso 1: ¿Quién soy en AWS?
# Si este paso falla, configura tus credenciales (`aws configure`, `aws sso login` o el rol de SageMaker).

# %%
identity = kit.client("sts").get_caller_identity()
print(f"✅ Cuenta: {identity['Account']}")
print(f"✅ Identidad: {identity['Arn']}")
print(f"✅ Región del workshop: {kit.region()}")

# %% [markdown]
# ## Paso 2: Parámetros del workshop (cdk.json + .env)
# Los mismos parámetros que usa CDK. Para otro cliente solo cambias el archivo `.env`.

# %%
cfg = kit.config()
for key in ("customer_name", "customer_brand", "agent_name", "resource_prefix", "fast_model_id", "default_model_id", "top_model_id"):
    print(f"   {key:<18} = {cfg[key]}")

# %% [markdown]
# ## Paso 3: Infraestructura base desplegada (stack foundation)

# %%
for key, value in kit.outputs().items():
    print(f"   {key:<28} {value}")

# %% [markdown]
# ## Paso 4: ¿Tengo acceso a los modelos?
# Hacemos una llamada mínima (maxTokens=50) a cada modelo que usaremos.

# %%
MODELS = [
    cfg["fast_model_id"],
    cfg["default_model_id"],
    cfg["top_model_id"],
    "us.openai.gpt-5.6-luna",
    "us.openai.gpt-5.6-terra",
    "us.openai.gpt-5.6-sol",
]
bedrock = kit.client("bedrock-runtime")
failed = []
for model_id in MODELS:
    try:  # streaming too: the Harness and the Strands agents use ConverseStream
        stream = bedrock.converse_stream(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "Responde solo: OK"}]}],
            inferenceConfig={"maxTokens": 50},
        )
        list(stream["stream"])
        print(f"   ✅ {model_id}")
    except Exception as exc:  # noqa: BLE001 - show any access problem to the participant
        failed.append(model_id)
        print(f"   ❌ {model_id}: {exc}")

if failed:
    print("\n⚠️ Cambia en .env los modelos con ❌ por otros habilitados en tu cuenta")
    print("   (p. ej. DEFAULT_MODEL_ID=global.anthropic.claude-sonnet-5, TOP_MODEL_ID=us.anthropic.claude-opus-5)")

kit.level_up(0)
