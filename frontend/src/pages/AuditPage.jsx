import { useEffect, useState } from "react";
import { getAuditExport, getAuditVerify } from "../api";
import { ErrorBox } from "../components";

export default function AuditPage() {
  const [report, setReport] = useState(null);
  const [exportText, setExportText] = useState(null);
  const [error, setError] = useState(null);
  // Starts true: the initial mount fetch below is already in flight by the
  // time this first renders, so the loading state is a fact from the start,
  // never a synchronous setState inside the effect itself.
  const [verifying, setVerifying] = useState(true);
  const [verifiedAt, setVerifiedAt] = useState(null);

  function fetchVerify() {
    getAuditVerify()
      .then((body) => { setReport(body); setVerifiedAt(new Date()); setError(null); })
      .catch(setError)
      .finally(() => setVerifying(false));
  }

  useEffect(fetchVerify, []);

  function runVerify() {
    setVerifying(true);
    fetchVerify();
  }

  async function loadExport() {
    setError(null);
    try {
      setExportText(await getAuditExport());
    } catch (err) {
      setError(err);
    }
  }

  return (
    <div className="page">
      <h1>Audit log</h1>
      <p className="hint">
        Hash-chained and insert-only. This is what a third party verifies without
        trusting this application at all -- independent re-hashing of every event,
        checked against the previous event's hash.
      </p>
      <ErrorBox error={error} />

      <div className="actions">
        <button onClick={runVerify} disabled={verifying}>
          {verifying ? "Verifying…" : "Verify chain now"}
        </button>
      </div>

      {verifying && <p className="hint">Re-hashing every event and checking each one against the previous event's hash…</p>}

      {report && !verifying && (
        <>
          <p className={report.intact ? "status" : "error"}>
            Chain {report.intact ? "intact" : "BROKEN"}: {report.events} events, {report.linked} linked, {report.rehashed} rehashed.
            {verifiedAt && ` Verified live at ${verifiedAt.toLocaleTimeString()}.`}
          </p>
          {report.breaks.length > 0 && (
            <table className="evidence-table">
              <thead><tr><th>Seq</th><th>Detail</th></tr></thead>
              <tbody>
                {report.breaks.map((b) => <tr key={b.seq}><td>{b.seq}</td><td>{b.detail}</td></tr>)}
              </tbody>
            </table>
          )}
        </>
      )}

      <div className="actions">
        <button onClick={loadExport}>Load full JSON Lines export</button>
      </div>
      {exportText !== null && (
        <pre className="audit-list" style={{ whiteSpace: "pre-wrap", maxHeight: 400, overflow: "auto", background: "var(--color-surface)", color: "var(--color-text)", border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)", padding: "var(--space-3)" }}>
          {exportText || "(no events yet)"}
        </pre>
      )}
    </div>
  );
}
