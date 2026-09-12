import { useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getBidderEvidenceGraph, getProvenance } from "../api";
import { useApi } from "../lib/useApi";
import { formatTimestamp } from "../lib/audit";
import PdfEvidenceViewer from "../features/PdfEvidenceViewer";
import {
  Card, Dash, Drawer, EmptyState, ErrorState, EvidenceChain, LoadingBlock,
  PageHeader, Section, VerdictBadge,
} from "../ui/primitives";

const VIEW_W = 1180, VIEW_H = 600;
const MIN_SCALE = 0.35, MAX_SCALE = 2.5;
const REQ_W = 250, EV_W = 270, AUTH_W = 250;
const COL_GAP = 110, ROW_H = 62, ROW_GAP = 20, TOP_PAD = 52;
const X_REQ = 0, X_EV = REQ_W + COL_GAP, X_AUTH = X_EV + EV_W + COL_GAP;

const VERDICT_STROKE = {
  PASS: "var(--status-pass-fg)",
  FAIL: "var(--status-fail-fg)",
  PARTIAL: "var(--status-partial-fg)",
  UNKNOWN: "var(--status-unknown-fg)",
};

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

function column(ids, x) {
  const pos = {};
  ids.forEach((id, i) => { pos[id] = { x, y: TOP_PAD + i * (ROW_H + ROW_GAP) }; });
  return pos;
}

function edgePath(from, to, fromW) {
  const x1 = from.x + fromW, y1 = from.y + ROW_H / 2;
  const x2 = to.x, y2 = to.y + ROW_H / 2;
  const mid = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
}

// A deterministic, layered DAG — Requirement → Evidence → Authority — laid
// out the same way every time. Not a force-directed simulation: an officer
// reading this under pressure needs the same graph to look the same twice.
export default function EvidenceGraphPage() {
  const { bidderId } = useParams();
  const [params] = useSearchParams();
  const tenderId = params.get("tender_id");

  const graph = useApi(() => getBidderEvidenceGraph(bidderId, tenderId), [bidderId, tenderId], { skip: !tenderId });
  const [selected, setSelected] = useState(null);
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const dragRef = useRef(null);

  const provenance = useApi(
    () => getProvenance(bidderId, selected),
    [bidderId, selected],
    { skip: !selected }
  );

  const layout = useMemo(() => {
    const g = graph.data;
    if (!g) return null;
    return {
      req: column(g.requirements.map((r) => r.requirement_id), X_REQ),
      ev: column(g.evidence.map((e) => e.path), X_EV),
      auth: column(g.authorities.map((a) => a.capability_id), X_AUTH),
      width: X_AUTH + AUTH_W,
    };
  }, [graph.data]);

  if (!tenderId) {
    return (
      <div className="page">
        <EmptyState glyph="⚠" title="Missing tender context"
                    message="An evidence graph is always scoped to one bidder on one tender."
                    action={<Link to="/tenders" className="btn btn-primary">Go to tenders</Link>} />
      </div>
    );
  }

  const g = graph.data;
  const trail = provenance.data?.trail;
  const extracted = trail?.find((t) => t.event_type === "FIELD_EXTRACTED");
  const document = trail?.find((t) => t.event_type === "DOCUMENT_INGESTED");
  const observed = trail?.find((t) => t.event_type === "VERIFICATION_OBSERVED");
  const failed = trail?.find((t) => t.event_type === "VERIFICATION_FAILED");
  const evaluated = trail?.find((t) => t.event_type === "REQUIREMENT_EVALUATED");

  return (
    <div className="page">
      <PageHeader
        eyebrow={<Link to={`/bidders/${encodeURIComponent(bidderId)}?tender_id=${encodeURIComponent(tenderId)}`}>
          Bidder {bidderId}
        </Link>}
        title="Evidence graph"
        subtitle="Requirements on the left, the evidence each one actually consumes in the middle, and which authority — if any — was asked about it on the right. Click any node or edge to open its full trace."
      />

      <ErrorState error={graph.error} onRetry={graph.reload} />

      {graph.loading ? <LoadingBlock lines={6} /> : !g ? null : g.requirements.length === 0 ? (
        <EmptyState
          glyph="⌕"
          title="Nothing to graph yet"
          message="No leaf requirement binds any evidence for this bidder. A graph appears once a rule pack with LEAF requirements has been adopted and evaluated."
        />
      ) : (
        <>
          <div className="graph-frame">
            <div className="graph-toolbar">
              <button type="button" className="btn btn-sm btn-secondary"
                      onClick={() => setView((v) => ({ ...v, scale: clamp(v.scale * 1.25, MIN_SCALE, MAX_SCALE) }))}>
                Zoom in
              </button>
              <button type="button" className="btn btn-sm btn-secondary"
                      onClick={() => setView((v) => ({ ...v, scale: clamp(v.scale / 1.25, MIN_SCALE, MAX_SCALE) }))}>
                Zoom out
              </button>
              <button type="button" className="btn btn-sm btn-secondary" onClick={() => setView({ x: 0, y: 0, scale: 1 })}>
                Reset
              </button>
              <span className="mono text-xs text-muted">{Math.round(view.scale * 100)}%</span>
              <span className="spacer" />
              <span className="text-xs text-muted">Drag to pan · scroll to zoom</span>
            </div>

            <svg
              className="graph-canvas" width="100%" viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} height={VIEW_H}
              role="img"
              aria-label="Evidence graph: requirements, the evidence they consume, and the authorities verifying it."
              onWheel={(e) => { e.preventDefault(); setView((v) => ({ ...v, scale: clamp(v.scale * (e.deltaY < 0 ? 1.1 : 1 / 1.1), MIN_SCALE, MAX_SCALE) })); }}
              onPointerDown={(e) => { dragRef.current = { sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y }; e.currentTarget.setPointerCapture(e.pointerId); }}
              onPointerMove={(e) => {
                if (!dragRef.current) return;
                const { sx, sy, ox, oy } = dragRef.current;
                setView((v) => ({ ...v, x: ox + (e.clientX - sx), y: oy + (e.clientY - sy) }));
              }}
              onPointerUp={() => { dragRef.current = null; }}
              onPointerLeave={() => { dragRef.current = null; }}
            >
              <g transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}>
                <text x={X_REQ} y={26} className="graph-col-header">Requirement</text>
                <text x={X_EV} y={26} className="graph-col-header">Evidence</text>
                <text x={X_AUTH} y={26} className="graph-col-header">Authority</text>

                {g.edges.map((e, i) => {
                  const from = e.from_kind === "requirement" ? layout.req[e.from_id] : layout.ev[e.from_id];
                  const to = e.to_kind === "evidence" ? layout.ev[e.to_id] : layout.auth[e.to_id];
                  if (!from || !to) return null;
                  const d = edgePath(from, to, e.from_kind === "requirement" ? REQ_W : EV_W);
                  return (
                    <g key={i} className="graph-edge-group">
                      <path d={d} className="graph-edge-hit" onClick={() => setSelected(e.requirement_id)} />
                      <path d={d}
                            className={`graph-edge${selected === e.requirement_id ? " graph-edge-selected" : ""}`}
                            style={{ stroke: VERDICT_STROKE[e.verdict] || VERDICT_STROKE.UNKNOWN }}
                            strokeDasharray={e.to_kind === "authority" && e.resolved === false ? "5 4" : undefined} />
                    </g>
                  );
                })}

                {g.requirements.map((r) => {
                  const p = layout.req[r.requirement_id];
                  return (
                    <foreignObject key={r.requirement_id} x={p.x} y={p.y} width={REQ_W} height={ROW_H}>
                      <button type="button" className="graph-node" title={r.text}
                              onClick={() => setSelected(r.requirement_id)}>
                        <span className="graph-node-title mono">{r.requirement_id}</span>
                        <span><VerdictBadge verdict={r.verdict} /></span>
                      </button>
                    </foreignObject>
                  );
                })}

                {g.evidence.map((e) => {
                  const p = layout.ev[e.path];
                  return (
                    <foreignObject key={e.path} x={p.x} y={p.y} width={EV_W} height={ROW_H}>
                      <div className={`graph-node ${e.resolved ? "graph-node-resolved" : "graph-node-unresolved"}`}>
                        <span className="graph-node-title mono truncate">{e.path}</span>
                        <span className="graph-node-sub truncate">
                          {e.resolved ? String(e.value) : (e.unresolved_reason || "not determined")}
                          {e.tier ? ` · Tier ${e.tier}` : ""}
                        </span>
                      </div>
                    </foreignObject>
                  );
                })}

                {g.authorities.map((a) => {
                  const p = layout.auth[a.capability_id];
                  return (
                    <foreignObject key={a.capability_id} x={p.x} y={p.y} width={AUTH_W} height={ROW_H}>
                      <div className="graph-node graph-node-authority">
                        <span className="graph-node-title truncate">{a.authority}</span>
                        <span className="graph-node-sub mono truncate">{a.capability_id}</span>
                      </div>
                    </foreignObject>
                  );
                })}
              </g>
            </svg>

            <div className="graph-legend">
              {["PASS", "FAIL", "PARTIAL", "UNKNOWN"].map((v) => (
                <span className="graph-legend-item" key={v}>
                  <span className="graph-legend-swatch" style={{ background: VERDICT_STROKE[v] }} />{v}
                </span>
              ))}
              <span className="graph-legend-item"><span className="graph-legend-dashed" />authority not resolved</span>
            </div>
          </div>

          <Drawer
            open={Boolean(selected)}
            title={selected || ""}
            subtitle="Evidence trace"
            onClose={() => setSelected(null)}
          >
            {provenance.loading ? <LoadingBlock /> : provenance.error ? (
              <ErrorState error={provenance.error} onRetry={provenance.reload} />
            ) : (
              <>
                <Card title="Chain of evidence">
                  <EvidenceChain steps={[
                    { label: "Requirement", value: <span className="mono">{selected}</span> },
                    { label: "Document", value: document ? document.payload.filename : <span className="text-muted">not document-sourced</span> },
                    { label: "Page", value: extracted ? <span className="mono">page {extracted.payload.page}</span> : <Dash /> },
                    { label: "Extracted value", value: extracted ? <span className="mono">{String(extracted.payload.value)}</span> : <Dash /> },
                    { label: "Verification", value: observed
                        ? <span className="mono">{observed.payload.capability_id}</span>
                        : failed
                          ? <span>{failed.payload.capability_id} → {failed.payload.reason_code}</span>
                          : <span className="text-muted">no authority asked</span> },
                    { label: "Rule", value: evaluated ? <span className="mono">{evaluated.payload.rule_pack_version}</span> : <Dash /> },
                    { label: "Verdict", value: evaluated
                        ? <span className="row" style={{ gap: 8 }}>
                            <VerdictBadge verdict={evaluated.payload.verdict} />
                            <span className="text-sm text-secondary">{evaluated.payload.reason_code}</span>
                          </span>
                        : <Dash /> },
                  ]} />
                </Card>

                {extracted && document && (
                  <Section title="Source document">
                    <PdfEvidenceViewer
                      documentSha256={document.payload.document_sha256}
                      page={extracted.payload.page}
                      region={extracted.payload.region}
                    />
                  </Section>
                )}

                <Section title="Full event trail">
                  <div className="timeline">
                    {(trail || []).map((step) => (
                      <div className="timeline-item" key={step.seq}>
                        <div className="timeline-rail"><span className="timeline-dot" /><span className="timeline-line" /></div>
                        <div className="timeline-body">
                          <div className="timeline-head">
                            <span className="timeline-type">{step.event_type}</span>
                            <span className="timeline-meta mono">#{step.seq} · {formatTimestamp(step.occurred_at)}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </Section>
              </>
            )}
          </Drawer>
        </>
      )}
    </div>
  );
}
