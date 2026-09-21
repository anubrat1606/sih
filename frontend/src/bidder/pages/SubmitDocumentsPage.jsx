import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getMySubmission, getMyTenderRequirements, recordDeclaration, uploadMyDocument } from "../bidderApi";
import { formatEvidenceValue } from "../../lib/currency";
import { useApi } from "../../lib/useApi";
import {
  Card, Dash, EmptyState, ErrorState, PageHeader, Tag,
} from "../../ui/primitives";

//: The exact label app.py's _evidence_expected returns for a
// bidder.declarations.* path -- how this page tells "needs a document" and
// "needs a self-declaration" apart, without the backend having to expose
// the raw evidence field to a bidder at all.
const DECLARATION_LABEL = "Self-declaration / undertaking";

// Round 9. An undertaking IS the self-declaration -- recorded directly,
// never uploaded as a document, and (unlike everything else on this page)
// takes effect the moment it's submitted, not deferred to the wizard's
// later steps.
function DeclarationRow({ requirement, bidderId, tenderId, existing, onRecorded }) {
  const [text, setText] = useState(existing?.declaration_text || "");
  // `forceEdit`, not "editing" directly: `existing` only becomes real once
  // onRecorded()'s reload actually resolves, which is strictly after this
  // component re-renders from a successful save. Deriving "editing" as
  // forceEdit || !existing (below), rather than a plain boolean flipped
  // optimistically in onSave, means the confirmed view can never render
  // while `existing` is still the stale pre-save value (undefined on a
  // first save) -- caught live: `existing.declaration_text` threw exactly
  // that instant before this fix.
  const [forceEdit, setForceEdit] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const editing = forceEdit || !existing;

  async function onSave() {
    if (!text.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await recordDeclaration(bidderId, tenderId, requirement.id, text.trim());
      setForceEdit(false);
      onRecorded();
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="table-frame" style={{ padding: "var(--space-4)", marginBottom: "var(--space-3)" }}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start", gap: "var(--space-3)" }}>
        <div>
          <div className="mono text-sm">{requirement.id}</div>
          <div className="cell-note" style={{ marginTop: 2 }}>{requirement.text}</div>
        </div>
        <ObligationTag obligation={requirement.obligation} />
      </div>

      <ErrorState error={error} />

      {editing ? (
        <div style={{ marginTop: "var(--space-3)" }}>
          <label htmlFor={`decl-${requirement.id}`} className="text-xs text-secondary">
            Your declaration — recorded exactly as written, with your identity and the time, permanently.
          </label>
          <textarea id={`decl-${requirement.id}`} rows={3} value={text} style={{ width: "100%", marginTop: 4 }}
                    onChange={(e) => setText(e.target.value)} />
          <div className="btn-group" style={{ marginTop: "var(--space-2)" }}>
            <button type="button" className="btn btn-primary btn-sm" disabled={saving || !text.trim()} onClick={onSave}>
              {saving ? "Recording…" : existing ? "Save correction" : "Record declaration"}
            </button>
            {existing && (
              <button type="button" className="btn btn-secondary btn-sm"
                      onClick={() => { setText(existing.declaration_text); setForceEdit(false); }}>
                Cancel
              </button>
            )}
          </div>
        </div>
      ) : (
        <div style={{ marginTop: "var(--space-3)" }}>
          <p className="text-sm">“{existing.declaration_text}”</p>
          <p className="text-xs text-secondary" style={{ marginTop: 4 }}>
            Recorded by {existing.declared_by} on {new Date(existing.declared_at).toLocaleString()}.
          </p>
          <button type="button" className="btn btn-secondary btn-sm" style={{ marginTop: 6 }}
                  onClick={() => setForceEdit(true)}>
            Correct this declaration
          </button>
        </div>
      )}
    </div>
  );
}

// The same declared_type values pages/RegisterBidderPage.jsx (officer
// side) offers — that file is Anubrat's and not importable across owners
// this round, so the list is repeated here rather than reached into.
const DOC_TYPES = ["PAN", "GST", "UDYAM", "CIN", "EPFO"];

const STEPS = [
  { n: 1, label: "Review the requirements" },
  { n: 2, label: "Upload documents" },
  { n: 3, label: "Confirm" },
];

const CHECKLIST_ITEMS = [
  { key: "reviewed", label: "I've reviewed the requirements above." },
  { key: "ready", label: "My documents are ready to upload." },
  { key: "terms", label: "I've read the tender's terms and conditions." },
  { key: "details", label: "My registered details are correct." },
];

function ObligationTag({ obligation }) {
  return <Tag accent={obligation === "mandatory"}>{obligation}</Tag>;
}

export default function SubmitDocumentsPage() {
  const { tenderId } = useParams();
  // bidderApi.js has no tender-independent "who am I" call; the signed-in
  // bidder's own bidder_id only ever appears scoped to a tender
  // (/me/tenders/{id}/submission already returns it), which this page has
  // anyway -- so this doubles as the source for the id uploadMyDocument
  // needs, rather than reaching for api.js's getMe().
  const submission = useApi(() => getMySubmission(tenderId), [tenderId]);
  const requirements = useApi(() => getMyTenderRequirements(tenderId), [tenderId]);

  const [step, setStep] = useState(1);
  const [checklist, setChecklist] = useState(
    Object.fromEntries(CHECKLIST_ITEMS.map((c) => [c.key, false]))
  );
  const checklistComplete = CHECKLIST_ITEMS.every((c) => checklist[c.key]);

  const [declaredType, setDeclaredType] = useState(DOC_TYPES[0]);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [uploads, setUploads] = useState([]); // [{declaredType, filename, result}]
  const hasSuccessfulUpload = uploads.some((u) => !u.failed);

  async function onUpload(e) {
    e.preventDefault();
    if (!file || !submission.data?.bidder_id) return;
    setUploadError(null);
    setUploading(true);
    try {
      const result = await uploadMyDocument(submission.data.bidder_id, tenderId, file, declaredType);
      setUploads((u) => [...u, { declaredType, filename: file.name, result, failed: false }]);
      setFile(null);
      e.target.reset();
    } catch (err) {
      setUploadError(err);
      setUploads((u) => [...u, { declaredType, filename: file.name, error: err, failed: true }]);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bidder"
        title={`Submit documents — ${tenderId}`}
        subtitle="Three steps. Nothing here is a result — only the procuring officer's recorded decision is."
      />

      <div className="row" style={{ alignItems: "flex-start", gap: "var(--space-6)" }}>
        <nav aria-label="Submission steps" style={{ minWidth: 190, flexShrink: 0 }}>
          {STEPS.map((s) => (
            <div
              key={s.n}
              className="row"
              style={{
                gap: "var(--space-2)", padding: "var(--space-2) 0",
                opacity: step === s.n ? 1 : 0.55,
                fontWeight: step === s.n ? 600 : 400,
              }}
            >
              <span className="mono">{s.n}.</span>
              <span>{s.label}</span>
            </div>
          ))}
        </nav>

        <div style={{ flex: 1, minWidth: 0 }}>
          {step === 1 && (
            <Card title="Requirements for this tender">
              <ErrorState error={requirements.error} onRetry={requirements.reload} />
              {requirements.loading ? (
                <p className="text-secondary text-sm">Loading…</p>
              ) : !requirements.data?.requirements?.length ? (
                <EmptyState
                  glyph="◌"
                  title="No requirements published yet"
                  message="The procuring office hasn't adopted a rule pack for this tender yet. You can still review this page later."
                />
              ) : (
                <div className="table-frame" style={{ marginBottom: "var(--space-4)" }}>
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead>
                        <tr><th>Requirement</th><th>Obligation</th><th>Page</th><th>Evidence expected</th></tr>
                      </thead>
                      <tbody>
                        {requirements.data.requirements.map((r) => (
                          <tr key={r.id}>
                            <td className="mono text-sm">{r.id}</td>
                            <td className="cell-note">{r.text}</td>
                            <td><ObligationTag obligation={r.obligation} /></td>
                            <td className="mono text-sm">{r.source_page ?? <Dash />}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {(() => {
                const declRequirements = (requirements.data?.requirements || [])
                  .filter((r) => r.evidence_expected === DECLARATION_LABEL);
                if (!declRequirements.length) return null;
                const byId = Object.fromEntries(
                  (submission.data?.declarations || []).map((d) => [d.requirement_id, d]));
                return (
                  <div style={{ marginBottom: "var(--space-5)" }}>
                    <h3 className="section-title" style={{ marginBottom: 8 }}>Self-declarations</h3>
                    <p className="text-xs text-secondary" style={{ marginBottom: 12 }}>
                      These requirements ask for your own attestation, not a document — there's nothing to
                      upload for them. Recorded the moment you save, with your identity and the time.
                    </p>
                    {declRequirements.map((r) => (
                      <DeclarationRow key={r.id} requirement={r} bidderId={submission.data?.bidder_id}
                                      tenderId={tenderId} existing={byId[r.id]}
                                      onRecorded={submission.reload} />
                    ))}
                  </div>
                );
              })()}

              <fieldset>
                <legend>Before you submit</legend>
                <p className="text-xs text-secondary">
                  This checklist is not verified by the system — it's a reminder for
                  you, not a check the system performs.
                </p>
                {CHECKLIST_ITEMS.map((c) => (
                  <label key={c.key} className="row" style={{ gap: "var(--space-2)", padding: "var(--space-1) 0" }}>
                    <input
                      type="checkbox"
                      checked={checklist[c.key]}
                      onChange={(e) => setChecklist({ ...checklist, [c.key]: e.target.checked })}
                    />
                    {c.label}
                  </label>
                ))}
              </fieldset>

              <div className="btn-group" style={{ marginTop: "var(--space-4)" }}>
                <button type="button" className="btn btn-primary" disabled={!checklistComplete}
                        onClick={() => setStep(2)}>
                  Next: upload documents
                </button>
              </div>
            </Card>
          )}

          {step === 2 && (
            <Card title="Upload your documents">
              <ErrorState error={submission.error} onRetry={submission.reload} />
              <ErrorState error={uploadError} />
              <form className="form form-wide" onSubmit={onUpload}>
                <div className="form-row">
                  <div className="field">
                    <label htmlFor="s-type">Document type</label>
                    <select id="s-type" value={declaredType} onChange={(e) => setDeclaredType(e.target.value)}>
                      {DOC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="s-file">File</label>
                    <input id="s-file" type="file" required onChange={(e) => setFile(e.target.files?.[0] || null)} />
                  </div>
                </div>
                <button type="submit" className="btn btn-primary"
                        disabled={uploading || !file || submission.loading || !submission.data?.bidder_id}>
                  {uploading ? "Uploading and reading…" : submission.loading ? "Loading…" : "Upload"}
                </button>
              </form>

              {uploads.length > 0 && (
                <div style={{ marginTop: "var(--space-5)" }}>
                  {uploads.map((u, i) => (
                    <Card key={i} title={`${u.declaredType} — ${u.filename}`}>
                      {u.failed ? (
                        <p className="error-note" role="alert">
                          <span aria-hidden="true">⚠</span>{" "}
                          {String(u.error?.message || u.error)}
                        </p>
                      ) : (
                        <>
                          {u.result.extracted?.length > 0 && (
                            <div className="table-frame" style={{ marginBottom: "var(--space-3)" }}>
                              <table className="data-table">
                                <thead><tr><th>Field</th><th>Value</th><th>Page</th></tr></thead>
                                <tbody>
                                  {u.result.extracted.map((f) => (
                                    <tr key={f.path}>
                                      <td className="mono text-sm">{f.path}</td>
                                      <td className="mono text-sm">{formatEvidenceValue(f.path, f.value)}</td>
                                      <td className="mono text-sm">{f.page}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                          {u.result.rejected?.length > 0 && u.result.rejected.map((r, j) => (
                            <p key={j} className="error-note" role="alert">
                              <span aria-hidden="true">⚠</span>{" "}
                              {r.path}: “{r.candidate}” was not accepted — {r.detail}
                            </p>
                          ))}
                          {u.result.unreadable_pages?.length > 0 && u.result.unreadable_pages.map((p, j) => (
                            <p key={j} className="error-note" role="alert">
                              <span aria-hidden="true">⚠</span>{" "}
                              Page {p.page} could not be read — {p.reason}
                            </p>
                          ))}
                          {u.result.identifier_cross_check?.outcome === "IDENTIFIER_CONFLICT" && (
                            <p className="error-note" role="alert">
                              <span aria-hidden="true">⚠</span>{" "}
                              The PAN embedded in the GSTIN ({u.result.identifier_cross_check.embedded_pan}) does
                              not match the PAN on file ({u.result.identifier_cross_check.pan}). The procuring
                              officer will need to review this.
                            </p>
                          )}
                          {u.result.identifier_cross_check?.outcome === "LINKED" && (
                            <p className="text-secondary text-sm">
                              PAN and GSTIN identifiers are consistent with each other.
                            </p>
                          )}
                          {!u.result.extracted?.length && !u.result.rejected?.length
                            && !u.result.unreadable_pages?.length && (
                            <p className="text-secondary text-sm">
                              Received — no statutory identifier was found on this document.
                            </p>
                          )}
                        </>
                      )}
                    </Card>
                  ))}
                </div>
              )}

              <div className="btn-group" style={{ marginTop: "var(--space-4)" }}>
                <button type="button" className="btn btn-secondary" onClick={() => setStep(1)}>Back</button>
                <button type="button" className="btn btn-primary" disabled={!hasSuccessfulUpload}
                        onClick={() => setStep(3)}>
                  Next: confirm
                </button>
              </div>
            </Card>
          )}

          {step === 3 && (
            <Card title="Confirm">
              <div className="table-frame" style={{ marginBottom: "var(--space-4)" }}>
                <table className="data-table">
                  <thead><tr><th>Type</th><th>File</th><th>SHA-256</th><th>Fields found</th></tr></thead>
                  <tbody>
                    {uploads.filter((u) => !u.failed).map((u, i) => (
                      <tr key={i}>
                        <td><Tag>{u.declaredType}</Tag></td>
                        <td className="text-sm">{u.filename}</td>
                        <td className="mono text-xs" title={u.result.document_sha256}>
                          {u.result.document_sha256.slice(0, 16)}…
                        </td>
                        <td className="mono">{u.result.extracted?.length ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <p>
                Your documents have been received by the procurement office. This
                confirms receipt only; assessment is performed by the procuring
                officer and you'll see the outcome under My results.
              </p>

              <div className="btn-group" style={{ marginTop: "var(--space-4)" }}>
                <button type="button" className="btn btn-secondary" onClick={() => setStep(2)}>Back</button>
                <Link className="btn btn-primary" to="/portal/submissions">Done — go to My submissions</Link>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
