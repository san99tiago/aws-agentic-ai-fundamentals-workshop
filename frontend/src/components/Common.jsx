import { useEffect, useId, useRef, useState } from "react";
import { useT } from "../config.jsx";

let mermaidPromise;
const loadMermaid = () => {
  mermaidPromise ??= import("mermaid").then((m) => m.default);
  return mermaidPromise;
};

export function Mermaid({ chart }) {
  const ref = useRef(null);
  const id = useId().replace(/:/g, "");
  const t = useT();
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const dark = document.documentElement.dataset.theme === "dark";
    loadMermaid().then(async (mermaid) => {
      mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "default", securityLevel: "strict", fontFamily: "inherit" });
      try {
        const { svg } = await mermaid.render(`m${id}${Date.now()}`, t(chart));
        if (!cancelled && ref.current) ref.current.innerHTML = svg;
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    }).catch((e) => {
      if (!cancelled) setError(String(e)); // e.g. stale chunk after a redeploy: show the source instead
    });
    return () => {
      cancelled = true;
    };
  }, [chart, id, t]);

  if (error) return <pre className="code">{t(chart)}</pre>;
  return <div className="mermaid-box" ref={ref} aria-label="Diagrama" />;
}

export function CodeBlock({ code, title }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const text = t(code);
  const copy = () => {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="code-wrap">
      {title && <div className="code-title">{title}</div>}
      <button className="copy-btn" onClick={copy} aria-label="Copiar código">
        {copied ? "✅ Copiado" : "📋 Copiar"}
      </button>
      <pre className="code">
        <code>{text}</code>
      </pre>
    </div>
  );
}

export function Quiz({ questions, onPass }) {
  const t = useT();
  const [answers, setAnswers] = useState({});
  if (!questions?.length) return null;
  const allRight = questions.every((q, i) => answers[i] === q.answer);
  return (
    <div className="quiz">
      {questions.map((q, i) => (
        <div key={i} className="quiz-q">
          <p className="quiz-title">❓ {t(q.q)}</p>
          <div className="quiz-options">
            {q.options.map((opt, j) => {
              const chosen = answers[i] === j;
              const cls = chosen ? (j === q.answer ? "opt right" : "opt wrong") : "opt";
              return (
                <button key={j} className={cls} onClick={() => setAnswers({ ...answers, [i]: j })}>
                  {chosen ? (j === q.answer ? "✅ " : "❌ ") : ""}
                  {t(opt)}
                </button>
              );
            })}
          </div>
        </div>
      ))}
      {allRight && (
        <button className="btn primary" onClick={onPass}>
          🎉 ¡Correcto! Marcar módulo como completado
        </button>
      )}
    </div>
  );
}

export function Chat({ messages, speed = 18 }) {
  const t = useT();
  const [shown, setShown] = useState(0);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!running || shown >= messages.length) {
      if (shown >= messages.length) setRunning(false);
      return undefined;
    }
    const delay = Math.min(2200, 300 + t(messages[shown].text).length * speed);
    const timer = setTimeout(() => setShown((s) => s + 1), delay);
    return () => clearTimeout(timer);
  }, [running, shown, messages, speed, t]);

  return (
    <div className="chat">
      <div className="chat-controls">
        <button className="btn primary" onClick={() => { setShown(0); setRunning(true); }}>
          ▶️ Reproducir conversación real
        </button>
        <button className="btn" onClick={() => { setRunning(false); setShown(messages.length); }}>⏭️ Ver todo</button>
      </div>
      <div className="chat-log" aria-live="polite">
        {messages.slice(0, shown).map((m, i) => (
          <div key={i} className={`bubble ${m.who}`}>
            {(m.who === "user" || m.who === "agent") && <span className="bubble-who">{m.who === "user" ? "👤" : "🤖"}</span>}
            <span>{t(m.text)}</span>
          </div>
        ))}
        {running && shown < messages.length && <div className="typing">●●●</div>}
      </div>
      <p className="muted small">Respuestas reales grabadas durante la validación del workshop (resumidas).</p>
    </div>
  );
}
