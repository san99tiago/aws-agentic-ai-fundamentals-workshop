# %% [markdown]
# # 📚 Módulo 04 - RAG con Amazon Bedrock Knowledge Bases
#
# **Objetivo:** que el agente responda con información **propia de la empresa** (documentos)
# sin re-entrenar el modelo, usando *Retrieval Augmented Generation* (RAG).
#
# ⏱️ Duración: 15 minutos
#
# Usamos **Bedrock Managed Knowledge Base**: Bedrock administra ingesta, embeddings, el
# almacén vectorial, búsqueda híbrida (semántica + keywords) y reranking. ¡Cero infraestructura!
#
# ```mermaid
# flowchart LR
#     subgraph Ingesta["1️⃣ Ingesta (una vez / sync)"]
#         D["📄 Documentos<br/>S3"] --> P["✂️ Parsing + Chunking"] --> E["🔢 Embeddings"] --> V[("🗄️ Almacén<br/>gestionado")]
#     end
#     subgraph Consulta["2️⃣ Consulta (cada pregunta)"]
#         Q["❓ Pregunta"] --> R["🔎 Retrieve<br/>búsqueda híbrida + rerank"]
#         V --> R
#         R -->|"top-k chunks"| A["🧩 Prompt aumentado"] --> L["🧠 LLM"] --> O["✅ Respuesta + citas"]
#     end
# ```
#
# **¿RAG o Tools?** RAG para conocimiento que cambia poco (FAQs, políticas, manuales).
# Tools/APIs para datos en tiempo real (saldos, transacciones) → módulo 08.

# %%
import sys
from pathlib import Path

ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "workshop" / "common").exists())
sys.path.insert(0, str(ROOT / "workshop" / "common"))

import workshop_kit as kit

kit.banner(4)
agent_ctl = kit.client("bedrock-agent")
agent_rt = kit.client("bedrock-agent-runtime")
runtime = kit.client("bedrock-runtime")
out = kit.outputs()
pack = kit.customer()
MODEL_ID = kit.config()["default_model_id"]
QUESTIONS = pack["examples"]["m04_rag"]

# %% [markdown]
# ## Paso 1: Sin RAG, el modelo NO conoce tus productos 🤷
# Los productos del workshop son ficticios: el modelo no puede saberlos (y podría inventar).

# %%
response = runtime.converse(
    modelId=MODEL_ID,
    system=[{"text": pack["agent_persona"]}],
    messages=[{"role": "user", "content": [{"text": QUESTIONS[0]}]}],
    inferenceConfig={"maxTokens": 300},
)
kit.show("Sin RAG", kit.converse_text(response), "🤷")

# %% [markdown]
# ## Paso 2: Los documentos ya están en S3 (los subió CDK)

# %%
s3 = kit.client("s3")
DOCS_BUCKET = out["KnowledgeBaseDocsBucketName"]
for obj in s3.list_objects_v2(Bucket=DOCS_BUCKET, Prefix="knowledge-base/").get("Contents", []):
    print(f"   📄 s3://{DOCS_BUCKET}/{obj['Key']} ({obj['Size']} bytes)")

# %% [markdown]
# ## Paso 3: Crear la Managed Knowledge Base + Data Source (S3)
# Solo necesitamos: nombre, rol IAM y el bucket. Bedrock elige y administra el modelo de embeddings.

# %%
KB_NAME = kit.name("kb")
existing = [kb for kb in agent_ctl.list_knowledge_bases()["knowledgeBaseSummaries"] if kb["name"] == KB_NAME]
if existing:
    kb_id = existing[0]["knowledgeBaseId"]
    print(f"♻️ Knowledge Base existente: {kb_id}")
else:
    kb_id = agent_ctl.create_knowledge_base(
        name=KB_NAME,
        description=pack["knowledge_base_description"],
        roleArn=out["KnowledgeBaseRoleArn"],
        knowledgeBaseConfiguration={
            "type": "MANAGED",
            "managedKnowledgeBaseConfiguration": {"embeddingModelType": "MANAGED"},
        },
    )["knowledgeBase"]["knowledgeBaseId"]
    print(f"✅ Knowledge Base creada: {kb_id}")

kit.wait_for(lambda: agent_ctl.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]["status"], ("ACTIVE",), ("FAILED",), "Knowledge Base")

data_sources = agent_ctl.list_data_sources(knowledgeBaseId=kb_id)["dataSourceSummaries"]
if data_sources:
    ds_id = data_sources[0]["dataSourceId"]
else:
    ds_id = agent_ctl.create_data_source(
        knowledgeBaseId=kb_id,
        name=kit.name("kb-docs"),
        description="Documentos FAQ del customer pack (S3)",
        dataSourceConfiguration={
            "type": "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
            "managedKnowledgeBaseConnectorConfiguration": {
                "connectorParameters": {
                    "type": "S3",
                    "version": "1",
                    "connectionConfiguration": {"bucketName": DOCS_BUCKET, "bucketOwnerAccountId": kit.account_id()},
                    "filterConfiguration": {"inclusionPrefixes": ["knowledge-base/"]},
                }
            },
        },
    )["dataSource"]["dataSourceId"]
    print(f"✅ Data source creado: {ds_id}")

kit.wait_for(
    lambda: agent_ctl.get_data_source(knowledgeBaseId=kb_id, dataSourceId=ds_id)["dataSource"]["status"],
    ("AVAILABLE",), ("FAILED", "DELETE_UNSUCCESSFUL"), "Data source", every=15,
)
kit.save_state(kb_id=kb_id, kb_data_source_id=ds_id)

# %% [markdown]
# ## Paso 4: Ingesta 🔄 (parsing → chunking → embeddings → índice)

# %%
job_id = agent_ctl.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)["ingestionJob"]["ingestionJobId"]
kit.wait_for(
    lambda: agent_ctl.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job_id)["ingestionJob"]["status"],
    ("COMPLETE",), ("FAILED", "STOPPED"), "Ingesta", every=15,
)
stats = agent_ctl.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job_id)["ingestionJob"]["statistics"]
print("📊 Estadísticas:", {k: v for k, v in stats.items() if v})

# %% [markdown]
# ## Paso 5: Retrieve 🔎 (solo búsqueda, sin LLM)
# Mira los *chunks* recuperados, su score y el documento de origen.

# %%
results = agent_rt.retrieve(
    knowledgeBaseId=kb_id,
    retrievalQuery={"text": QUESTIONS[0]},
    retrievalConfiguration={"managedSearchConfiguration": {"numberOfResults": 3}},
)["retrievalResults"]
for i, r in enumerate(results, 1):
    source = r.get("metadata", {}).get("_document_title", r.get("documentId"))
    print(f"\n#{i} score={r.get('score', 0):.3f}  📄 {source}\n   {r['content']['text'][:250]}...")

# %% [markdown]
# ## Paso 6: Agentic Retrieval ✨ (RAG multi-paso + respuesta generada)
# Exclusivo de Managed KB: un agente interno **planea** sub-consultas, recupera, evalúa,
# re-rankea y genera la respuesta. Ideal para preguntas complejas (multi-hop).
# Observa los pasos (`Planning`, `Retrieval`...) en el stream.

# %%
def agentic_retrieve(question: str) -> None:
    stream = agent_rt.agentic_retrieve_stream(
        messages=[{"role": "user", "content": {"text": question}}],
        retrievers=[{"configuration": {"knowledgeBase": {"knowledgeBaseId": kb_id}}, "description": pack["knowledge_base_description"]}],
        agenticRetrieveConfiguration={"foundationModelType": "MANAGED", "rerankingModelType": "MANAGED", "maxAgentIteration": 3},
        generateResponse=True,
    )["stream"]
    print(f"\n❓ {question}")
    answer_started = False
    for event in stream:
        if "traceEvent" in event:
            attrs = event["traceEvent"]["attributes"]
            if attrs["status"] != "IN_PROGRESS":
                print(f"   🧭 {attrs['step']}: {attrs['status']} - {attrs['message'][:110]}")
        elif "responseEvent" in event:  # the generated answer, streamed token by token
            if not answer_started:
                print("📚 ", end="")
                answer_started = True
            print(event["responseEvent"]["text"], end="", flush=True)
        elif "result" in event:
            citations = event["result"].get("generatedResponse", {}).get("citations", [])
            print(f"\n   🔗 {len(event['result']['results'])} chunks recuperados | {len(citations)} citas")


for question in QUESTIONS:
    agentic_retrieve(question)

# %% [markdown]
# ## Paso 7: RAG "manual" (control total del prompt y del modelo)
# Recuperas chunks y construyes tú el prompt: así funciona por dentro y así lo haremos en los agentes.

# %%
question = QUESTIONS[1]
chunks = agent_rt.retrieve(
    knowledgeBaseId=kb_id,
    retrievalQuery={"text": question},
    retrievalConfiguration={"managedSearchConfiguration": {"numberOfResults": 3}},
)["retrievalResults"]
context = "\n\n".join(f"<documento>{c['content']['text']}</documento>" for c in chunks)
response = runtime.converse(
    modelId=kit.config()["fast_model_id"],
    system=[{"text": pack["agent_persona"] + "\nResponde SOLO con base en los documentos. Si no esta en ellos, dilo."}],
    messages=[{"role": "user", "content": [{"text": f"{context}\n\nPregunta: {question}"}]}],
    inferenceConfig={"maxTokens": 400},
)
kit.show(f"{kit.agent_name()} con RAG manual", kit.converse_text(response), "📚")
print(f"🪙 Solo enviamos {response['usage']['inputTokens']} tokens de contexto relevante (no todos los documentos).")

# %%
kit.level_up(4)
