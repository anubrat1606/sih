import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { listTenders, registerBidder, uploadDocument, verifyBidder } from "../api";
import { useApi } from "../lib/useApi";
import { useToast } from "../notifications";
import {
  Callout, Card, Dash, ErrorState, PageHeader, Section, Tag, UnavailableNote, VerdictBadge,
} from "../ui/primitives";

const DOC_TYPES = ["PAN", "GST", "UDYAM", "CIN", "EPFO"];

const ATTRIBUTES = [
  { key: "director_name", label: "Director name" },
  { key: "address", label: "Registered address" },
  { key: "phone", label: "Phone" },
  { key: "bank_account", label: "Bank account" },
];

export default function RegisterBidderPage() {
  const { notify } = useToast();
  const [params] = useSearchParams();
  const tenders = useApi(() => listTenders(), []);

  const [tenderId, setTenderId] = useState(params.get("tender_id") || "");
  const [bidderId, setBidderId] = useState("");
  const [attrs, setAttrs] = useState({ director_name: "", address: "", phone: "", bank_account: "" });
  const [registered, setRegistered] = useState(null);
  const [docType, setDocType] = useState(DOC_TYPES[0]);
  const [file, setFile] = useState(null);
  const [uploads, setUploads] = useState([]);
  const [verifyResult, setVerifyResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function onRegister(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const present = Object.fromEntries(Object.entries(attrs).filter(([, v]) => v.trim()));
      const result = await registerBidder(tenderId, bidderId, present);
      setRegistered(result);
      notify(`Registered ${bidderId} on ${tenderId}.`, { kind: "success" });
    } catch (err) {
      setError(err);
      notify("Registration failed.", { kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(e) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      const result = await uploadDocument(bidderId, tenderId, file, docType);
      setUploads((u) => [...u, { type: docType, name: file.name, result }]);
      setFile(null);
      e.target.reset();
      notify(`${docType} document ingested.`, { kind: "success" });
    } catch (err) {
      setError(err);
      notify("Upload failed.", { kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  async function onVerify() {
    setError(null);
    setBusy(true);
    try {
      setVerifyResult(await verifyBidder(bidderId, tenderId));
      notify("Verification run complete.", { kind: "success" });
    } catch (err) {
      setError(err);
      notify("Verification failed.", { kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page page-narrow" style={{ maxWidth: 780 }}>
      <PageHeader
        eyebrow="Evaluation"
        title="Register a bidder"
        subtitle="A bidder always exists in the context of one tender. Attributes below are used only for common-entity detection — whatever subset you have is used; registration is never all-or-nothing."
      />

      <ErrorState error={error} />

      {!registered ? (
        <Card title="Bidder identity">
          <form className="form form-wide" onSubmit={onRegister}>
            <div className="form-row">
              <div className="field">
                <label htmlFor="r-tender">Tender</label>
                {tenders.data?.tenders?.length ? (
                  <select id="r-tender" value={tenderId} onChange={(e) => setTenderId(e.target.value)} required>
                    <option value="">— select a tender —</option>
                    {tenders.data.tenders.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                ) : (
                  <input id="r-tender" className="mono" value={tenderId} required
                         onChange={(e) => setTenderId(e.target.value)} />
                )}
              </div>
              <div className="field">
                <label htmlFor="r-bidder">Bidder ID</label>
                <input id="r-bidder" className="mono" value={bidderId} required
                       onChange={(e) => setBidderId(e.target.value)} />
              </div>
            </div>

            <fieldset>
              <legend>Common-entity attributes (optional)</legend>
              <p className="text-xs text-secondary">
                Only a salted hash of each value ever enters the event log — the raw value is never stored.
                Two bidders sharing one of these is a signal for an officer to review, never a finding of fraud.
              </p>
              <div className="form-row">
                {ATTRIBUTES.map((a) => (
                  <div className="field" key={a.key}>
                    <label htmlFor={`r-${a.key}`}>{a.label}</label>
                    <input id={`r-${a.key}`} value={attrs[a.key]}
                           onChange={(e) => setAttrs({ ...attrs, [a.key]: e.target.value })} />
                  </div>
                ))}
              </div>
            </fieldset>

            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Registering…" : "Register bidder"}
            </button>
          </form>
        </Card>
      ) : (
        <>
          <Callout strong>
            Registered <span className="mono">{bidderId}</span> on <span className="mono">{tenderId}</span>.
            {registered.shared_attribute_links?.length > 0 && (
              <> Shares an attribute with{" "}
                {registered.shared_attribute_links.map((l) => `${l.with} (${l.attribute})`).join(", ")} —
                flagged for officer review.</>
            )}
          </Callout>

          <Section title="Upload documents"
                   note="Each document is hashed, stored by content, and read deterministically — identifiers are located by grammar and structurally validated before any authority is asked.">
            <Card>
              <form className="form form-wide" onSubmit={onUpload}>
                <div className="form-row">
                  <div className="field">
                    <label htmlFor="u-type">Document type</label>
                    <select id="u-type" value={docType} onChange={(e) => setDocType(e.target.value)}>
                      {DOC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="u-file">File</label>
                    <input id="u-file" type="file" required onChange={(e) => setFile(e.target.files?.[0] || null)} />
                  </div>
                </div>
                <button type="submit" className="btn btn-primary" disabled={busy || !file}>
                  {busy ? "Ingesting…" : "Upload and extract"}
                </button>
              </form>

              {uploads.length > 0 && (
                <div className="table-frame" style={{ marginTop: 16 }}>
                  <table className="data-table">
                    <thead><tr><th>Type</th><th>File</th><th>Extracted</th><th>Rejected</th></tr></thead>
                    <tbody>
                      {uploads.map((u, i) => (
                        <tr key={i}>
                          <td><Tag>{u.type}</Tag></td>
                          <td className="text-sm">{u.name}</td>
                          <td className="mono">{u.result.extracted?.length ?? 0}</td>
                          <td className="mono">{u.result.rejected?.length ?? 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </Section>

          <Section title="Run verification"
                   note="Asks every registered capability about what has been extracted so far. Where an authority cannot be reached, the answer is UNKNOWN with a machine-readable reason — never a guess.">
            <Card>
              <div className="btn-group">
                <button type="button" className="btn btn-primary" onClick={onVerify} disabled={busy}>
                  {busy ? "Verifying…" : "Run verification"}
                </button>
                <Link className="btn btn-secondary" to={`/officials/tenders/${encodeURIComponent(tenderId)}?tab=bidders`}>
                  Back to tender
                </Link>
                <Link className="btn btn-secondary"
                      to={`/officials/bidders/${encodeURIComponent(bidderId)}?tender_id=${encodeURIComponent(tenderId)}`}>
                  Open compliance workspace
                </Link>
              </div>

              {verifyResult && (
                verifyResult.outcomes.length === 0 ? (
                  <UnavailableNote title="Nothing to verify yet">
                    No extracted identifier was available to check against an authority. Upload a document first.
                  </UnavailableNote>
                ) : (
                  <div className="table-frame" style={{ marginTop: 16 }}>
                    <div className="table-scroll">
                      <table className="data-table">
                        <thead><tr><th>Capability</th><th>Result</th><th>Reason</th><th>Detail</th></tr></thead>
                        <tbody>
                          {verifyResult.outcomes.map((o) => (
                            <tr key={o.capability_id}>
                              <td className="mono text-sm">{o.capability_id}</td>
                              <td><VerdictBadge verdict={o.verdict} /></td>
                              <td className="mono text-xs">{o.reason_code || <Dash />}</td>
                              <td className="cell-note">{o.detail || <Dash />}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )
              )}
            </Card>
          </Section>
        </>
      )}
    </div>
  );
}
