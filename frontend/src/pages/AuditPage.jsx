import { useEffect, useMemo, useState } from "react";
import { getAuditExport, getAuditVerify } from "../api";
import { AuditTimeline } from "../AuditTimeline";
import { ErrorBox } from "../components";
import { useToast } from "../notifications";
import { SkeletonLine } from "../Skeleton";

export default function AuditPage() {
  const { notify } = useToast();
  const [report, setReport] = useState(null);
  const [exportText, setExportText] = useState(null);
  const [error, setError] = useState(null);
  // Starts true: the initial mount fetch below is already in flight by the
  // time this first renders, so the loading state is a fact from the start,
  // never a synchronous setState inside the effect itself.
  const [verifying, setVerifying] = useState(true);
  const [verifiedAt, setVerifiedAt] = useState(null);
  const [filterType, setFilterType] = useState("");

  function fetchVerify() {
    getAuditVerify()
      .then((body) => {
        setReport(body);
        setVerifiedAt(new Date());
        setError(null);
        notify(body.intact ? `Chain intact: ${body.events} events verified.` : "Chain BROKEN — see the breaks below.",
          { kind: body.intact ? "success" : "error" });
      })
      .catch((err) => { setError(err); notify("Chain verification failed to run.", { kind: "error" }); })
      .finally(() => setVerifying(false));
  }

  // notify() is stable (useCallback in ToastProvider) -- deliberately not
  // re-running this on every render just because the context identity check
  // can't see that.
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
      notify("Could not load the audit log.", { kind: "error" });
    }
  }

  // GET /audit/export is JSON Lines, one object per line -- the first line
  // is chain metadata (no event_type), the rest are real events. Parsed
  // once per exportText change, not on every render.
  const events = useMemo(() => {
    if (!exportText) return null;
    return exportText.split("\n").filter((l) => l.trim())
      .map((l) => { try { return JSON.parse(l); } catch { return null; } })
      .filter((e) => e && e.event_type);
  }, [exportText]);

  const eventTypes = useMemo(() => {
    if (!events) return [];
    return [...new Set(events.map((e) => e.event_type))].sort();
  }, [events]);

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

      {verifying && (
        <div className="stack">
          <SkeletonLine width="70%" />
        </div>
      )}

      {report && !verifying && (
        <>
          <p className={report.intact ? "status" : "error"}>
            Chain {report.intact ? "intact" : "BROKEN"}: {report.events} events, {report.linked} linked, {report.rehashed} rehashed.
            {verifiedAt && ` Verified live at ${verifiedAt.toLocaleTimeString()}.`}
          </p>
          {report.breaks.length > 0 && (
            <div className="table-scroll">
              <table className="evidence-table">
                <thead><tr><th>Seq</th><th>Detail</th></tr></thead>
                <tbody>
                  {report.breaks.map((b) => <tr key={b.seq}><td>{b.seq}</td><td>{b.detail}</td></tr>)}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      <div className="actions">
        <button onClick={loadExport}>Load the full audit log</button>
      </div>

      {events && (
        events.length === 0 ? (
          <p className="hint">No events yet.</p>
        ) : (
          <>
            <div className="actions">
              <label>Filter by event type
                <select value={filterType} onChange={(e) => setFilterType(e.target.value)}>
                  <option value="">All types</option>
                  {eventTypes.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
            </div>
            <AuditTimeline events={events} filterType={filterType || undefined} />
            <details>
              <summary className="hint">View raw JSON Lines (what a third party actually re-hashes)</summary>
              <pre className="audit-list" style={{ whiteSpace: "pre-wrap", maxHeight: 400, overflow: "auto", background: "var(--color-surface)", color: "var(--color-text)", border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)", padding: "var(--space-3)" }}>
                {exportText}
              </pre>
            </details>
          </>
        )
      )}
    </div>
  );
}
