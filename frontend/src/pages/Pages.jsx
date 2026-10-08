import { Link, useParams } from "react-router-dom";
import { useConfig, useT } from "../config.jsx";
import { MODULES } from "../data/modules.js";
import { useProgress } from "../progress.jsx";
import Mascot from "../components/Mascot.jsx";
import { CodeBlock, Mermaid, Quiz } from "../components/Common.jsx";
import { WIDGETS } from "../widgets/Widgets.jsx";

const MAIN = MODULES.filter((m) => m.id !== "99");

// draw.io architecture diagrams (assets/diagrams, exported at DPI-400)
const DIAGRAMS = {
  "00": "00-setup", "01": "01-bedrock-llms", "02": "02-model-battle", "03": "03-guardrails", "04": "04-rag",
  "05": "05-harness", "06": "06-gateway-websearch", "07": "07-runtime-strands", "08": "08-runtime-gateway-api", "09": "09-final-agent",
};

function AwsDiagram({ id }) {
  const stem = DIAGRAMS[id];
  if (!stem) return null;
  return (
    <figure className="aws-diagram">
      <a href={`/diagrams/${stem}.png`} target="_blank" rel="noreferrer" title="Abrir en alta resolución">
        <img src={`/diagrams/${stem}.png`} alt={`Arquitectura AWS del módulo ${id}`} loading="lazy" />
      </a>
      <figcaption className="row">
        <a className="btn" href={`/diagrams/${stem}.png`} target="_blank" rel="noreferrer">🔍 Alta resolución (PNG)</a>
        <a className="btn" href={`/diagrams/${stem}.drawio`} download>📐 Descargar .drawio (editable)</a>
      </figcaption>
    </figure>
  );
}
const TOTAL_MIN = MODULES.reduce((s, m) => s + m.duration, 0);

const ARCHITECTURE = `flowchart LR
  subgraph IDE["💻 IDE participante"]
    NB["📓 Notebooks 00-09"]
  end
  subgraph BR["Amazon Bedrock"]
    M["🧠 Claude · OpenAI"]
    GR["🛡️ Guardrails"]
    KB["📚 Managed KB"]
  end
  subgraph AC["Amazon Bedrock AgentCore"]
    H["🤖 Harness"]
    RT["🚀 Runtime (Strands)"]
    GW["🌐 Gateway MCP"]
  end
  subgraph CDK["🏗️ Base CDK (pre-desplegada)"]
    S3["S3 docs + artifacts"]
    API["API GW + λ<br/>API bancaria"]
    IAM["Roles IAM"]
  end
  NB --> M & GR & KB & H & RT
  H --> GW
  RT --> GW
  RT --> GR
  GW --> API
  GW --> KB
  GW --> WS["🔎 Web Search"]
  KB --> S3
  CF["☁️ CloudFront + S3 (OAC)<br/>este portal"] -.-> NB`;

export function Home() {
  const c = useConfig();
  const t = useT();
  const { done, level } = useProgress();
  return (
    <>
      <section className="hero">
        <div>
          <p className="eyebrow">{c.customer_name} × AWS {c.workshop_date && `· ${c.workshop_date}`}</p>
          <h1>{c.workshop_title}</h1>
          <p className="lead">
            Construye paso a paso a <b>{c.agent_name}</b> {c.agent_emoji}: de un LLM que solo habla a un agente productivo con
            Guardrails, RAG, herramientas MCP y despliegue serverless en <b>Amazon Bedrock AgentCore</b>.
          </p>
          <div className="row">
            <Link className="btn primary" to="/modulo/00">🚀 Empezar</Link>
            <Link className="btn" to="/arquitectura">🏗️ Ver arquitectura</Link>
            <a className="btn" href={c.repo_url} target="_blank" rel="noreferrer">💻 Repositorio</a>
          </div>
          <div className="stats">
            <div className="stat"><b>{MAIN.length}</b><span>módulos</span></div>
            <div className="stat"><b>~{Math.ceil(TOTAL_MIN / 60)} h</b><span>duración ({TOTAL_MIN} min + Q&amp;A)</span></div>
            <div className="stat"><b>{level}/9</b><span>tu progreso</span></div>
          </div>
        </div>
        <div className="hero-mascot">
          <Mascot level={level} size={240} />
          <p className="mascot-caption">{c.agent_name} v{level} · {MODULES.find((m) => m.level === level && m.id !== "99")?.stage}</p>
        </div>
      </section>

      <section>
        <h2>🧬 La evolución de {c.agent_name}</h2>
        <p className="muted">Cada módulo le da un superpoder nuevo. Completa el quiz de cada módulo para hacerlo evolucionar.</p>
        <div className="timeline">
          {MAIN.map((m) => (
            <Link key={m.id} to={`/modulo/${m.id}`} className={`tl-item ${done[m.id] ? "done" : ""}`}>
              <div className="tl-mascot"><Mascot level={m.level} size={70} animate={false} /></div>
              <div className="tl-body">
                <span className="tl-id">Módulo {m.id} · {m.duration} min</span>
                <b>{m.emoji} {m.stage}</b>
                <span className="small">{t(m.title)}</span>
              </div>
              {done[m.id] && <span className="tl-check">✅</span>}
            </Link>
          ))}
        </div>
      </section>

      <section className="grid3">
        <div className="card"><h3>👩‍💻 Qué necesitas</h3><ul><li>Cuenta AWS del workshop (us-east-1)</li><li>VS Code o SageMaker Studio</li><li>Python 3.12+ (Poetry o pip)</li></ul></div>
        <div className="card"><h3>🧭 Cómo funciona</h3><ul><li>Lee el concepto y el diagrama aquí</li><li>Ejecuta el notebook celda por celda</li><li>Responde el quiz y evoluciona</li></ul></div>
        <div className="card"><h3>🔐 Seguridad primero</h3><ul><li>APIs privadas con IAM (SigV4)</li><li>Buckets privados + CloudFront OAC</li><li>Roles least-privilege con confused-deputy</li></ul></div>
      </section>
    </>
  );
}

export function ModulePage() {
  const { id } = useParams();
  const t = useT();
  const c = useConfig();
  const { done, toggle } = useProgress();
  const index = MODULES.findIndex((m) => m.id === id);
  const m = MODULES[index] ?? MODULES[0];
  const prev = MODULES[index - 1];
  const next = MODULES[index + 1];
  const Widget = m.widget ? WIDGETS[m.widget] : null;

  return (
    <article className="module">
      <header className="module-head">
        <Mascot level={m.level} size={120} />
        <div>
          <p className="eyebrow">Módulo {m.id} · ⏱️ {m.duration} min · {c.agent_name} v{m.level} {m.emoji} {m.stage}</p>
          <h1>{t(m.title)}</h1>
          <p className="lead">{t(m.objective)}</p>
          <p className="muted small">📓 <code>{m.folder}/{m.file}</code> (también disponible como <code>.py</code>)</p>
        </div>
      </header>

      <section>
        <h2>💡 Conceptos clave</h2>
        <div className="concepts">
          {m.concepts.map(([title, text]) => (
            <div key={title} className="concept"><b>{t(title)}</b><p>{t(text)}</p></div>
          ))}
        </div>
      </section>

      {DIAGRAMS[m.id] && (
        <section>
          <h2>🏛️ Arquitectura AWS del módulo</h2>
          <AwsDiagram id={m.id} />
        </section>
      )}

      {m.diagram && (
        <section>
          <h2>🗺️ Flujo conceptual</h2>
          <Mermaid chart={m.diagram} />
        </section>
      )}

      {Widget && (
        <section>
          <h2>🎮 Interactivo</h2>
          <Widget />
        </section>
      )}

      <section>
        <h2>🪜 Paso a paso</h2>
        <ol className="steps">
          {m.steps.map((s, i) => (
            <li key={i}>
              <h3>{t(s.title)}</h3>
              <CodeBlock code={s.code} />
            </li>
          ))}
        </ol>
      </section>

      {m.lesson && <div className="callout warn"><b>🧠 Lección aprendida:</b> {t(m.lesson)}</div>}
      {m.challenge && <div className="callout"><b>🎯 Reto:</b> {t(m.challenge)}</div>}

      {m.quiz?.length > 0 && (
        <section>
          <h2>🏁 Quiz para evolucionar</h2>
          {done[m.id] ? (
            <div className="callout safe">✅ ¡Módulo completado! {c.agent_name} evolucionó a {m.emoji} {m.stage}. <button className="link" onClick={() => toggle(m.id, false)}>reiniciar</button></div>
          ) : (
            <Quiz questions={m.quiz} onPass={() => toggle(m.id, true)} />
          )}
        </section>
      )}

      {m.docs?.length > 0 && (
        <section>
          <h2>📖 Documentación oficial</h2>
          <ul className="docs">{m.docs.map(([label, url]) => <li key={url}><a href={url} target="_blank" rel="noreferrer">{label} ↗</a></li>)}</ul>
        </section>
      )}

      <nav className="pager">
        {prev ? <Link className="btn" to={`/modulo/${prev.id}`}>◀️ {prev.id} {prev.emoji} {t(prev.title)}</Link> : <span />}
        {next && <Link className="btn primary" to={`/modulo/${next.id}`}>{next.id} {next.emoji} {t(next.title)} ▶️</Link>}
      </nav>
    </article>
  );
}

export function Architecture() {
  const c = useConfig();
  return (
    <article className="module">
      <h1>🏗️ Arquitectura completa del workshop</h1>
      <p className="lead">Qué despliega CDK (base compartida), qué creas tú en los notebooks y cómo se conecta todo para {c.agent_name}.</p>
      <h2>🦸 Arquitectura final (módulo 09)</h2>
      <AwsDiagram id="09" />
      <h2>🏗️ Infraestructura base (CDK)</h2>
      <AwsDiagram id="00" />
      <h2>🗺️ Mapa conceptual completo</h2>
      <Mermaid chart={ARCHITECTURE} />
      <div className="grid2">
        <div className="card">
          <h3>🏗️ CDK (pre-desplegado por el facilitador)</h3>
          <ul>
            <li>S3 privado con los documentos del cliente (RAG)</li>
            <li>S3 privado para los paquetes del agente (Runtime)</li>
            <li>API bancaria ficticia: API Gateway (AWS_IAM) + Lambda</li>
            <li>Roles IAM: Knowledge Base, Gateway, Harness, Runtime</li>
            <li>Este portal: S3 privado + CloudFront (OAC)</li>
          </ul>
        </div>
        <div className="card">
          <h3>📓 Notebooks (lo creas tú)</h3>
          <ul>
            <li>03 · Guardrail (tier STANDARD)</li>
            <li>04 · Managed Knowledge Base + data source S3</li>
            <li>05 · AgentCore Harness</li>
            <li>06 · AgentCore Gateway + targets (Web, API, KB)</li>
            <li>07-09 · AgentCore Runtime (Strands, 3 versiones)</li>
          </ul>
        </div>
      </div>
      <h2>⚙️ Parametrizado para cualquier cliente</h2>
      <CodeBlock title=".env (git-ignored) → sobrescribe infrastructure/cdk.json" code={`CUSTOMER_ID=${c.customer_id}
CUSTOMER_NAME=${c.customer_name}
AGENT_NAME=${c.agent_name}
PRIMARY_COLOR=${c.primary_color}
RESOURCE_PREFIX=<prefijo>
DEFAULT_MODEL_ID=${c.default_model_id}`} />
    </article>
  );
}
