import { createContext, useContext, useEffect, useState } from "react";

const KEY = "agentic-workshop-progress";
const ProgressContext = createContext({ done: {}, toggle: () => {}, level: 0 });

function read() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {};
  }
}

export function ProgressProvider({ children }) {
  const [done, setDone] = useState(read);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(done));
    } catch {
      /* private mode: progress is per page view only */
    }
  }, [done]);
  const toggle = (id, value) => setDone((d) => ({ ...d, [id]: value ?? !d[id] }));
  const level = ["01", "02", "03", "04", "05", "06", "07", "08", "09"].filter((id) => done[id]).length;
  return <ProgressContext.Provider value={{ done, toggle, level }}>{children}</ProgressContext.Provider>;
}

export const useProgress = () => useContext(ProgressContext);
