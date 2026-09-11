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

// Bid Autopsy: FATAL is positive evidence against the bidder (re-checking the
// same fact won't change it); CURABLE is an absence of evidence or a
// procedural gap (new evidence could flip it). Reuses the verdict palette --
// FATAL reads the same as a FAIL, CURABLE the same as a PARTIAL -- rather
// than inventing a second colour vocabulary for the same underlying idea.
export function ClassificationBadge({ classification }) {
  const cls = classification === "FATAL" ? "v-fail" : classification === "CURABLE" ? "v-partial" : "v-unknown";
  return <span className={`badge ${cls}`}>{classification}</span>;
}

// Compliance Repair: who can actually act on this gap. SYSTEM means "we
// haven't configured this yet" -- never told to a bidder as their problem.
export function ActionableBadge({ actionableBy }) {
  return <span className={`badge ${actionableBy === "BIDDER" ? "v-pass" : "v-unknown"}`}>{actionableBy}</span>;
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
