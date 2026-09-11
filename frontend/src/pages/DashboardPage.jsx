import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getDashboard } from "../api";
import { RiskDistributionBar, StatTile } from "../charts";
import { ErrorBox } from "../components";
import { SkeletonLine, SkeletonTable } from "../Skeleton";

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
      {!body && !error && (
        <div className="stack">
          <SkeletonLine width="80%" />
          <SkeletonTable rows={3} columns={5} />
        </div>
      )}
      {body && (
        <>
          <div className="stat-tiles">
            <StatTile label="Tenders" value={body.tender_count} />
            <StatTile label="Bidders" value={body.bidder_count} />
            <StatTile label="Collusion-flagged" value={body.flagged_bidder_count} />
            <StatTile label="Authorities live" value={body.capabilities.live_count} />
          </div>

          <h2>Risk distribution</h2>
          <RiskDistributionBar
            low={body.risk_distribution.LOW}
            medium={body.risk_distribution.MEDIUM}
            high={body.risk_distribution.HIGH}
          />

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
