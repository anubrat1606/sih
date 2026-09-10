// Small shared bits. Not a design system (see satyapramana.md section 2.3
// for what that would look like) -- just enough to keep every screen
// rendering the four-state verdict and the three metrics consistently.

const VERDICT_CLASS = { PASS: "v-pass", FAIL: "v-fail", PARTIAL: "v-partial", UNKNOWN: "v-unknown" };

export function VerdictBadge({ verdict }) {
  return <span className={`badge ${VERDICT_CLASS[verdict] || "v-unknown"}`}>{verdict}</span>;
}

const RISK_CLASS = { LOW: "r-low", MEDIUM: "r-medium", HIGH: "r-high" };

export function RiskBadge({ level }) {
  return <span className={`badge ${RISK_CLASS[level] || "r-medium"}`}>{level} RISK</span>;
}

// A metric is null, never zero, when nothing could be determined -- an em
// dash says that plainly instead of looking like a real 0%. Values already
// arrive on a 0-100 scale (services/core/satyapramana/metrics.py) -- this
// never re-scales them, only rounds for display.
export function Metric({ label, value }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value === null || value === undefined ? "—" : `${Math.round(value)}%`}</div>
    </div>
  );
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return <p className="error">{String(error.message || error)}</p>;
}
