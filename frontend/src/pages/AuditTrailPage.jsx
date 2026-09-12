import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAuditExport, getAuditVerify } from "../api";
import { useApi } from "../lib/useApi";
import { formatTimestamp, parseAuditExport, summarizeEvent } from "../lib/audit";
import { useToast } from "../notifications";
import {
  Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Section, Stat, Tag,
} from "../ui/primitives";

// The audit trail is the product's final claim: a third party can re-hash
// every event and check it against the previous one, without trusting this
// application at all.
export default function AuditTrailPage() {
  const { notify } = useToast();
  const events = useApi(() => getAuditExport(), []);
  const [verification, setVerification] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [typeFilter, setTypeFilter] = useState("all");
  const [actorFilter, setActorFilter] = useState("all");
  const [query, setQuery] = useState("");

  const parsed = useMemo(() => (events.data ? parseAuditExport(events.data) : null), [events.data]);

  const types = useMemo(() => [...new Set((parsed || []).map((e) => e.event_type))].sort(), [parsed]);
  const actors = useMemo(() => [...new Set((parsed || []).map((e) => e.actor_kind))].sort(), [parsed]);

  const filtered = useMemo(() => {
    if (!parsed) return null;
    const q = query.trim().toLowerCase();
    return [...parsed]
      .filter((e) => typeFilter === "all" || e.event_type === typeFilter)
      .filter((e) => actorFilter === "all" || e.actor_kind === actorFilter)
      .filter((e) => !q || JSON.stringify(e).toLowerCase().includes(q))
      .sort((a, b) => b.seq - a.seq);
  }, [parsed, typeFilter, actorFilter, query]);

  async function runVerify() {
    setVerifying(true);
    try {
      const body = await getAuditVerify();
      setVerification({ ...body, at: new Date() });
      notify(body.intact ? `Chain intact — ${body.events} events re-hashed.` : "Chain BROKEN — see the breaks below.",
        { kind: body.intact ? "success" : "error" });
    } catch (err) {
      notify(`Verification failed to run: ${err.message}`, { kind: "error" });
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Integrity"
        title="Audit Trail"
        subtitle="Hash-chained and insert-only. Nothing in this system changes state except by appending an event here — projections are rebuilt from it, never patched."
        actions={
          <button type="button" className="btn btn-primary" onClick={runVerify} disabled={verifying}>
            {verifying ? "Re-hashing…" : "Verify chain integrity"}
          </button>
        }
      />

      <ErrorState error={events.error} onRetry={events.reload} />

      {verification && (
        <div className="stat-row" style={{ marginBottom: 20 }}>
          <Stat label="Chain status" value={verification.intact ? "INTACT" : "BROKEN"}
                accent={verification.intact ? "pass" : "fail"}
                note={`verified ${verification.at.toLocaleTimeString()}`} />
          <Stat label="Events re-hashed" value={verification.rehashed} accent="neutral" />
          <Stat label="Links checked" value={verification.linked} accent="neutral" />
          <Stat label="Breaks found" value={verification.breaks.length}
                accent={verification.breaks.length ? "fail" : "pass"} />
        </div>
      )}

      {verification?.breaks?.length > 0 && (
        <Card title="Chain breaks">
          <div className="table-frame">
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th>Sequence</th><th>Detail</th></tr></thead>
                <tbody>
                  {verification.breaks.map((b) => (
                    <tr key={b.seq}><td className="mono">{b.seq}</td><td>{b.detail}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Card>
      )}

      <Section title="Event log"
               note="Every recorded action, newest first. An event is never edited or removed — a correction is a new event.">
        {events.loading ? <LoadingBlock lines={6} /> : !parsed?.length ? (
          <EmptyState glyph="≣" title="No events yet"
                      message="The first event appears as soon as a tender is created."
                      action={<Link to="/officials/tenders" className="btn btn-primary">Go to tenders</Link>} />
        ) : (
          <>
            <div className="toolbar">
              <div className="toolbar-search">
                <input type="search" value={query} placeholder="Search events…" aria-label="Search events"
                       onChange={(e) => setQuery(e.target.value)} />
              </div>
              <div className="row" style={{ gap: 6 }}>
                <label className="field-hint" htmlFor="f-type">Type</label>
                <select id="f-type" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
                        style={{ width: "auto", minWidth: 180 }}>
                  <option value="all">All types</option>
                  {types.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="row" style={{ gap: 6 }}>
                <label className="field-hint" htmlFor="f-actor">Actor</label>
                <select id="f-actor" value={actorFilter} onChange={(e) => setActorFilter(e.target.value)}
                        style={{ width: "auto", minWidth: 120 }}>
                  <option value="all">All actors</option>
                  {actors.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </div>
              <span className="toolbar-count mono">{filtered.length} of {parsed.length}</span>
            </div>

            <div className="table-frame">
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th style={{ width: 70 }}>#</th>
                      <th style={{ width: 190 }}>Timestamp</th>
                      <th style={{ width: 210 }}>Action</th>
                      <th style={{ width: 170 }}>Actor</th>
                      <th style={{ width: 180 }}>Object</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((e) => (
                      <tr key={e.seq}>
                        <td className="mono text-xs">{e.seq}</td>
                        <td className="mono text-xs">{formatTimestamp(e.occurred_at)}</td>
                        <td><span className="text-sm" style={{ fontWeight: 600 }}>{e.event_type}</span></td>
                        <td>
                          <Tag>{e.actor_kind}</Tag>{" "}
                          <span className="mono text-xs">{e.actor_id}</span>
                        </td>
                        <td className="text-xs">
                          {e.tender_id && <div className="mono">{e.tender_id}</div>}
                          {e.bidder_id && <div className="mono text-muted">{e.bidder_id}</div>}
                          {!e.tender_id && !e.bidder_id && <span className="text-muted">—</span>}
                        </td>
                        <td className="cell-note">
                          {summarizeEvent(e)}
                          <div className="text-xs text-muted mono" style={{ marginTop: 4 }}>
                            event {String(e.event_id).slice(0, 8)}…
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <details style={{ marginTop: 16 }}>
              <summary className="text-sm text-secondary" style={{ cursor: "pointer" }}>
                View raw JSON Lines — exactly what an independent verifier re-hashes
              </summary>
              <pre className="mono" style={{
                background: "var(--color-surface)", border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)", padding: 16, overflow: "auto",
                maxHeight: 400, fontSize: 11, marginTop: 8, whiteSpace: "pre-wrap",
              }}>{events.data}</pre>
            </details>
          </>
        )}
      </Section>
    </div>
  );
}
