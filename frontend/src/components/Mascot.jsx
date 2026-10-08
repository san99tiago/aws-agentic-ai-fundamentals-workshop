// The workshop agent mascot. It EVOLVES with the level (0-9): new accessories per module.
export default function Mascot({ level = 0, size = 160, animate = true }) {
  if (level === 0) {
    return (
      <svg width={size} height={size} viewBox="0 0 200 200" className={animate ? "mascot float" : "mascot"} role="img" aria-label="Huevo del agente">
        <ellipse cx="100" cy="185" rx="45" ry="8" fill="var(--shadow)" />
        <path d="M100 20 C55 20 40 100 45 130 C50 170 75 180 100 180 C125 180 150 170 155 130 C160 100 145 20 100 20Z" fill="var(--brand)" stroke="var(--ink)" strokeWidth="4" />
        <path d="M70 95 L85 110 L100 92 L115 110 L130 95" fill="none" stroke="var(--ink)" strokeWidth="4" strokeLinecap="round" />
        <circle cx="80" cy="70" r="6" fill="#fff" opacity="0.7" />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 200 200" className={animate ? "mascot float" : "mascot"} role="img" aria-label={`Agente nivel ${level}`}>
      <ellipse cx="100" cy="188" rx="50" ry="7" fill="var(--shadow)" />
      {level >= 9 && <path d="M55 95 L30 175 L100 160 L170 175 L145 95Z" fill="var(--brand-accent)" stroke="var(--ink)" strokeWidth="3" />}
      {/* antenna: grows a signal when connected to the web */}
      <line x1="100" y1="38" x2="100" y2="18" stroke="var(--ink)" strokeWidth="4" />
      <circle cx="100" cy="15" r="7" fill={level >= 6 ? "var(--brand-accent)" : "var(--brand)"} stroke="var(--ink)" strokeWidth="3" className={level >= 6 ? "pulse" : ""} />
      {level >= 6 && <path d="M80 10 Q100 -5 120 10" fill="none" stroke="var(--brand-accent)" strokeWidth="3" />}
      {/* head */}
      <rect x="55" y="38" width="90" height="70" rx="22" fill="var(--brand)" stroke="var(--ink)" strokeWidth="4" />
      <rect x="68" y="52" width="64" height="38" rx="14" fill="var(--ink)" />
      <circle cx="86" cy="71" r={level >= 2 ? 7 : 5} fill="var(--brand-accent)" className="blink" />
      <circle cx="114" cy="71" r={level >= 2 ? 7 : 5} fill="var(--brand-accent)" className="blink" />
      {level >= 4 && <rect x="76" y="62" width="48" height="18" rx="6" fill="none" stroke="#fff" strokeWidth="2" opacity="0.8" />}
      <path d="M88 83 Q100 90 112 83" fill="none" stroke="var(--brand-accent)" strokeWidth="3" strokeLinecap="round" />
      {/* body */}
      <rect x="65" y="110" width="70" height="55" rx="16" fill="var(--brand)" stroke="var(--ink)" strokeWidth="4" />
      {level >= 7 ? (
        <text x="100" y="146" textAnchor="middle" fontSize="24">🚀</text>
      ) : (
        <circle cx="100" cy="137" r="10" fill="var(--ink)" />
      )}
      {/* arms */}
      <path d="M65 125 Q45 135 48 155" fill="none" stroke="var(--ink)" strokeWidth="5" strokeLinecap="round" />
      <path d="M135 125 Q155 135 152 155" fill="none" stroke="var(--ink)" strokeWidth="5" strokeLinecap="round" />
      {level >= 3 && (
        <g transform="translate(28 140)">
          <path d="M0 0 L22 -6 L44 0 L40 24 Q22 40 4 24Z" fill="var(--brand-accent)" stroke="var(--ink)" strokeWidth="3" />
          <path d="M14 14 L20 20 L32 8" fill="none" stroke="#fff" strokeWidth="3" />
        </g>
      )}
      {level >= 5 && <text x="160" y="160" textAnchor="middle" fontSize="26">{level >= 8 ? "🏦" : "🧮"}</text>}
      {level === 1 && <text x="150" y="40" fontSize="22">💬</text>}
      {level >= 4 && level < 9 && <text x="35" y="45" fontSize="22">📚</text>}
      {level >= 9 && <text x="148" y="40" fontSize="26">⭐</text>}
      {/* legs */}
      <rect x="78" y="165" width="14" height="18" rx="5" fill="var(--ink)" />
      <rect x="108" y="165" width="14" height="18" rx="5" fill="var(--ink)" />
    </svg>
  );
}
