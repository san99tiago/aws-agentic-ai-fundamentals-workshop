# 🎤 Guía del facilitador

## Antes del workshop (T-2 días)

1. **Cuentas:** una cuenta AWS por participante o equipo (p. ej., Workshop Studio), región `us-east-1`.
2. **Acceso a modelos de Bedrock:** el notebook 00 valida (en streaming) los modelos de `.env`
   (`FAST_MODEL_ID`, `DEFAULT_MODEL_ID`, `TOP_MODEL_ID`) y `us.openai.gpt-5.6-{luna,terra,sol}`.
   Si alguno falla, cámbialo en `.env`; no hay que tocar código.
3. **Despliegue:** `make deploy-accounts PROFILES="team01 team02 ..."` (el portal solo se despliega en la primera cuenta).
4. **Ensayo:** ejecuta los notebooks 00 → 09 en una cuenta y después `99_cleanup`.
5. **Comparte** con los participantes: la URL del portal, el repo y los valores del `.env`.

## Agenda sugerida (120 min)

| Min | Bloque |
|---|---|
| 0-10 | Contexto: anatomía de un agente, harness, MCP (slides) + módulo 00 |
| 10-30 | 01 LLM I/O · 02 batalla de modelos |
| 30-60 | 03 Guardrails · 04 RAG (lanza la ingesta del 04 al inicio, tarda ~2-3 min) |
| 60-85 | 05 Harness · 06 Gateway + Web Search |
| 85-110 | 07 Runtime · 08 API · 09 agente final |
| 110-120 | Cierre, retos, siguientes pasos y limpieza |

## Lecciones aprendidas

Las encontramos validando el workshop; úsalas como material de enseñanza:

| Tema | Qué pasó | Solución en el workshop |
|---|---|---|
| Trust del rol del Harness | `CREATE_FAILED: Role validation failed` | El Harness corre sobre un Runtime gestionado: el trust permite `harness/*` **y** `runtime/*` |
| Capacidad del perfil `us.` | `ServiceUnavailableException` en streaming con Sonnet 5.5 | Perfil `global.` para `DEFAULT_MODEL_ID` (más capacidad; revisa los requisitos de residencia de datos) |
| `temperature` | Sonnet/Opus 5.5 rechazan `temperature` | No se envía a los modelos de razonamiento |
| Cambio de proveedor a mitad de sesión | OpenAI rechaza los bloques de razonamiento de Claude | El cambio de modelo en la misma sesión se hace entre modelos Claude; para OpenAI se usa una sesión nueva |
| API Gateway como target | `responses is missing` en el OpenAPI | `method_responses` definidos en CDK |
| Managed KB | `RetrieveAndGenerate` no soportado | `AgenticRetrieveStream` (agentic retrieval) |
| Falsos positivos de denied topics | Se bloqueaba "¿qué hago si me piden la clave dinámica?" | Definición precisa (cometer ≠ protegerse) + tema evaluado solo en INPUT |
| Guardrail + tools | Los documentos de la KB disparaban el tema de fraude | En v09 el guardrail es una capa independiente (`ApplyGuardrail` en INPUT y OUTPUT) |
| Private Marketplace en cuentas de workshop | Sonnet/Opus 5.5 respondían en la 1.a llamada y luego `AccessDeniedException ... private marketplace eligibility` | Modelos parametrizados (`DEFAULT_MODEL_ID=global.anthropic.claude-sonnet-5`, `TOP_MODEL_ID=us.anthropic.claude-opus-5`) y el módulo 00 los valida en streaming |
| `deploy.sh` con `source .env` | Fallaba con valores con espacios (p. ej. `CUSTOMER_NAME=ACME Corp`) | El script lee la config con el mismo loader de Python que usa CDK |
| Memoria de largo plazo del Harness | En una cuenta nueva la extracción tardó más de 60 s | El bonus del módulo 05 reintenta hasta 4 veces (cada 45 s) |
| Portal en blanco al cambiar de página | `useEffect(() => window.scrollTo(0, 0))` retornaba la Promise que devuelve `scrollTo` en Chrome reciente, y React la ejecutaba como cleanup (`_ is not a function`) | Efecto con llaves (sin retorno implícito) + Error Boundary para no volver a quedar en blanco |
| Pestañas con un build viejo | Tras un redeploy se pedían chunks JS ya borrados y el fallback SPA devolvía HTML | CloudFront Function solo para rutas sin extensión, `index.html` con `no-cache`, assets `immutable` sin prune y auto-recarga |

## Troubleshooting rápido

- `AccessDeniedException` en un modelo → falta acceso al modelo o hay una SCP en la cuenta.
- Ingesta en `IN_PROGRESS` mucho tiempo → es normal la primera vez (~2-3 min).
- `ConflictException` al recrear el Harness → la eliminación es asíncrona; el notebook espera y reintenta.
- Runtime `CREATE_FAILED` → revisa `/aws/bedrock-agentcore/runtimes/<id>-DEFAULT` en CloudWatch Logs.

# LICENSE

Copyright 2026 Santiago Garcia Arango
