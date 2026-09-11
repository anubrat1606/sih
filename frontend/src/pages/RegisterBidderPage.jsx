import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { registerBidder, uploadDocument, verifyBidder } from "../api";
import { ErrorBox } from "../components";
import { useToast } from "../notifications";

const DOC_TYPES = ["PAN", "GST", "UDYAM", "CIN", "EPFO"];

export default function RegisterBidderPage() {
  const navigate = useNavigate();
  const { notify } = useToast();
  const [tenderId, setTenderId] = useState("");
  const [bidderId, setBidderId] = useState("");
  const [attrs, setAttrs] = useState({ director_name: "", address: "", phone: "", bank_account: "" });
  const [registered, setRegistered] = useState(null);
  const [docType, setDocType] = useState(DOC_TYPES[0]);
  const [file, setFile] = useState(null);
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
      await uploadDocument(bidderId, tenderId, file, docType);
      setFile(null);
      e.target.reset();
      notify("Document uploaded and extracted.", { kind: "success" });
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
      notify("Verification complete.", { kind: "success" });
    } catch (err) {
      setError(err);
      notify("Verification failed.", { kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <h1>Register a bidder</h1>
      <p className="hint">
        Attributes below (director name, address, phone, bank account) are only
        used for collusion linking -- whatever subset you provide is used,
        registration is never all-or-nothing.
      </p>
      <ErrorBox error={error} />

      {!registered ? (
        <form className="form" onSubmit={onRegister}>
          <label>Tender ID<input value={tenderId} onChange={(e) => setTenderId(e.target.value)} required /></label>
          <label>Bidder ID<input value={bidderId} onChange={(e) => setBidderId(e.target.value)} required /></label>
          <fieldset>
            <legend>Collusion-linking attributes (optional)</legend>
            {Object.keys(attrs).map((key) => (
              <label key={key}>
                {key.replace("_", " ")}
                <input value={attrs[key]} onChange={(e) => setAttrs({ ...attrs, [key]: e.target.value })} />
              </label>
            ))}
          </fieldset>
          <button type="submit" disabled={busy}>Register bidder</button>
        </form>
      ) : (
        <>
          <p className="status">Registered {bidderId} on {tenderId}.
            {registered.shared_attribute_links.length > 0 &&
              ` Shares an attribute with: ${registered.shared_attribute_links.map((l) => `${l.with} (${l.attribute})`).join(", ")}.`}
          </p>

          <h2>Upload a document</h2>
          <form className="form" onSubmit={onUpload}>
            <label>Document type
              <select value={docType} onChange={(e) => setDocType(e.target.value)}>
                {DOC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label>File<input type="file" onChange={(e) => setFile(e.target.files[0])} required /></label>
            <button type="submit" disabled={busy || !file}>Upload</button>
          </form>

          <h2>Verify</h2>
          <p className="hint">Runs every registered capability against what's been extracted so far.</p>
          <div className="actions">
            <button onClick={onVerify} disabled={busy}>Run verification</button>
            <button onClick={() => navigate(`/tenders/${encodeURIComponent(tenderId)}`)}>Go to tender dashboard</button>
          </div>

          {verifyResult && (
            <table className="evidence-table">
              <thead><tr><th>Capability</th><th>Result</th><th>Reason</th><th>Detail</th></tr></thead>
              <tbody>
                {verifyResult.outcomes.map((o) => (
                  <tr key={o.capability_id}>
                    <td>{o.capability_id}</td>
                    <td>{o.verdict}</td>
                    <td>{o.reason_code || "—"}</td>
                    <td className="details">{o.detail || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
