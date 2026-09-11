import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getDashboard } from "../api";
import { ErrorBox } from "../components";

const RISK_ORDER = ["LOW", "MEDIUM", "HIGH"];

// Horizontal stacked bar, segment widths genuinely proportional to counts --
// a tender with 0 MEDIUM must render a 0-width segment, never an evenly
// split third. Self-contained here on purpose: round 4's chart primitives
// (Rishika, R2) will replace this once they land, without this page's data
// logic changing at all.
function RiskDistributionBar({ counts }) {
  const total = RISK_ORDER.reduce((sum, level) => sum + counts[level], 0);
  if (total === 0) return <p className="hint">No bidders registered yet.</p>;
  return (
    <div className="risk-bar">
      {RISK_ORDER.map((level) => {
        const pct = (counts[level] / total) * 100;
        if (pct === 0) return null;
        return (
          <div key={level} className={`risk-bar-segment risk-bar-${level.toLowerCase()}`}
               style={{ width: `${pct}%` }} title={`${level}: ${counts[level]}`} />
        );
      })}
    </div>
  );
}

export default function DashboardPage() {
  const [body, setBody] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getDashboard().then(setBody).catch(setError);
  }, []);

  return (
    <div className="page">
      <h1>Mission Control</h1>
      <p className="hint">Every tender and bidder in the system, at a glance.</p>
      <ErrorBox error={error} />
      {body && (
        <>
          <div className="stat-tiles">
            <div className="stat-tile"><div className="stat-tile-value mono">{body.tender_count}</div><div className="stat-tile-label">Tenders</div></div>
            <div className="stat-tile"><div className="stat-tile-value mono">{body.bidder_count}</div><div className="stat-tile-label">Bidders</div></div>
            <div className="stat-tile"><div className="stat-tile-value mono">{body.flagged_bidder_count}</div><div className="stat-tile-label">Collusion-flagged</div></div>
            <div className="stat-tile">
              <div className="stat-tile-value mono">{body.capabilities.live_count}</div>
              <div className="stat-tile-label">Authorities live</div>
            </div>
          </div>

          <h2>Risk distribution</h2>
          <RiskDistributionBar counts={body.risk_distribution} />
          <p className="hint">
            {RISK_ORDER.map((level) => `${level} ${body.risk_distribution[level]}`).join(" · ")}
          </p>

          <h2>Recent decisions</h2>
          {body.recent_decisions.length === 0 ? (
            <p className="hint">No decisions recorded yet.</p>
          ) : (
            <table className="evidence-table">
              <thead><tr><th>When</th><th>Tender</th><th>Bidder</th><th>Decision</th><th>Officer</th></tr></thead>
              <tbody>
                {body.recent_decisions.map((d, i) => (
                  <tr key={i}>
                    <td className="mono">{new Date(d.occurred_at).toLocaleString()}</td>
                    <td><Link to={`/tenders/${encodeURIComponent(d.tender_id)}`}>{d.tender_id}</Link></td>
                    <td>
                      <Link to={`/bidders/${encodeURIComponent(d.bidder_id)}?tender_id=${encodeURIComponent(d.tender_id)}`} className="mono">
                        {d.bidder_id}
                      </Link>
                    </td>
                    <td className={d.decision === "QUALIFY" ? "status" : "error"}>{d.decision}</td>
                    <td className="mono">{d.officer}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Verification capabilities</h2>
          <p className="hint">
            {body.capabilities.live_count} of {body.capabilities.capabilities.filter((c) => c.capability_id).length} live.{" "}
            <Link to="/">Full detail →</Link>
          </p>
        </>
      )}
    </div>
  );
}
