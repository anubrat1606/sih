import { useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  evaluateBidder, getAutopsy, getBidder, getBidderEvidence, getExplanation,
  getProvenance, getRepairPlan, overrideVerdict,
} from "../api";
import { roleAtLeast, useAuth } from "../authContext";
import { useApi } from "../lib/useApi";
import { formatTimestamp } from "../lib/audit";
import { useToast } from "../notifications";
import PdfEvidenceViewer from "../features/PdfEvidenceViewer";
import FinalisePanel from "../officer/review/FinalisePanel";
import {
  Callout, Card, ConfirmDialog, CoverageMetric, Dash, Drawer, EmptyState, ErrorState,
  EvidenceChain, Field, LoadingBlock, MetricCard, PageHeader, RiskBadge, Section,
  SeverityBadge, Tabs, Tag, UnavailableNote, VerdictBadge,
} from "../ui/primitives";

const TABS = [
  { id: "compliance", label: "Compliance" },
  { id: "autopsy", label: "Bid Autopsy" },
  { id: "repair", label: "Compliance Repair" },
  { id: "evidence", label: "Evidence" },
  { id: "decision", label: "Officer Decision" },
];

function EvidencePanel({ bidderId, requirementId, verdict, onClose }) {
  const provenance = useApi(() => getProvenance(bidderId, requirementId), [bidderId, requirementId]);
  const trail = provenance.data?.trail;

  const extracted = trail?.find((t) => t.event_type === "FIELD_EXTRACTED");
  const document = trail?.find((t) => t.event_type === "DOCUMENT_INGESTED");
  const observed = trail?.find((t) => t.event_type === "VERIFICATION_OBSERVED");
  const failed = trail?.find((t) => t.event_type === "VERIFICATION_FAILED");
  const evaluated = trail?.find((t) => t.event_type === "REQUIREMENT_EVALUATED");

  return (
    <Drawer open title={requirementId} subtitle="Evidence trace" onClose={onClose}>
      {provenance.loading ? <LoadingBlock /> : provenance.error ? (
        <ErrorState error={provenance.error} onRetry={provenance.reload} />
      ) : (
        <>
          <Card title="Chain of evidence">
            <EvidenceChain
              steps={[
                { label: "Requirement", value: <span className="mono">{requirementId}</span> },
                {
                  label: "Document",
                  value: document
                    ? <span>{document.payload.filename} <span className="text-muted mono text-xs">({String(document.payload.document_sha256).slice(0, 12)}…)</span></span>
                    : <span className="text-muted">no source document — this fact came from an authority, not a page</span>,
                },
                {
                  label: "Page",
                  value: extracted ? <span className="mono">page {extracted.payload.page}</span> : <Dash />,
                },
                {
                  label: "Extracted value",
                  value: extracted ? <span className="mono">{String(extracted.payload.value)}</span> : <Dash />,
                },
                {
                  label: "Verification",
                  value: observed
                    ? <span>{observed.payload.capability_id} responded at <span className="mono">{observed.payload.observed_at}</span></span>
                    : failed
                      ? <span>{failed.payload.capability_id} → {failed.payload.reason_code}{failed.payload.detail ? ` — ${failed.payload.detail}` : ""}</span>
                      : <span className="text-muted">no authority was asked for this fact</span>,
                },
                {
                  label: "Rule",
                  value: evaluated
                    ? <span className="mono">{evaluated.payload.rule_pack_version}</span>
                    : <Dash />,
                },
                {
                  label: "Verdict",
                  value: <span className="row" style={{ gap: 8 }}>
                    <VerdictBadge verdict={verdict} />
                    {evaluated && <span className="text-sm text-secondary">{evaluated.payload.reason_code}</span>}
                  </span>,
                },
              ]}
            />
          </Card>

          {extracted && document && (
            <Section title="Source document" note="The exact page and region this value was read from.">
              <PdfEvidenceViewer
                documentSha256={document.payload.document_sha256}
                page={extracted.payload.page}
                region={extracted.payload.region}
              />
            </Section>
          )}

          <Section title="Full event trail" note="Every event behind this verdict, newest last.">
            <Card flush>
              <div style={{ padding: "12px 20px" }}>
                <div className="timeline">
                  {(trail || []).map((step) => (
                    <div className="timeline-item" key={step.seq}>
                      <div className="timeline-rail"><span className="timeline-dot" /><span className="timeline-line" /></div>
                      <div className="timeline-body">
                        <div className="timeline-head">
                          <span className="timeline-type">{step.event_type}</span>
                          <span className="timeline-meta mono">#{step.seq} · {formatTimestamp(step.occurred_at)}</span>
                        </div>
                        <div className="timeline-detail mono text-xs">{JSON.stringify(step.payload)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          </Section>
        </>
      )}
    </Drawer>
  );
}

export default function BidderCompliancePage() {
  const { bidderId } = useParams();
  const [params, setParams] = useSearchParams();
  const tenderId = params.get("tender_id");
  const activeTab = params.get("tab") || "compliance";
  const { session } = useAuth();
  const { notify } = useToast();
  const canOverride = roleAtLeast(session.role, "SENIOR_OFFICER");

  const bidder = useApi(() => getBidder(bidderId, tenderId), [bidderId, tenderId], { skip: !tenderId });
  const evidence = useApi(() => getBidderEvidence(bidderId, tenderId).catch(() => null), [bidderId, tenderId], { skip: !tenderId });
  const autopsy = useApi(() => getAutopsy(bidderId, tenderId).catch(() => null), [bidderId, tenderId], { skip: !tenderId });
  const repair = useApi(() => getRepairPlan(bidderId, tenderId).catch(() => null), [bidderId, tenderId], { skip: !tenderId });

  const [openRequirement, setOpenRequirement] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [explaining, setExplaining] = useState(false);
  const [bidDate, setBidDate] = useState("");
  const [confirmOverride, setConfirmOverride] = useState(false);
  const [overrideForm, setOverrideForm] = useState({ requirement_id: "", verdict_after: "PASS", justification: "" });
  const [actionError, setActionError] = useState(null);

  const evidenceByPath = useMemo(() => {
    const rows = evidence.data?.evidence || [];
    return Object.fromEntries(rows.map((e) => [e.path, e]));
  }, [evidence.data]);

  function setTab(id) {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    setParams(next, { replace: true });
  }

  if (!tenderId) {
    return (
      <div className="page">
        <EmptyState
          glyph="⚠"
          title="Missing tender context"
          message="A bidder's compliance is always relative to one tender. Open this bidder from a tender's bidder list."
          action={<Link to="/tenders" className="btn btn-primary">Go to tenders</Link>}
        />
      </div>
    );
  }

  const b = bidder.data;
  const verdicts = b?.verdicts || [];

  async function onEvaluate(e) {
    e.preventDefault();
    setActionError(null);
    try {
      await evaluateBidder(bidderId, tenderId, bidDate);
      bidder.reload(); autopsy.reload(); repair.reload(); evidence.reload();
      notify("Evaluation complete.", { kind: "success" });
    } catch (err) {
      setActionError(err);
      notify("Evaluation failed.", { kind: "error" });
    }
  }

  async function onExplain() {
    setExplaining(true);
    try {
      const result = await getExplanation(bidderId, tenderId);
      setExplanation(result);
      if (!result.available) notify(`Summary unavailable: ${result.reason}`, { kind: "info" });
    } catch (err) {
      setActionError(err);
    } finally {
      setExplaining(false);
    }
  }

  async function doOverride() {
    setConfirmOverride(false);
    setActionError(null);
    try {
      await overrideVerdict(bidderId, tenderId, overrideForm.requirement_id, overrideForm.verdict_after, overrideForm.justification);
      setOverrideForm({ requirement_id: "", verdict_after: "PASS", justification: "" });
      bidder.reload();
      notify(`Overrode ${overrideForm.requirement_id}.`, { kind: "success" });
    } catch (err) {
      setActionError(err);
      notify("Override failed.", { kind: "error" });
    }
  }

  const overall = verdicts.length === 0
    ? "UNKNOWN"
    : verdicts.some((v) => v.verdict_effective === "FAIL") ? "FAIL"
    : verdicts.some((v) => v.verdict_effective === "UNKNOWN") ? "UNKNOWN"
    : verdicts.some((v) => v.verdict_effective === "PARTIAL") ? "PARTIAL"
    : "PASS";

  return (
    <div className="page">
      <PageHeader
        eyebrow={<Link to={`/tenders/${encodeURIComponent(tenderId)}?tab=bidders`}>Tender {tenderId}</Link>}
        title={bidderId}
        subtitle="Every verdict below can be traced to the document, page and authority that produced it."
        actions={
          <>
            <Link className="btn btn-secondary"
                  to={`/bidders/${encodeURIComponent(bidderId)}/evidence-graph?tender_id=${encodeURIComponent(tenderId)}`}>
              Evidence graph
            </Link>
            <span className="row" style={{ gap: 8 }}>
              <VerdictBadge verdict={overall} />
              {b?.risk && <RiskBadge level={b.risk.level} />}
            </span>
          </>
        }
      />

      <ErrorState error={bidder.error} onRetry={bidder.reload} />
      <ErrorState error={actionError} />

      {bidder.loading ? <LoadingBlock lines={3} /> : b && (
        <>
          {/* Three metrics — always three, never blended into one score. */}
          <div className="metric-triad">
            <MetricCard label="Compliance score" value={b.metrics.compliance_score}
                        note={b.metrics.compliance_score == null ? "nothing determinate yet — not zero" : "of what could be checked"} />
            <MetricCard label="Evidence confidence" value={b.metrics.evidence_confidence}
                        note="strength of the evidence behind those checks" />
            <CoverageMetric label="Verification coverage" value={b.metrics.verification_coverage}
                            note="independently confirmed with an authority" />
          </div>
          <p className="text-xs text-muted" style={{ marginTop: 10 }}>
            These three are deliberately never averaged together. A bid can be fully compliant on everything
            that was checkable while coverage remains honestly low.
          </p>

          {b.collusion?.flagged && (
            <div style={{ marginTop: 16 }}>
              <UnavailableNote title="Potential common entity — officer review required">
                This bidder shares a tracked attribute with{" "}
                <span className="mono">{b.collusion.members.filter((m) => m !== bidderId).join(", ")}</span>{" "}
                (cluster <span className="mono">{b.collusion.cluster_id}</span>). A shared attribute is a
                signal to look, never a finding of collusion.
              </UnavailableNote>
            </div>
          )}

          <div style={{ marginTop: 24 }}>
            <Tabs tabs={TABS.map((t) => ({
              ...t,
              count: t.id === "compliance" ? verdicts.length
                   : t.id === "repair" ? repair.data?.actions?.length
                   : undefined,
            }))} active={activeTab} onChange={setTab} />
          </div>

          {activeTab === "compliance" && (
            verdicts.length === 0 ? (
              <EmptyState
                glyph="◌"
                title="Not evaluated yet"
                message="This bidder has not been evaluated against an adopted rule pack. Run an evaluation from the Officer Decision tab once a rule pack governs this tender."
                action={<button type="button" className="btn btn-secondary" onClick={() => setTab("decision")}>Go to evaluation</button>}
              />
            ) : (
              <div className="table-frame">
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Requirement</th>
                        <th>Evidence</th>
                        <th>Verification</th>
                        <th>Result</th>
                        <th className="cell-actions" />
                      </tr>
                    </thead>
                    <tbody>
                      {verdicts.map((v) => {
                        const ev = evidenceByPath[v.evidence_path] || null;
                        return (
                          <tr key={v.requirement_id}>
                            <td>
                              <div className="mono cell-primary">{v.requirement_id}</div>
                              {v.text && <div className="text-xs text-secondary" style={{ marginTop: 2 }}>{v.text}</div>}
                            </td>
                            <td>
                              {ev?.resolved ? (
                                <>
                                  <div className="mono text-sm">{String(ev.value)}</div>
                                  <div className="text-xs text-muted">{ev.path}</div>
                                </>
                              ) : (
                                <span className="text-muted text-sm">
                                  {ev?.unresolved_reason || "no evidence recorded"}
                                </span>
                              )}
                            </td>
                            <td className="text-sm">
                              {ev?.capability_id
                                ? <span>{ev.capability_id}{ev.tier ? ` · Tier ${ev.tier}` : ""}</span>
                                : <span className="text-muted">not authority-verified</span>}
                            </td>
                            <td>
                              <VerdictBadge verdict={v.verdict_effective} />
                              <div className="text-xs text-muted" style={{ marginTop: 2 }}>{v.reason_effective}</div>
                              {v.overridden_by && (
                                <div className="text-xs" style={{ color: "var(--status-partial-fg)", marginTop: 2 }}>
                                  overridden by {v.overridden_by}
                                </div>
                              )}
                            </td>
                            <td className="cell-actions">
                              <button type="button" className="btn btn-sm btn-secondary"
                                      onClick={() => setOpenRequirement({ id: v.requirement_id, verdict: v.verdict_effective })}>
                                Trace evidence
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          )}

          {activeTab === "autopsy" && (
            <Section title="Bid Autopsy"
                     note="Why this bid would fail right now — derived deterministically from the event log, never regenerated by a model.">
              {autopsy.loading ? <LoadingBlock /> : !autopsy.data || autopsy.data.would_qualify === null ? (
                <UnavailableNote title="Nothing to analyse yet">
                  {autopsy.data?.note || "No rule pack has been adopted for this tender, so there is nothing to evaluate against."}
                </UnavailableNote>
              ) : autopsy.data.would_qualify ? (
                <EmptyState glyph="✓" title="Nothing is blocking qualification"
                            message="Every mandatory requirement is satisfied on the evidence available." />
              ) : (
                <>
                  <Callout>
                    {autopsy.data.blocking_requirements.length} requirement(s) block qualification, ranked below.
                    FATAL means positive evidence against the bidder — re-checking the same fact will not change it.
                    CURABLE means an absence of evidence a new document could still fill.
                  </Callout>
                  <div style={{ marginTop: 16 }}>
                    {autopsy.data.blocking_requirements.map((blocker, i) => (
                      <Card key={blocker.requirement_id}
                            title={`${String(i + 1).padStart(2, "0")} · ${blocker.requirement_id}`}
                            actions={<SeverityBadge classification={blocker.classification} />}>
                        <div className="field-grid">
                          <Field label="Requirement">{blocker.text}</Field>
                          <Field label="Result"><VerdictBadge verdict={blocker.verdict} /></Field>
                          <Field label="Evidence" empty={!evidenceByPath[blocker.evidence_path]?.resolved}>
                            {evidenceByPath[blocker.evidence_path]?.resolved
                              ? <span className="mono">{String(evidenceByPath[blocker.evidence_path].value)}</span>
                              : (evidenceByPath[blocker.evidence_path]?.unresolved_reason || "no evidence recorded")}
                          </Field>
                          <Field label="Rule">{blocker.reason_code || <Dash />}</Field>
                        </div>
                        <div style={{ marginTop: 12 }}>
                          <button type="button" className="btn btn-sm btn-secondary"
                                  onClick={() => setOpenRequirement({ id: blocker.requirement_id, verdict: blocker.verdict })}>
                            Trace evidence
                          </button>
                        </div>
                      </Card>
                    ))}
                  </div>
                  {autopsy.data.counterfactual && (
                    <Callout strong>
                      {autopsy.data.counterfactual.would_qualify_if_cured
                        ? <>Curing <span className="mono">{autopsy.data.counterfactual.curable_requirement_ids.join(", ")}</span> would be enough — this bid would move to qualifying.</>
                        : <>Even curing <span className="mono">{autopsy.data.counterfactual.curable_requirement_ids.join(", ")}</span> would not be enough — <span className="mono">{autopsy.data.counterfactual.still_blocking_after_cure.join(", ")}</span> would still block qualification.</>}
                    </Callout>
                  )}
                </>
              )}
            </Section>
          )}

          {activeTab === "repair" && (
            <Section title="How can this be resolved?"
                     note="One specific, executable action per curable gap. A fatal finding gets none — paperwork does not fix positive contradicting evidence.">
              {repair.loading ? <LoadingBlock /> : !repair.data?.actions?.length ? (
                <UnavailableNote title="No repair actions">
                  {repair.data?.note || "Nothing is currently curable — either nothing is blocking, or the blockers are fatal."}
                </UnavailableNote>
              ) : (
                repair.data.actions.map((a) => (
                  <Card key={a.requirement_id} title={a.requirement_id}
                        actions={<Tag accent={a.actionable_by === "BIDDER"}>{a.actionable_by === "BIDDER" ? "BIDDER CAN ACT" : "SYSTEM GAP"}</Tag>}>
                    <div className="field-grid">
                      <Field label="Required action">{a.action}</Field>
                      {a.authority && <Field label="Authority">{a.authority}</Field>}
                      <Field label="Current status"><VerdictBadge verdict={a.verdict || "UNKNOWN"} /></Field>
                    </div>
                    {a.actionable_by !== "BIDDER" && (
                      <p className="text-xs text-muted" style={{ marginTop: 10 }}>
                        This gap is ours, not the bidder's — it is never reported to them as their problem.
                      </p>
                    )}
                  </Card>
                ))
              )}
            </Section>
          )}

          {activeTab === "evidence" && (
            <Section title="Evidence held for this bidder"
                     note="Every fact the system holds, resolved or not. An unresolved row states why, never blank.">
              {evidence.loading ? <LoadingBlock /> : !evidence.data?.evidence?.length ? (
                <EmptyState glyph="⌕" title="No evidence recorded"
                            message="Upload this bidder's documents and run verification to populate their evidence." />
              ) : (
                <div className="table-frame">
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead>
                        <tr><th>Evidence path</th><th>Value</th><th>Source</th><th>Tier</th><th>Status</th></tr>
                      </thead>
                      <tbody>
                        {evidence.data.evidence.map((e) => (
                          <tr key={e.path}>
                            <td className="mono text-sm">{e.path}</td>
                            <td>{e.resolved ? <span className="mono">{String(e.value)}</span> : <Dash />}</td>
                            <td className="text-sm">{e.capability_id || <span className="text-muted">document extraction</span>}</td>
                            <td>{e.tier ? <Tag>TIER {e.tier}</Tag> : <Dash />}</td>
                            <td>
                              {e.resolved
                                ? <span className="badge badge-pass"><span className="badge-glyph" aria-hidden="true">✓</span>RESOLVED</span>
                                : <span className="badge badge-unknown" title={e.unresolved_reason}>
                                    <span className="badge-glyph" aria-hidden="true">?</span>{e.unresolved_reason || "UNRESOLVED"}
                                  </span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </Section>
          )}

          {activeTab === "decision" && (
            <div className="grid-2">
              <Card title="Evaluate against the rule pack">
                <p className="text-secondary text-sm" style={{ marginBottom: 12 }}>
                  Folds the evidence, fuses it, and decides — deterministically, with no model in the path.
                  Requires an adopted rule pack on this tender.
                </p>
                <form className="form" onSubmit={onEvaluate}>
                  <div className="field">
                    <label htmlFor="bid-date">Bid submission date</label>
                    <input id="bid-date" type="date" className="mono" value={bidDate} required
                           onChange={(e) => setBidDate(e.target.value)} />
                  </div>
                  <button type="submit" className="btn btn-primary">Run evaluation</button>
                </form>
              </Card>

              <FinalisePanel bidderId={bidderId} tenderId={tenderId} />

              <Card title="Officer summary">
                <p className="text-secondary text-sm" style={{ marginBottom: 12 }}>
                  A narrator, not a judge: the model restates the dossier above in prose and may not alter a
                  single fact in it. If it is unavailable, everything above remains complete on its own.
                </p>
                <button type="button" className="btn btn-secondary" onClick={onExplain} disabled={explaining}>
                  {explaining ? "Generating…" : "Generate summary"}
                </button>
                {explanation && (
                  explanation.available ? (
                    <div style={{ marginTop: 12 }}>
                      <p className="narrative">{explanation.narrative}</p>
                      <p className="text-xs text-muted" style={{ marginTop: 8 }}>
                        Narrated by {explanation.model} at {explanation.generated_at}.
                      </p>
                    </div>
                  ) : (
                    <div style={{ marginTop: 12 }}>
                      <UnavailableNote title="Summary unavailable">{explanation.reason}</UnavailableNote>
                    </div>
                  )
                )}
              </Card>

              <Card title="Override a verdict">
                <p className="text-secondary text-sm" style={{ marginBottom: 12 }}>
                  A human may overrule the system. The system remembers that they did, and keeps its own
                  conclusion alongside theirs — it is never erased.
                </p>
                {canOverride ? (
                  <form className="form" onSubmit={(e) => { e.preventDefault(); setConfirmOverride(true); }}>
                    <div className="field">
                      <label htmlFor="ov-req">Requirement ID</label>
                      <input id="ov-req" className="mono" value={overrideForm.requirement_id} required
                             onChange={(e) => setOverrideForm({ ...overrideForm, requirement_id: e.target.value })} />
                    </div>
                    <div className="field">
                      <label htmlFor="ov-verdict">New verdict</label>
                      <select id="ov-verdict" value={overrideForm.verdict_after}
                              onChange={(e) => setOverrideForm({ ...overrideForm, verdict_after: e.target.value })}>
                        {["PASS", "FAIL", "PARTIAL", "UNKNOWN"].map((v) => <option key={v} value={v}>{v}</option>)}
                      </select>
                    </div>
                    <div className="field">
                      <label htmlFor="ov-just">Justification</label>
                      <input id="ov-just" value={overrideForm.justification} required
                             onChange={(e) => setOverrideForm({ ...overrideForm, justification: e.target.value })} />
                    </div>
                    <button type="submit" className="btn btn-secondary">Override</button>
                  </form>
                ) : (
                  <UnavailableNote title="Requires SENIOR OFFICER or higher">
                    You are signed in as {session.role.replace("_", " ")}.
                  </UnavailableNote>
                )}
              </Card>
            </div>
          )}
        </>
      )}

      {openRequirement && (
        <EvidencePanel
          bidderId={bidderId}
          requirementId={openRequirement.id}
          verdict={openRequirement.verdict}
          onClose={() => setOpenRequirement(null)}
        />
      )}

      <ConfirmDialog
        open={confirmOverride}
        title="Override this verdict?"
        body={`This sets ${overrideForm.requirement_id || "the requirement"} to ${overrideForm.verdict_after} for ${bidderId}, attributed to ${session.displayName}. The system's original conclusion stays visible alongside your override.`}
        confirmLabel="Override"
        danger
        onConfirm={doOverride}
        onCancel={() => setConfirmOverride(false)}
      />
    </div>
  );
}
