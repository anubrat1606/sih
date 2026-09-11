import { Fragment, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import {
  evaluateBidder, getAutopsy, getBidder, getBidderEvidence, getProvenance,
  getRepairPlan, overrideVerdict, recordDecision,
} from "../api";
import {
  ClassificationBadge, ConflictCard, CoverageMeter, ErrorBox, EvidenceChip,
  Metric, ProvenanceStep, RepairAction, RiskBadge, VerdictBadge,
} from "../components";
import PdfEvidenceViewer from "../PdfEvidenceViewer";

export default function BidderDetailPage() {
  const { bidderId } = useParams();
  const [params] = useSearchParams();
  const tenderId = params.get("tender_id");

  const [bidder, setBidder] = useState(null);
  const [error, setError] = useState(null);
  const [openProvenance, setOpenProvenance] = useState(null);
  const [provenance, setProvenance] = useState(null);
  const [autopsy, setAutopsy] = useState(null);
  const [repairPlan, setRepairPlan] = useState(null);
  const [evidence, setEvidence] = useState(null);

  const [bidSubmissionDate, setBidSubmissionDate] = useState("");
  const [officerId, setOfficerId] = useState("officer_demo");
  const [decisionNote, setDecisionNote] = useState("");
  const [lastDecision, setLastDecision] = useState(null);

  const [overrideForm, setOverrideForm] = useState({ requirement_id: "", verdict_after: "PASS", justification: "" });

  function load() {
    if (!tenderId) return;
    getBidder(bidderId, tenderId).then(setBidder).catch(setError);
    // A 409 here just means no rule pack has been adopted for this tender yet
    // -- an expected state, not a page-breaking error, so it renders inline
    // in each section rather than in the shared ErrorBox.
    getAutopsy(bidderId, tenderId).then(setAutopsy).catch(() => setAutopsy(null));
    getRepairPlan(bidderId, tenderId).then(setRepairPlan).catch(() => setRepairPlan(null));
    getBidderEvidence(bidderId, tenderId).then(setEvidence).catch(() => setEvidence(null));
  }

  useEffect(load, [bidderId, tenderId]);

  if (!tenderId) return <div className="page"><p className="error">Missing tender_id in the URL -- open this page from the tender dashboard.</p></div>;

  async function onEvaluate(e) {
    e.preventDefault();
    setError(null);
    try {
      await evaluateBidder(bidderId, tenderId, bidSubmissionDate);
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function onDecision(decision) {
    setError(null);
    try {
      setLastDecision(await recordDecision(bidderId, tenderId, officerId, decision, decisionNote));
    } catch (err) {
      setError(err);
    }
  }

  async function onOverride(e) {
    e.preventDefault();
    setError(null);
    try {
      await overrideVerdict(bidderId, tenderId, officerId, overrideForm.requirement_id, overrideForm.verdict_after, overrideForm.justification);
      setOverrideForm({ requirement_id: "", verdict_after: "PASS", justification: "" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function toggleProvenance(requirementId) {
    if (openProvenance === requirementId) {
      setOpenProvenance(null);
      return;
    }
    setError(null);
    try {
      setProvenance(await getProvenance(bidderId, requirementId));
      setOpenProvenance(requirementId);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <div className="page">
      <h1 className="mono">{bidderId}</h1>
      <p className="hint">Tender {tenderId}</p>
      <ErrorBox error={error} />
      {bidder && (
        <>
          <div className="actions">
            <RiskBadge level={bidder.risk.level} />
          </div>
          {bidder.risk.triggers.length > 0 && (
            <p className="hint">Risk triggers: {bidder.risk.triggers.join(", ")} (function {bidder.risk.function_version})</p>
          )}
          <div className="metric-row">
            <Metric label="Compliance score" value={bidder.metrics.compliance_score} />
            <Metric label="Evidence confidence" value={bidder.metrics.evidence_confidence} />
          </div>
          <div className="metric-row">
            <CoverageMeter label="Verification coverage" value={bidder.metrics.verification_coverage} />
            <CoverageMeter label="Mandatory coverage" value={bidder.metrics.verification_coverage_mandatory} />
          </div>
          <p className="hint">
            Three independent metrics, never blended into one score -- a bidder can be
            fully compliant on what was checked while coverage is honestly low.
          </p>

          {evidence && evidence.evidence.length > 0 && (() => {
            const byPath = Object.fromEntries(evidence.evidence.map((e) => [e.path, e]));
            const claimed = byPath["bidder.gst.claimed_legal_name"];
            const authority = byPath["bidder.gst.legal_name"];
            if (!claimed?.resolved || !authority?.resolved) return null;
            return (
              <ConflictCard field="GST legal name" claim={claimed.value} authority={authority.value} />
            );
          })()}

          {bidder.collusion && (
            <p className={bidder.collusion.flagged ? "flag" : "hint"}>
              Collusion: {bidder.collusion.flagged ? `flagged, cluster ${bidder.collusion.cluster_id}, with ${bidder.collusion.members.filter((m) => m !== bidderId).join(", ")}` : "not flagged"}
            </p>
          )}

          <h2>Verdicts</h2>
          {bidder.verdicts.length === 0 ? (
            <p className="hint">No rule pack has been evaluated for this bidder yet.</p>
          ) : (
            <table className="evidence-table">
              <thead><tr><th>Requirement</th><th>Verdict</th><th>Reason</th><th>Overridden by</th><th></th></tr></thead>
              <tbody>
                {bidder.verdicts.map((v) => (
                  <Fragment key={v.requirement_id}>
                    <tr>
                      <td className="mono">{v.requirement_id}</td>
                      <td><VerdictBadge verdict={v.verdict_effective} /></td>
                      <td>{v.reason_effective}</td>
                      <td>{v.overridden_by || "—"}</td>
                      <td><EvidenceChip
                        value={openProvenance === v.requirement_id ? "Hide" : "Why?"}
                        open={openProvenance === v.requirement_id}
                        onReveal={() => toggleProvenance(v.requirement_id)}
                      /></td>
                    </tr>
                    {openProvenance === v.requirement_id && provenance && (
                      <tr>
                        <td colSpan={5}>
                          <ol className="audit-list">
                            {provenance.trail.map((t) => <ProvenanceStep key={t.seq} step={t} />)}
                          </ol>
                          {(() => {
                            // The demo axiom: click a verdict, land on the exact
                            // highlighted line of the actual PDF. Only possible
                            // when the trail reaches both an extracted field
                            // (page + region) and the document it came from
                            // (its content hash) -- a verification-sourced fact
                            // never reaches a document, and that's correct, not
                            // a bug (see PROVENANCE_SUMMARY's own comment).
                            const extracted = provenance.trail.find((t) => t.event_type === "FIELD_EXTRACTED");
                            const document = provenance.trail.find((t) => t.event_type === "DOCUMENT_INGESTED");
                            if (!extracted || !document) return null;
                            return (
                              <PdfEvidenceViewer
                                documentSha256={document.payload.document_sha256}
                                page={extracted.payload.page}
                                region={extracted.payload.region}
                              />
                            );
                          })()}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}

          <h2>Bid Autopsy</h2>
          <p className="hint">Why this bid would fail right now -- deterministic, derived from the event log, never regenerated by a model.</p>
          {!autopsy || autopsy.would_qualify === null ? (
            <p className="hint">{autopsy?.note || "No rule pack adopted yet."}</p>
          ) : autopsy.would_qualify ? (
            <p className="status">Every mandatory requirement is satisfied -- nothing is blocking qualification.</p>
          ) : (
            <>
              <table className="evidence-table">
                <thead><tr><th>Requirement</th><th>Text</th><th>Verdict</th><th>Classification</th></tr></thead>
                <tbody>
                  {autopsy.blocking_requirements.map((b) => (
                    <tr key={b.requirement_id}>
                      <td className="mono">{b.requirement_id}</td>
                      <td>{b.text}</td>
                      <td><VerdictBadge verdict={b.verdict} /></td>
                      <td><ClassificationBadge classification={b.classification} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {autopsy.counterfactual && (
                <p className="hint">
                  {autopsy.counterfactual.would_qualify_if_cured
                    ? `Curing ${autopsy.counterfactual.curable_requirement_ids.join(", ")} would be enough -- this bid would move to qualifying.`
                    : `Even curing ${autopsy.counterfactual.curable_requirement_ids.join(", ")} would not be enough -- ${autopsy.counterfactual.still_blocking_after_cure.join(", ")} would still block qualification.`}
                </p>
              )}
            </>
          )}

          <h2>Compliance Repair</h2>
          <p className="hint">The forward-looking inverse: one action per curable gap. Fatal findings get none -- paperwork doesn't fix positive contradicting evidence.</p>
          {!repairPlan || repairPlan.actions.length === 0 ? (
            <p className="hint">{repairPlan?.note || "Nothing to repair right now."}</p>
          ) : (
            repairPlan.actions.map((a) => <RepairAction key={a.requirement_id} action={a} />)
          )}

          <h2>Evaluate</h2>
          <p className="hint">Folds evidence, fuses it, and decides -- deterministically. Needs a rule pack adopted on this tender first.</p>
          <form className="form" onSubmit={onEvaluate}>
            <label>Bid submission date<input type="date" value={bidSubmissionDate} onChange={(e) => setBidSubmissionDate(e.target.value)} required /></label>
            <button type="submit">Evaluate</button>
          </form>

          <h2>Officer decision</h2>
          <form className="form" onSubmit={(e) => e.preventDefault()}>
            <label>Officer ID<input value={officerId} onChange={(e) => setOfficerId(e.target.value)} /></label>
            <label>Note (optional)<input value={decisionNote} onChange={(e) => setDecisionNote(e.target.value)} /></label>
            <div className="actions">
              <button onClick={() => onDecision("QUALIFY")}>Qualify</button>
              <button className="danger" onClick={() => onDecision("DISQUALIFY")}>Disqualify</button>
            </div>
          </form>
          {lastDecision && <p className="status">Recorded: {lastDecision.decision} (seq {lastDecision.seq}, hash <span className="mono">{lastDecision.hash.slice(0, 16)}…</span>)</p>}

          <h2>Override a verdict</h2>
          <p className="hint">A human may overrule the system. The system remembers that they did, and keeps its own conclusion alongside theirs.</p>
          <form className="form" onSubmit={onOverride}>
            <label>Requirement ID<input value={overrideForm.requirement_id} onChange={(e) => setOverrideForm({ ...overrideForm, requirement_id: e.target.value })} required /></label>
            <label>New verdict
              <select value={overrideForm.verdict_after} onChange={(e) => setOverrideForm({ ...overrideForm, verdict_after: e.target.value })}>
                {["PASS", "FAIL", "PARTIAL", "UNKNOWN"].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </label>
            <label>Justification<input value={overrideForm.justification} onChange={(e) => setOverrideForm({ ...overrideForm, justification: e.target.value })} required /></label>
            <button type="submit">Override</button>
          </form>
        </>
      )}
    </div>
  );
}
