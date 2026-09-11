import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getBidderEvidenceGraph, getProvenance } from "../api";
import { ErrorBox, ProvenancePanel, VerdictBadge } from "../components";

const VIEWPORT_W = 940, VIEWPORT_H = 560;
const MIN_SCALE = 0.4, MAX_SCALE = 2.5;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// satyapramana.md section 2.3: "the signature screen... requirements on one
// axis, evidence nodes beneath, authority verifications beside, edges
// weighted by verdict and confidence... a serious information-visualisation
// problem, not a decorative force-directed blob." Laid out as a deterministic
// three-column DAG -- Requirement -> Evidence -> Authority -- computed once
// per render, not simulated: the same graph looks the same every time, which
// a force layout can never promise and an officer reading it under pressure
// genuinely needs.
const REQ_W = 230, EV_W = 250, AUTH_W = 250;
const COL_GAP = 90;
const ROW_H = 60, ROW_GAP = 18;
const TOP_PAD = 56;
const X_REQ = 0;
const X_EV = REQ_W + COL_GAP;
const X_AUTH = X_EV + EV_W + COL_GAP;

const VERDICT_COLOR = {
  PASS: "var(--status-pass-fg)", FAIL: "var(--status-fail-fg)",
  PARTIAL: "var(--status-partial-fg)", UNKNOWN: "var(--status-unknown-fg)",
};

function columnLayout(ids, x) {
  const pos = {};
  ids.forEach((id, i) => { pos[id] = { x, y: TOP_PAD + i * (ROW_H + ROW_GAP) }; });
  return pos;
}

function edgePath(from, to, fromW) {
  const x1 = from.x + fromW, y1 = from.y + ROW_H / 2;
  const x2 = to.x, y2 = to.y + ROW_H / 2;
  const midX = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
}

export default function EvidenceGraphPage() {
  const { bidderId } = useParams();
  const [params] = useSearchParams();
  const tenderId = params.get("tender_id");

  const [graph, setGraph] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null); // { requirementId }
  const [provenance, setProvenance] = useState(null);

  // Pan/zoom, hand-rolled -- this is an SVG built as a deterministic layered
  // DAG (see the header comment), not a physics-driven force graph, so
  // there's no charting library underneath it to inherit interactivity
  // from. translate/scale on one wrapping <g>, nothing else.
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const dragRef = useRef(null);

  function onWheel(e) {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    setView((v) => ({ ...v, scale: clamp(v.scale * factor, MIN_SCALE, MAX_SCALE) }));
  }
  function onPointerDown(e) {
    dragRef.current = { startX: e.clientX, startY: e.clientY, origX: view.x, origY: view.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function onPointerMove(e) {
    if (!dragRef.current) return;
    const { startX, startY, origX, origY } = dragRef.current;
    setView((v) => ({ ...v, x: origX + (e.clientX - startX), y: origY + (e.clientY - startY) }));
  }
  function onPointerUp() {
    dragRef.current = null;
  }
  function zoomBy(factor) {
    setView((v) => ({ ...v, scale: clamp(v.scale * factor, MIN_SCALE, MAX_SCALE) }));
  }
  function resetView() {
    setView({ x: 0, y: 0, scale: 1 });
  }

  useEffect(() => {
    if (!tenderId) return;
    (async () => {
      setError(null);
      setGraph(null);
      try {
        setGraph(await getBidderEvidenceGraph(bidderId, tenderId));
      } catch (err) {
        setError(err);
      }
    })();
  }, [bidderId, tenderId]);

  const layout = useMemo(() => {
    if (!graph) return null;
    const reqIds = graph.requirements.map((r) => r.requirement_id);
    const evPaths = graph.evidence.map((e) => e.path);
    const authIds = graph.authorities.map((a) => a.capability_id);
    return {
      req: columnLayout(reqIds, X_REQ),
      ev: columnLayout(evPaths, X_EV),
      auth: columnLayout(authIds, X_AUTH),
      height: TOP_PAD + Math.max(reqIds.length, evPaths.length, authIds.length, 1) * (ROW_H + ROW_GAP),
      width: X_AUTH + AUTH_W,
    };
  }, [graph]);

  if (!tenderId) return <div className="page"><p className="error">Missing tender_id in the URL.</p></div>;

  async function openRequirement(requirementId) {
    setSelected({ requirementId });
    setProvenance(null);
    try {
      setProvenance(await getProvenance(bidderId, requirementId));
    } catch (err) {
      setError(err);
    }
  }

  return (
    <div className="page page-wide">
      <h1 className="mono">{bidderId}</h1>
      <p className="hint">
        Evidence Graph — Tender {tenderId}. Requirements on the left, the
        evidence each one actually consumes in the middle, and which
        authority (if any) was asked about it on the right. Click any edge
        for its full provenance trail.
      </p>
      <p className="actions"><Link to={`/bidders/${encodeURIComponent(bidderId)}?tender_id=${encodeURIComponent(tenderId)}`}>← Back to bidder detail</Link></p>
      <ErrorBox error={error} />

      {graph && layout && graph.requirements.length === 0 && (
        <p className="hint">No leaf requirement binds any evidence yet — nothing to graph until a rule pack with LEAF requirements is adopted and evaluated.</p>
      )}

      {graph && layout && graph.requirements.length > 0 && (
        <>
          <div className="eg-toolbar">
            <button type="button" onClick={() => zoomBy(1.25)}>Zoom in +</button>
            <button type="button" onClick={() => zoomBy(1 / 1.25)}>Zoom out −</button>
            <button type="button" onClick={resetView}>Reset view</button>
            <span className="hint mono">{Math.round(view.scale * 100)}%</span>
            <span className="hint">Scroll or drag to pan · wheel to zoom</span>
          </div>
          <div className="evidence-graph-scroll">
            <svg
              className="evidence-graph-svg eg-svg-viewport"
              width={VIEWPORT_W}
              height={VIEWPORT_H}
              role="img"
              aria-label="Evidence graph: requirements, the evidence they consume, and the authorities verifying it. Scroll to zoom, drag to pan."
              onWheel={onWheel}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerLeave={onPointerUp}
            >
            <g transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}>
              <text x={X_REQ} y={28} className="eg-col-header">Requirements</text>
              <text x={X_EV} y={28} className="eg-col-header">Evidence</text>
              <text x={X_AUTH} y={28} className="eg-col-header">Authority</text>

              {graph.edges.map((e, i) => {
                const from = e.from_kind === "requirement" ? layout.req[e.from_id] : layout.ev[e.from_id];
                const to = e.to_kind === "evidence" ? layout.ev[e.to_id] : layout.auth[e.to_id];
                if (!from || !to) return null;
                const fromW = e.from_kind === "requirement" ? REQ_W : EV_W;
                const d = edgePath(from, to, fromW);
                const color = VERDICT_COLOR[e.verdict] || VERDICT_COLOR.UNKNOWN;
                const unresolved = e.to_kind === "authority" && e.resolved === false;
                const isSelected = selected?.requirementId === e.requirement_id;
                return (
                  <g key={i} className="eg-edge-group">
                    <path d={d} className="eg-edge-hit"
                          onClick={() => openRequirement(e.requirement_id)} />
                    <path d={d} className={`eg-edge${isSelected ? " eg-edge-selected" : ""}`}
                          style={{ stroke: color }}
                          strokeDasharray={unresolved ? "4 4" : undefined} />
                  </g>
                );
              })}

              {graph.requirements.map((r) => {
                const p = layout.req[r.requirement_id];
                return (
                  <foreignObject key={r.requirement_id} x={p.x} y={p.y} width={REQ_W} height={ROW_H}>
                    <button type="button" className="eg-node eg-node-requirement"
                            onClick={() => openRequirement(r.requirement_id)}
                            title={r.text}>
                      <span className="mono eg-node-id">{r.requirement_id}</span>
                      <VerdictBadge verdict={r.verdict} />
                    </button>
                  </foreignObject>
                );
              })}

              {graph.evidence.map((e) => {
                const p = layout.ev[e.path];
                return (
                  <foreignObject key={e.path} x={p.x} y={p.y} width={EV_W} height={ROW_H}>
                    <div className={`eg-node eg-node-evidence ${e.resolved ? "eg-node-resolved" : "eg-node-unresolved"}`}>
                      <span className="mono eg-node-id">{e.path}</span>
                      <span className="hint eg-node-sub">
                        {e.resolved ? String(e.value) : (e.unresolved_reason || "not determined")}
                        {e.tier ? ` · Tier ${e.tier}` : ""}
                      </span>
                    </div>
                  </foreignObject>
                );
              })}

              {graph.authorities.map((a) => {
                const p = layout.auth[a.capability_id];
                return (
                  <foreignObject key={a.capability_id} x={p.x} y={p.y} width={AUTH_W} height={ROW_H}>
                    <div className="eg-node eg-node-authority">
                      <span className="eg-node-sub">{a.authority}</span>
                      <span className="mono eg-node-id">{a.capability_id}</span>
                    </div>
                  </foreignObject>
                );
              })}
            </g>
            </svg>
          </div>

          <div className="eg-legend">
            <span className="eg-legend-item"><span className="eg-legend-swatch" style={{ background: VERDICT_COLOR.PASS }} />PASS</span>
            <span className="eg-legend-item"><span className="eg-legend-swatch" style={{ background: VERDICT_COLOR.FAIL }} />FAIL</span>
            <span className="eg-legend-item"><span className="eg-legend-swatch" style={{ background: VERDICT_COLOR.PARTIAL }} />PARTIAL</span>
            <span className="eg-legend-item"><span className="eg-legend-swatch" style={{ background: VERDICT_COLOR.UNKNOWN }} />UNKNOWN</span>
            <span className="eg-legend-item"><span className="eg-legend-dashed" />authority not resolved</span>
          </div>

          {selected && (
            <div className="eg-provenance">
              <h2 className="mono">{selected.requirementId}</h2>
              {provenance ? <ProvenancePanel trail={provenance.trail} /> : <p className="hint">Loading…</p>}
            </div>
          )}
        </>
      )}
    </div>
  );
}
