import { Component, StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { ConfigProvider, useConfig } from "./config.jsx";
import { ProgressProvider, useProgress } from "./progress.jsx";
import { MODULES } from "./data/modules.js";
import { Architecture, Home, ModulePage } from "./pages/Pages.jsx";
import "./styles.css";

const RELOAD_FLAG = "agentic-workshop-reloaded";
const isStaleBuildError = (error) => /dynamically imported module|Importing a module script failed|Failed to fetch|ChunkLoadError|MIME type/i.test(String(error?.message || error));

function reloadOnce() {
  try {
    if (sessionStorage.getItem(RELOAD_FLAG)) return false;
    sessionStorage.setItem(RELOAD_FLAG, "1");
  } catch {
    /* ignore */
  }
  window.location.reload();
  return true;
}

// A new deploy replaced the chunks this tab was built with: reload to get the new version
window.addEventListener("vite:preloadError", (event) => {
  event.preventDefault();
  reloadOnce();
});
window.addEventListener("load", () => setTimeout(() => {
  try { sessionStorage.removeItem(RELOAD_FLAG); } catch { /* ignore */ }
}, 5000));

// Never leave the participant with a blank page
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidCatch(error) {
    if (isStaleBuildError(error)) reloadOnce();
    console.error(error);
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="content">
        <div className="callout warn">
          <h2>😅 Algo falló al mostrar esta página</h2>
          <p className="small"><code>{String(this.state.error?.message || this.state.error)}</code></p>
          <div className="row">
            <button className="btn primary" onClick={() => window.location.reload()}>🔄 Recargar</button>
            <a className="btn" href="/">🏠 Ir al inicio</a>
          </div>
        </div>
      </div>
    );
  }
}

function getInitialTheme() {
  try {
    const saved = localStorage.getItem("agentic-workshop-theme");
    if (saved) return saved;
  } catch {
    /* ignore */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function ScrollTop() {
  const { pathname } = useLocation();
  // Braces matter: modern browsers return a Promise from scrollTo, and React would
  // treat an implicitly returned value as the effect cleanup function.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function Layout() {
  const c = useConfig();
  const { level } = useProgress();
  const [theme, setTheme] = useState(getInitialTheme);
  const [menu, setMenu] = useState(false);
  const { pathname } = useLocation();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("agentic-workshop-theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  return (
    <div className="app">
      <ScrollTop />
      <header className="topbar">
        <Link to="/" className="brand" onClick={() => setMenu(false)}>
          <span className="brand-dot">{c.agent_emoji}</span>
          <span>{c.agent_name} <small>· {c.customer_brand}</small></span>
        </Link>
        <div className="topbar-right">
          <span className="level-pill" title="Tu progreso">v{level}/9</span>
          <button className="icon-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Cambiar tema">
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
          <button className="icon-btn menu-btn" onClick={() => setMenu(!menu)} aria-label="Menú">☰</button>
        </div>
      </header>
      <div className="shell">
        <nav className={`sidebar ${menu ? "open" : ""}`} onClick={() => setMenu(false)}>
          <NavLink to="/" end>🏠 Inicio</NavLink>
          <NavLink to="/arquitectura">🏗️ Arquitectura</NavLink>
          <div className="nav-sep">Módulos</div>
          {MODULES.map((m) => (
            <NavLink key={m.id} to={`/modulo/${m.id}`}>
              <span className="nav-id">{m.id}</span> {m.emoji} {m.stage}
            </NavLink>
          ))}
        </nav>
        <main className="content">
          <ErrorBoundary key={pathname}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/arquitectura" element={<Architecture />} />
            <Route path="/modulo/:id" element={<ModulePage />} />
            <Route path="*" element={<Home />} />
          </Routes>
          </ErrorBoundary>
          <footer className="footer">
            {c.workshop_title} · {c.customer_name} × AWS · Facilitador: {c.facilitator_name} · Contenido de entrenamiento con datos ficticios.
          </footer>
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <ErrorBoundary>
    <ConfigProvider>
      <ProgressProvider>
        <BrowserRouter>
          <Layout />
        </BrowserRouter>
      </ProgressProvider>
    </ConfigProvider>
    </ErrorBoundary>
  </StrictMode>,
);
