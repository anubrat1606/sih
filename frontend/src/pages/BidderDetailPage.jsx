import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import ForceGraph2D from "react-force-graph-2d";
import { getBidder, postDecision, getAuditLog, getTenderGraph } from "../api";

const STATUS_COLOR = { PASS: "#1a7f37", FAIL: "#cf222e", MISMATCH: "#b08800", UNVERIFIED: "#6e7781" };

export default function BidderDetailPage() {
  const { bidderId } = useParams();
  const [searchParams] = useSearchParams();
  const tenderId = searchParams.get("tender_id");

  const [data, setData] = useState(null);
  const [graph, setGraph] = useState({ nodes: [], links: [] });
  const [auditLog, setAuditLog] = useState([]);
  const [error, setError] = useState("");
  const [decisionMsg, setDecisionMsg] = useState("");
  const graphRef = useRef();

  function load() {
    getBidder(bidderId, tenderId).then(setData).catch((err) => setError(String(err.message || err)));
    getAuditLog(bidderId).then(setAuditLog).catch(() => {});
    if (tenderId) {
      getTenderGraph(tenderId)
        .then((g) =>
          setGraph({
            nodes: g.nodes.map((id) => ({ id, isCurrent: id === bidderId })),
            links: g.edges.map((e) => ({ source: e.from, target: e.to, label: e.shared_attribute })),
          })
        )
        .catch(() => {});
    }
  }

  useEffect(load, [bidderId, tenderId]);

  async function decide(decision) {
    setDecisionMsg("");
    setError("");
    try {
      await postDecision(bidderId, tenderId, "officer_demo", decision);
      setDecisionMsg(`Recorded: ${decision}. Written to the tamper-evident audit log.`);
      load();
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  if (error) return <div className="page"><p className="error">Error: {error}</p></div>;
  if (!data) return <div className="page"><p>Loading...</p></div>;

  const { score } = data;

  return (
    <div className="page">
      <h1>{bidderId}</h1>
      <p className="score-big">{score.compliance_score}/100 — {score.risk_level} RISK</p>
      <p>{score.ai_recommendation}</p>

      <div className="actions">
        <button onClick={() => decide("QUALIFY")}>Qualify</button>
        <button className="danger" onClick={() => decide("DISQUALIFY")}>Disqualify</button>
      </div>
      {decisionMsg && <p className="status">{decisionMsg}</p>}

      <h2>Evidence Trail</h2>
      <table className="evidence-table">
        <thead>
          <tr><th>Field</th><th>Value</th><th>Source</th><th>Status</th><th>Confidence</th><th>Details</th></tr>
        </thead>
        <tbody>
          {score.verification_breakdown.map((c, i) => (
            <tr key={i}>
              <td>{c.field}</td>
              <td>{c.value_extracted || "—"}</td>
              <td>{c.matched_against}</td>
              <td style={{ color: STATUS_COLOR[c.status], fontWeight: 600 }}>{c.status}</td>
              <td>{Math.round(c.confidence * 100)}%</td>
              <td className="details">{c.details}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Collusion Graph {tenderId ? `— Tender ${tenderId}` : ""}</h2>
      <div className="graph-box">
        {graph.nodes.length > 0 ? (
          <ForceGraph2D
            ref={graphRef}
            graphData={graph}
            width={600}
            height={400}
            nodeLabel="id"
            nodeColor={(n) => (n.isCurrent ? "#cf222e" : "#57606a")}
            linkLabel={(l) => l.label}
            linkColor={() => "#b08800"}
            linkDirectionalArrowLength={0}
          />
        ) : (
          <p>No graph data for this tender yet.</p>
        )}
      </div>

      <h2>Audit Log</h2>
      <ul className="audit-list">
        {auditLog.map((e) => (
          <li key={e.entry_id}>
            <strong>{e.decision}</strong> by {e.officer_id} at {e.timestamp} — hash {e.hash.slice(0, 12)}… (prev {e.prev_hash === "genesis" ? "genesis" : e.prev_hash.slice(0, 12) + "…"})
          </li>
        ))}
        {auditLog.length === 0 && <li>No decisions recorded yet.</li>}
      </ul>
    </div>
  );
}
