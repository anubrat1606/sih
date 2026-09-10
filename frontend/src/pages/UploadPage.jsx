import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadDocument, verifyBidder } from "../api";

const DOC_TYPES = ["PAN", "GST", "UDYAM", "EPFO"];

export default function UploadPage() {
  const navigate = useNavigate();
  const [bidderId, setBidderId] = useState("");
  const [tenderId, setTenderId] = useState("");
  const [documentType, setDocumentType] = useState("PAN");
  const [directorName, setDirectorName] = useState("");
  const [address, setAddress] = useState("");
  const [phone, setPhone] = useState("");
  const [bankAccount, setBankAccount] = useState("");
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (!bidderId || !tenderId || !file) {
      setError("bidder ID, tender ID, and a file are all required.");
      return;
    }
    try {
      setStatus("Uploading and running real OCR extraction...");
      await uploadDocument(bidderId, documentType, file);

      setStatus("Running live verification and collusion check...");
      await verifyBidder(bidderId, {
        tender_id: tenderId,
        director_name: directorName,
        address,
        phone,
        bank_account: bankAccount,
      });

      setStatus("Done.");
      navigate(`/dashboard/${encodeURIComponent(tenderId)}`);
    } catch (err) {
      setError(String(err.message || err));
      setStatus("");
    }
  }

  return (
    <div className="page">
      <h1>Bidder Document Upload</h1>
      <p className="hint">
        This calls the real extraction and verification services -- there is no
        sample data path in this form. If a service isn't running, you'll see
        the real error below, not a fake success.
      </p>
      <form onSubmit={handleSubmit} className="form">
        <label>Bidder ID<input value={bidderId} onChange={(e) => setBidderId(e.target.value)} required /></label>
        <label>Tender ID<input value={tenderId} onChange={(e) => setTenderId(e.target.value)} required /></label>
        <label>
          Document type
          <select value={documentType} onChange={(e) => setDocumentType(e.target.value)}>
            {DOC_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <fieldset>
          <legend>Identifying details (for collusion linkage -- real values only)</legend>
          <label>Director name<input value={directorName} onChange={(e) => setDirectorName(e.target.value)} /></label>
          <label>Address<input value={address} onChange={(e) => setAddress(e.target.value)} /></label>
          <label>Phone<input value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
          <label>Bank account<input value={bankAccount} onChange={(e) => setBankAccount(e.target.value)} /></label>
        </fieldset>
        <label>Document file<input type="file" onChange={(e) => setFile(e.target.files[0])} required /></label>
        <button type="submit">Upload &amp; Verify</button>
      </form>
      {status && <p className="status">{status}</p>}
      {error && <p className="error">Error: {error}</p>}
    </div>
  );
}
