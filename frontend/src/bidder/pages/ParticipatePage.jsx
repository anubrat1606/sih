import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { registerBidder, uploadBidderDocument, verifyBidder } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { Stepper } from "../components/FormControls";
import {
  Callout, Card, Dash, ErrorState, PageHeader, Tag, UnavailableNote, VerdictBadge,
} from "../../ui/primitives";

const STEPS = ["Tender Review", "Documents", "Bid Details", "Confirmation", "Submission"];
const DOC_TYPES = ["PAN", "GST", "UDYAM", "CIN", "EPFO"];

const CHECKLIST = [
  "I have read the tender's eligibility requirements.",
  "I have the compliance documents (PAN, GST and any others required) ready to upload.",
  "I understand my documents will be checked against live government registries where available.",
  "I understand the procurement officer's final decision, not this checklist, determines the outcome.",
];

export default function ParticipatePage() {
  const { tenderId } = useParams();
  const { trackBid } = useBidderSession();

  const [step, setStep] = useState(0);
  const [checklistDone, setChecklistDone] = useState(false);
  const [checked, setChecked] = useState(() => CHECKLIST.map(() => false));
  const [bidderId, setBidderId] = useState("");
  const [attrs, setAttrs] = useState({ director_name: "", address: "", phone: "", bank_account: "" });
  const [registered, setRegistered] = useState(null);
  const [docType, setDocType] = useState(DOC_TYPES[0]);
  const [file, setFile] = useState(null);
  const [uploads, setUploads] = useState([]);
  const [verifyResult, setVerifyResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const allChecked = checked.every(Boolean);

  async function onRegister(e) {
    e.preventDefault();
    if (!bidderId.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const present = Object.fromEntries(Object.entries(attrs).filter(([, v]) => v.trim()));
      const result = await registerBidder(tenderId, bidderId.trim(), present);
      setRegistered(result);
      trackBid(tenderId, bidderId.trim());
      setStep(1); // Documents
    } catch (err) {
      setError(err);
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
      const result = await uploadBidderDocument(bidderId, tenderId, file, docType);
      setUploads((u) => [...u, { type: docType, name: file.name, result }]);
      setFile(null);
      e.target.reset();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function onVerify() {
    setError(null);
    setBusy(true);
    try {
      setVerifyResult(await verifyBidder(bidderId, tenderId));
      setStep(3);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page page-narrow" style={{ maxWidth: 780 }}>
      <PageHeader
        eyebrow={<Link to={`/bidder/tenders/${encodeURIComponent(tenderId)}`}>Tender {tenderId}</Link>}
        title="Participate"
        subtitle="Registering, uploading documents and verifying are real actions against the live system — nothing here is simulated."
      />

      <Stepper steps={STEPS} current={step} />
      <ErrorState error={error} />

      {step === 0 && !checklistDone && (
        <Card title="Before you begin">
          <div className="checklist">
            {CHECKLIST.map((label, i) => (
              <label className="checklist-item" key={i}>
                <input type="checkbox" checked={checked[i]}
                       onChange={(e) => setChecked((c) => c.map((v, idx) => idx === i ? e.target.checked : v))} />
                <span className="text-sm">{label}</span>
              </label>
            ))}
          </div>
          <button type="button" className="btn btn-primary" style={{ marginTop: 16 }} disabled={!allChecked}
                  onClick={() => setChecklistDone(true)}>
            Continue to registration
          </button>
        </Card>
      )}

      {step === 0 && checklistDone && (
        <Card title="Register as a bidder on this tender">
          <p className="text-sm text-secondary" style={{ marginBottom: 12 }}>
            A bidder ID identifies your submission on this tender. Common-entity attributes below are optional
            and are only ever stored as a salted hash, never in plain text.
          </p>
          <form className="form form-wide" onSubmit={onRegister}>
            <div className="field">
              <label htmlFor="p-bidder">Bidder ID</label>
              <input id="p-bidder" className="mono" value={bidderId} required onChange={(e) => setBidderId(e.target.value)} />
            </div>
            <fieldset>
              <legend>Common-entity attributes (optional)</legend>
              <div className="form-row">
                {["director_name", "address", "phone", "bank_account"].map((k) => (
                  <div className="field" key={k}>
                    <label htmlFor={`p-${k}`}>{k.replace("_", " ")}</label>
                    <input id={`p-${k}`} value={attrs[k]} onChange={(e) => setAttrs({ ...attrs, [k]: e.target.value })} />
                  </div>
                ))}
              </div>
            </fieldset>
            <button type="submit" className="btn btn-primary" disabled={busy || !bidderId.trim()}>
              {busy ? "Registering…" : "Register"}
            </button>
          </form>
        </Card>
      )}

      {step === 1 && registered && (
        <Card title="Upload your documents">
          {registered.shared_attribute_links?.length > 0 && (
            <Callout>
              Shares an attribute with {registered.shared_attribute_links.map((l) => `${l.with} (${l.attribute})`).join(", ")}
              {" "}— flagged for officer review. This is a signal to look, never a finding against you.
            </Callout>
          )}
          <form className="form form-wide" onSubmit={onUpload}>
            <div className="form-row">
              <div className="field">
                <label htmlFor="p-doctype">Document type</label>
                <select id="p-doctype" value={docType} onChange={(e) => setDocType(e.target.value)}>
                  {DOC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="p-file">File</label>
                <input id="p-file" type="file" required onChange={(e) => setFile(e.target.files?.[0] || null)} />
              </div>
            </div>
            <button type="submit" className="btn btn-primary" disabled={busy || !file}>
              {busy ? "Uploading…" : "Upload and extract"}
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

          <button type="button" className="btn btn-secondary" style={{ marginTop: 16 }}
                  disabled={uploads.length === 0} onClick={() => setStep(2)}>
            Continue to bid details
          </button>
        </Card>
      )}

      {step === 2 && (
        <Card title="Run verification">
          <p className="text-sm text-secondary" style={{ marginBottom: 12 }}>
            Checks every extracted identifier against the relevant authority. Where an authority cannot be
            reached, the result is UNKNOWN with a stated reason — never a guess.
          </p>
          <button type="button" className="btn btn-primary" onClick={onVerify} disabled={busy}>
            {busy ? "Verifying…" : "Run verification"}
          </button>
        </Card>
      )}

      {step === 3 && verifyResult && (
        <Card title="Verification results">
          {verifyResult.outcomes.length === 0 ? (
            <UnavailableNote title="Nothing to verify yet">
              No extracted identifier was available to check against an authority.
            </UnavailableNote>
          ) : (
            <div className="table-frame">
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
          )}
          <button type="button" className="btn btn-primary" style={{ marginTop: 16 }} onClick={() => setStep(4)}>
            Continue
          </button>
        </Card>
      )}

      {step === 4 && (
        <Card title="Submission recorded">
          <Callout strong>
            Your registration and documents for bidder <span className="mono">{bidderId}</span> on tender{" "}
            <span className="mono">{tenderId}</span> are recorded. This is not the auction and it is not a
            final award — the procurement officer still reviews compliance and evidence before a decision is
            published.
          </Callout>
          <div className="btn-group" style={{ marginTop: 16 }}>
            <Link className="btn btn-primary" to="/bidder/my-bids">View in My Bids</Link>
            <Link className="btn btn-secondary" to="/bidder/tenders">Back to tenders</Link>
          </div>
        </Card>
      )}
    </div>
  );
}
