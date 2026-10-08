import { createContext, useContext, useEffect, useState } from "react";

// Defaults used during local development (npm run dev) when /config.json is absent.
// In AWS, CDK generates /config.json from infrastructure/cdk.json + .env.
const DEFAULTS = {
  customer_id: "acme",
  customer_name: "ACME Corp",
  customer_brand: "ACME Bank",
  agent_name: "AgentBot",
  agent_emoji: "🤖",
  primary_color: "#FF9900",
  secondary_color: "#232F3E",
  accent_color: "#1A9C3E",
  workshop_title: "Agentic AI on AWS - Hands-On Workshop",
  workshop_date: "",
  facilitator_name: "AWS Solutions Architect",
  repo_url: "https://github.com/san99tiago/aws-agentic-ai-fundamentals-workshop",
  aws_region: "us-east-1",
  default_model_id: "global.anthropic.claude-sonnet-5",
  fast_model_id: "us.anthropic.claude-haiku-4-5-20251001-v1:0",
  top_model_id: "us.anthropic.claude-opus-5",
};

const ConfigContext = createContext(DEFAULTS);

export function ConfigProvider({ children }) {
  const [config, setConfig] = useState(DEFAULTS);

  useEffect(() => {
    fetch("/config.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : {}))
      .then((remote) => setConfig({ ...DEFAULTS, ...remote }))
      .catch(() => setConfig(DEFAULTS));
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--brand", config.primary_color);
    root.style.setProperty("--brand-ink", config.secondary_color);
    root.style.setProperty("--brand-accent", config.accent_color);
    document.title = `${config.agent_name} · ${config.workshop_title}`;
  }, [config]);

  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}

export const useConfig = () => useContext(ConfigContext);

// Replace {agent} {brand} {customer} {repo} placeholders in workshop content
export function useT() {
  const c = useConfig();
  return (text = "") =>
    String(text)
      .replaceAll("{agent}", c.agent_name)
      .replaceAll("{brand}", c.customer_brand)
      .replaceAll("{customer}", c.customer_name)
      .replaceAll("{repo}", c.repo_url);
}
