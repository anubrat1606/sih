import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ForceGraph2D from "react-force-graph-2d";
import { adoptRulePack, getCollusionEdges, getTender, getTenderCollusion, listTenderBidders,
  uploadTenderDocument, validateRulePack } from "../api";
import { roleAtLeast, useAuth } from "../authContext";
import { ErrorBox, Metric, RiskBadge } from "../components";
import { EmptyState } from "../EmptyState";
import { useToast } from "../notifications";
import { ReportActions } from "../ReportActions";
import RulePackBuilder from "../RulePackBuilder";
import { SearchFilterBar } from "../SearchFilterBar";
import { SkeletonCard } from "../Skeleton";
import TenderIntelligence from "../TenderIntelligence";
import { cssVar } from "../theme";

const RISK_ORDER = { LOW: 0, MEDIUM: 1, HIGH: 2 };

export default function TenderDashboardPage() {
  const { tenderId } = useParams();
  const { session } = useAuth();
  const { notify } = useToast();
  const canAdopt = roleAtLeast(session.role, "SENIOR_OFFICER");
  const [bidders, setBidders] = useState(null);
  const [filteredBidders, setFilteredBidders] = useState(null);
  const [collusion, setCollusion] = useState(null);
  const [edges, setEdges] = useState(null);
  const [error, setError] = useState(null);
  const [adoptResult, setAdoptResult] = useState(null);
  const [violations, setViolations] = useState(null);
  const [adopting, setAdopting] = useState(false);
  const [validateResult, setValidateResult] = useState(null);
  const [validating, setValidating] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [tender, setTender] = useState(null);
  const [prefill, setPrefill] = useState(null);
  const [tenderPdf, setTenderPdf] = useState(null);
  const [uploadingPdf, setUploadingPdf] = useState(false);
  const graphRef = useRef();

  const bidderSortOptions = useMemo(() => [
    { label: "Risk: high → low", compare: (a, b) => RISK_ORDER[b.risk.level] - RISK_ORDER[a.risk.level] },
    { label: "Compliance: low → high", compare: (a, b) => (a.metrics.compliance_score ?? -1) - (b.metrics.compliance_score ?? -1) },
    { label: "Bidder ID, A → Z", compare: (a, b) => a.bidder_id.localeCompare(b.bidder_id) },
  ], []);

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
      const result = await adoptRulePack(tenderId, pack);
      setAdoptResult(result);
      notify(`Adopted rule pack version ${result.rule_pack_version}.`, { kind: "success" });
    } catch (err) {
      if (err.detail?.violations) {
        setViolations(err.detail.violations);
        notify(`Rule pack refused: ${err.detail.violations.length} violation(s).`, { kind: "error" });
      } else {
        setError(err);
        notify("Could not adopt the rule pack.", { kind: "error" });
      }
    } finally {
      setAdopting(false);
    }
  }

  async function handleValidate(pack, parseError) {
    setValidateResult(null);
    if (parseError) {
      notify(parseError.message, { kind: "error" });
      return;
    }
    setValidating(true);
    try {
      const result = await validateRulePack(tenderId, pack);
      setValidateResult(result);
      notify(result.valid ? "Valid — ready to adopt." : `${result.violations.length} violation(s) found.`,
        { kind: result.valid ? "success" : "error" });
    } catch {
      notify("Could not validate the rule pack.", { kind: "error" });
    } finally {
      setValidating(false);
    }
  }

  async function handleUploadPdf(e) {
    e.preventDefault();
    if (!tenderPdf) return;
    setUploadingPdf(true);
    try {
      const result = await uploadTenderDocument(tenderId, tenderPdf);
      notify(`Uploaded. Document SHA-256: ${result.document_sha256.slice(0, 16)}…`, { kind: "success" });
      setTenderPdf(null);
    } catch (err) {
      notify(`Could not upload the tender PDF: ${err.message}`, { kind: "error" });
    } finally {
      setUploadingPdf(false);
    }
  }

  return (
    <div className="page">
      <h1>{tender?.title || <span className="mono">{tenderId}</span>}</h1>
      {tender?.title ? (
        <p className="hint">
          <span className="mono">{tenderId}</span> · {tender.issuing_authority}
          {tender.department && ` · ${tender.department}`}
          {tender.category && ` · ${tender.category}`}
          {tender.issue_date && ` · issued ${tender.issue_date}`}
          {tender.bid_submission_deadline && ` · bids close ${tender.bid_submission_deadline}`}
        </p>
      ) : (
        <p className="hint">No tender metadata on file -- this tender exists only because a bidder registered on it.</p>
      )}
      {tender?.description && <p className="hint">{tender.description}</p>}
      <ErrorBox error={error} />

      <h2>Bidders</h2>
      {bidders === null && (
        <div className="card-grid">
          <SkeletonCard /><SkeletonCard /><SkeletonCard />
        </div>
      )}
      {bidders && bidders.length === 0 && (
        <EmptyState message="No bidders registered yet." actionLabel="Register a bidder" actionTo="/register" />
      )}
      {bidders && bidders.length > 0 && (
        <>
          <SearchFilterBar
            items={bidders}
            searchKeys={["bidder_id"]}
            sortOptions={bidderSortOptions}
            onChange={setFilteredBidders}
            placeholder="Search bidders…"
          />
          <div className="card-grid">
            {(filteredBidders || bidders).map((b) => (
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
          <ReportActions tenderId={tenderId} />
        </>
      )}

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
      <h3>Tender PDF</h3>
      <p className="hint">
        The original tender notice, kept as the authoritative source for Tender
        Intelligence below and for the rule pack's own source_document_sha256.
      </p>
      <form className="form" onSubmit={handleUploadPdf}>
        <label>Upload tender PDF
          <input type="file" accept="application/pdf" onChange={(e) => setTenderPdf(e.target.files?.[0] || null)} />
        </label>
        <button type="submit" disabled={!tenderPdf || uploadingPdf}>{uploadingPdf ? "Uploading…" : "Upload"}</button>
      </form>

      {canAdopt ? (
        <>
          <p className="hint">Adopted as {session.displayName} ({session.role.replace("_", " ")}).</p>
          <TenderIntelligence tenderId={tenderId} onUseProposal={setPrefill} />
          <RulePackBuilder tenderId={tenderId} onAdopt={handleAdopt} onValidate={handleValidate}
                           submitting={adopting} validating={validating}
                           prefill={prefill} onPrefillConsumed={() => setPrefill(null)} />
          {validateResult && (
            validateResult.valid ? (
              <p className="status">Valid — content hash {validateResult.content_hash.slice(0, 16)}…, {validateResult.requirement_count} requirement(s). Not adopted yet; click Adopt to publish.</p>
            ) : (
              <div className="error">
                <p>Validation found {validateResult.violations.length} violation(s) — not adopted:</p>
                <ul>
                  {validateResult.violations.map((v, i) => (
                    <li key={i}>[{v.rule}] {v.requirement_id ? `${v.requirement_id}: ` : ""}{v.message}</li>
                  ))}
                </ul>
              </div>
            )
          )}
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
