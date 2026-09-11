import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ForceGraph2D from "react-force-graph-2d";
import { adoptRulePack, getCollusionEdges, getTender, getTenderCollusion, listTenderBidders } from "../api";
import { roleAtLeast, useAuth } from "../authContext";
import { ErrorBox, Metric, RiskBadge } from "../components";
import RulePackBuilder from "../RulePackBuilder";
import { cssVar } from "../theme";

export default function TenderDashboardPage() {
  const { tenderId } = useParams();
  const { session } = useAuth();
  const canAdopt = roleAtLeast(session.role, "SENIOR_OFFICER");
  const [bidders, setBidders] = useState(null);
  const [collusion, setCollusion] = useState(null);
  const [edges, setEdges] = useState(null);
  const [error, setError] = useState(null);
  const [adoptResult, setAdoptResult] = useState(null);
  const [violations, setViolations] = useState(null);
  const [adopting, setAdopting] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [tender, setTender] = useState(null);
  const graphRef = useRef();

  // Which bidder ids are actually connected to the selected node, so a
  // click can dim everything else instead of leaving the whole graph
  // equally weighted -- react-force-graph-2d gives pan/zoom for free
  // (d3-zoom under the hood), this is the one thing it doesn't.
  function connectedTo(bidderId, edgeList) {
    const linked = new Set([bidderId]);
    edgeList.forEach((e) => {
      if (e.bidder_a === bidderId) linked.add(e.bidder_b);
      if (e.bidder_b === bidderId) linked.add(e.bidder_a);
    });
    return linked;
  }

  function load() {
    getTender(tenderId).then(setTender).catch(() => setTender(null));
    listTenderBidders(tenderId).then((body) => setBidders(body.bidders)).catch(setError);
    getTenderCollusion(tenderId).then((body) => setCollusion(body.bidders)).catch(setError);
    getCollusionEdges(tenderId).then((body) => setEdges(body.edges)).catch(setError);
  }

  useEffect(load, [tenderId]);

  async function handleAdopt(pack, parseError) {
    setError(null);
    setViolations(null);
    setAdoptResult(null);
    if (parseError) {
      setError(parseError);
      return;
    }
    setAdopting(true);
    try {
      setAdoptResult(await adoptRulePack(tenderId, pack));
    } catch (err) {
      if (err.detail?.violations) setViolations(err.detail.violations);
      else setError(err);
    } finally {
      setAdopting(false);
    }
  }

  return (
    <div className="page">
      <h1>{tender?.title || <span className="mono">{tenderId}</span>}</h1>
      {tender?.title ? (
        <p className="hint">
          <span className="mono">{tenderId}</span> · {tender.issuing_authority}
          {tender.bid_submission_deadline && ` · bids close ${tender.bid_submission_deadline}`}
        </p>
      ) : (
        <p className="hint">No tender metadata on file -- this tender exists only because a bidder registered on it.</p>
      )}
      {tender?.description && <p className="hint">{tender.description}</p>}
      <ErrorBox error={error} />

      <h2>Bidders</h2>
      {bidders && bidders.length === 0 && <p className="hint">No bidders registered yet.</p>}
      <div className="card-grid">
        {bidders && bidders.map((b) => (
          <Link className="card" key={b.bidder_id} to={`/bidders/${encodeURIComponent(b.bidder_id)}?tender_id=${encodeURIComponent(tenderId)}`}>
            <h2 className="mono">{b.bidder_id}</h2>
            <RiskBadge level={b.risk.level} />
            <div className="metric-row">
              <Metric label="Compliance" value={b.metrics.compliance_score} />
              <Metric label="Coverage" value={b.metrics.verification_coverage} />
              <Metric label="Confidence" value={b.metrics.evidence_confidence} />
            </div>
            {b.collusion?.flagged && <p className="flag">Collusion flagged: <span className="mono">{b.collusion.cluster_id}</span></p>}
          </Link>
        ))}
      </div>

      <h2>Collusion</h2>
      <p className="hint">
        Edges are a shared director name, address, phone, or bank account across
        bidders on this tender -- the graph shows only the specific pair and
        attribute the event log actually recorded, nothing inferred beyond that.
      </p>
      {bidders && edges && (
        edges.length === 0 ? (
          <p className="hint">No collusion links found among registered bidders.</p>
        ) : (
          <>
            <div className="eg-toolbar">
              <button type="button" onClick={() => graphRef.current?.zoomToFit(400, 40)}>Reset view</button>
              {selectedNode && (
                <button type="button" onClick={() => setSelectedNode(null)}>Clear selection</button>
              )}
              <span className="hint">Scroll to zoom, drag to pan, click a bidder to trace their links</span>
            </div>
            <div className="graph-box">
              <ForceGraph2D
                ref={graphRef}
                width={640}
                height={360}
                graphData={{
                  nodes: bidders.map((b) => ({ id: b.bidder_id, flagged: b.collusion?.flagged })),
                  links: edges.map((e) => ({ source: e.bidder_a, target: e.bidder_b, label: e.attribute })),
                }}
                nodeLabel="id"
                onNodeClick={(n) => setSelectedNode((cur) => (cur === n.id ? null : n.id))}
                nodeColor={(n) => {
                  const dim = selectedNode && !connectedTo(selectedNode, edges).has(n.id);
                  const base = n.flagged ? cssVar("--status-fail-fg") : cssVar("--status-unknown-fg");
                  return dim ? cssVar("--color-border") : base;
                }}
                linkLabel={(l) => l.label}
                linkColor={(l) => {
                  if (!selectedNode) return cssVar("--status-partial-fg");
                  const sourceId = l.source.id ?? l.source;
                  const targetId = l.target.id ?? l.target;
                  const connected = sourceId === selectedNode || targetId === selectedNode;
                  return connected ? cssVar("--status-partial-fg") : cssVar("--color-border");
                }}
                linkDirectionalArrowLength={0}
                linkCanvasObjectMode={() => "after"}
                linkCanvasObject={(link, ctx) => {
                  if (typeof link.source !== "object" || typeof link.target !== "object") return;
                  const midX = (link.source.x + link.target.x) / 2;
                  const midY = (link.source.y + link.target.y) / 2;
                  ctx.font = "3px sans-serif";
                  ctx.fillStyle = cssVar("--status-partial-fg");
                  ctx.textAlign = "center";
                  ctx.fillText(link.label, midX, midY);
                }}
              />
            </div>
            <div className="eg-legend">
              <span className="eg-legend-item"><span className="eg-legend-swatch" style={{ background: "var(--status-fail-fg)" }} />collusion-flagged</span>
              <span className="eg-legend-item"><span className="eg-legend-swatch" style={{ background: "var(--status-unknown-fg)" }} />tracked, not flagged</span>
            </div>
          </>
        )
      )}

      {collusion && collusion.some((b) => b.flagged) && (
        <table className="evidence-table">
          <thead><tr><th>Bidder A</th><th>Bidder B</th><th>Shared attribute</th></tr></thead>
          <tbody>
            {(edges || []).map((e, i) => (
              <tr key={i}><td className="mono">{e.bidder_a}</td><td className="mono">{e.bidder_b}</td><td>{e.attribute}</td></tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Adopt a rule pack</h2>
      <p className="hint">
        Rule packs are versioned, content-addressed data (docs/RULE_PACKS.md), not code --
        paste one matching /schemas/rule_pack.schema.json. Adopting a new version never
        mutates a past verdict.
      </p>
      {canAdopt ? (
        <>
          <p className="hint">Adopted as {session.displayName} ({session.role.replace("_", " ")}).</p>
          <RulePackBuilder tenderId={tenderId} onAdopt={handleAdopt} submitting={adopting} />
          {adoptResult && <p className="status">Adopted rule pack version {adoptResult.rule_pack_version}.</p>}
          {violations && (
            <div className="error">
              <p>Rule pack refused -- {violations.length} violation(s):</p>
              <ul>
                {violations.map((v, i) => (
                  <li key={i}>[{v.rule}] {v.requirement_id ? `${v.requirement_id}: ` : ""}{v.message}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : (
        <p className="hint">Adopting a rule pack requires SENIOR_OFFICER or higher — you're signed in as {session.role.replace("_", " ")}.</p>
      )}
    </div>
  );
}
