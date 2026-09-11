import { useEffect, useState } from "react";
import { getAuditExport, getAuditVerify } from "../api";
import { ErrorBox } from "../components";

export default function AuditPage() {
  const [report, setReport] = useState(null);
  const [exportText, setExportText] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getAuditVerify().then(setReport).catch(setError);
  }, []);

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
      {report && (
        <>
          <p className={report.intact ? "status" : "error"}>
            Chain {report.intact ? "intact" : "BROKEN"}: {report.events} events, {report.linked} linked, {report.rehashed} rehashed.
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
        <pre className="audit-list" style={{ whiteSpace: "pre-wrap", maxHeight: 400, overflow: "auto", background: "white", border: "1px solid #d0d7de", borderRadius: 8, padding: 12 }}>
          {exportText || "(no events yet)"}
        </pre>
      )}
    </div>
  );
}
