import { Fragment, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import {
  evaluateBidder, getBidder, getProvenance, overrideVerdict, recordDecision,
} from "../api";
import { ErrorBox, Metric, RiskBadge, VerdictBadge } from "../components";

export default function BidderDetailPage() {
  const { bidderId } = useParams();
  const [params] = useSearchParams();
  const tenderId = params.get("tender_id");

  const [bidder, setBidder] = useState(null);
  const [error, setError] = useState(null);
  const [openProvenance, setOpenProvenance] = useState(null);
  const [provenance, setProvenance] = useState(null);

  const [bidSubmissionDate, setBidSubmissionDate] = useState("");
  const [officerId, setOfficerId] = useState("officer_demo");
  const [decisionNote, setDecisionNote] = useState("");
  const [lastDecision, setLastDecision] = useState(null);

  const [overrideForm, setOverrideForm] = useState({ requirement_id: "", verdict_after: "PASS", justification: "" });

  function load() {
    if (!tenderId) return;
    getBidder(bidderId, tenderId).then(setBidder).catch(setError);
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
      <h1>{bidderId}</h1>
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
            <Metric label="Verification coverage" value={bidder.metrics.verification_coverage} />
            <Metric label="Mandatory coverage" value={bidder.metrics.verification_coverage_mandatory} />
            <Metric label="Evidence confidence" value={bidder.metrics.evidence_confidence} />
          </div>
          <p className="hint">
            Three independent metrics, never blended into one score -- a bidder can be
            fully compliant on what was checked while coverage is honestly low.
          </p>

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
                      <td>{v.requirement_id}</td>
                      <td><VerdictBadge verdict={v.verdict_effective} /></td>
                      <td>{v.reason_effective}</td>
                      <td>{v.overridden_by || "—"}</td>
                      <td><button onClick={() => toggleProvenance(v.requirement_id)}>
                        {openProvenance === v.requirement_id ? "Hide" : "Why?"}
                      </button></td>
                    </tr>
                    {openProvenance === v.requirement_id && provenance && (
                      <tr>
                        <td colSpan={5}>
                          <ol className="audit-list">
                            {provenance.trail.map((t) => (
                              <li key={t.seq}>
                                {t.event_type} (seq {t.seq}, {t.occurred_at}): {JSON.stringify(t.payload)}
                              </li>
                            ))}
                          </ol>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
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
          {lastDecision && <p className="status">Recorded: {lastDecision.decision} (seq {lastDecision.seq}, hash {lastDecision.hash.slice(0, 16)}…)</p>}

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
