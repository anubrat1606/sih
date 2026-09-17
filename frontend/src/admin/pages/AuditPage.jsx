import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAuditExport, getAuditVerify, getCapabilities } from "../../api";
import { useApi } from "../../lib/useApi";
import { formatTimestamp, parseAuditExport } from "../../lib/audit";
import { useToast } from "../../notifications";
import {
  Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Section, Stat,
} from "../../ui/primitives";

// Round 7, Rishika. Built entirely on the two existing calls
// AuditTrailPage.jsx already uses (getAuditExport, getAuditVerify) plus the
// existing getCapabilities -- no new backend endpoint. The "officer
// activity" list below is computed here, from the same real event export;
// it isn't a capability the backend exposes on its own.
const STATUS_LABEL = { LIVE: "Live", AWAITING_CREDENTIALS: "Awaiting credentials", UNAVAILABLE: "No lawful source" };

function officerActivityFrom(events) {
  const byActor = {};
  for (const e of events) {
    if (e.actor_kind !== "HUMAN") continue;
    const row = byActor[e.actor_id] || { actor_id: e.actor_id, count: 0, latest: null };
    row.count += 1;
    if (!row.latest || e.occurred_at > row.latest) row.latest = e.occurred_at;
    byActor[e.actor_id] = row;
  }
  return Object.values(byActor).sort((a, b) => (b.latest || "").localeCompare(a.latest || ""));
}

export default function AuditPage() {
  const { notify } = useToast();
  const events = useApi(getAuditExport, []);
  const capabilities = useApi(getCapabilities, []);
  const [verification, setVerification] = useState(null);
  const [verifying, setVerifying] = useState(false);

  const parsed = useMemo(() => (events.data ? parseAuditExport(events.data) : null), [events.data]);
  const officerActivity = useMemo(() => (parsed ? officerActivityFrom(parsed) : null), [parsed]);

  async function runVerify() {
    setVerifying(true);
    try {
      const body = await getAuditVerify();
      setVerification({ ...body, at: new Date() });
      notify(body.intact ? `Chain intact — ${body.rehashed} events re-hashed.` : "Chain BROKEN — see the breaks below.",
        { kind: body.intact ? "success" : "error" });
    } catch (err) {
      notify(`Verification failed to run: ${err.message}`, { kind: "error" });
    } finally {
      setVerifying(false);
    }
  }

  const liveCount = capabilities.data?.capabilities?.filter((c) => c.status === "LIVE").length;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Admin console"
        title="Audit & System"
        subtitle="The full event log's own integrity, every verification authority in detail, and who's actually been acting on this deployment — all read live, nothing pre-computed."
      />

      <Section title="Chain integrity"
               note="Re-hashes every event in the log against the one before it, right now, in this browser.">
        <Card
          actions={
            <button type="button" className="btn btn-primary btn-sm" onClick={runVerify} disabled={verifying}>
              {verifying ? "Re-hashing…" : "Verify now"}
            </button>
          }
        >
          {!verification ? (
            <p className="text-sm text-muted">Not verified this session yet — click "Verify now."</p>
          ) : (
            <div className="stat-row">
              <Stat label="Chain status" value={verification.intact ? "INTACT" : "BROKEN"}
                    accent={verification.intact ? "pass" : "fail"}
                    note={`verified ${verification.at.toLocaleTimeString()}`} />
              <Stat label="Events re-hashed" value={verification.rehashed} accent="neutral" />
              <Stat label="Links checked" value={verification.linked} accent="neutral" />
              <Stat label="Breaks found" value={verification.breaks.length}
                    accent={verification.breaks.length ? "fail" : "pass"} />
            </div>
          )}
          <p className="text-xs text-muted" style={{ marginTop: 14 }}>
            <Link to="/audit">Full event log, search and filters →</Link>
          </p>
        </Card>

        {verification?.breaks?.length > 0 && (
          <Card title="Chain breaks" flush>
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
      </Section>

      <Section title="Capability registry"
               note="Every field this deployment's live capability registry returns, not just status.">
        {capabilities.loading ? <LoadingBlock lines={4} /> : capabilities.error || !capabilities.data ? (
          <ErrorState error={capabilities.error || new Error("Registry unavailable")} onRetry={capabilities.reload} />
        ) : (
          <>
            <p className="text-sm text-secondary" style={{ marginBottom: 12 }}>
              <strong className="text-pass">{liveCount}</strong> of {capabilities.data.capabilities.length} capabilities live.
            </p>
            <div className="table-frame">
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Authority</th><th>Capability</th><th>Status</th>
                      <th>Tier</th><th>Channel</th><th>As-of supported</th><th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {capabilities.data.capabilities.map((c) => (
                      <tr key={c.adapter_id}>
                        <td className="cell-primary">{c.authority}</td>
                        <td className="mono text-sm">{c.capability_id || "—"}</td>
                        <td>
                          <span className={`admin-authority-status admin-authority-status-${c.status.toLowerCase()}`}>
                            {STATUS_LABEL[c.status] || c.status}
                          </span>
                        </td>
                        <td className="text-sm">{c.tier ?? "—"}</td>
                        <td className="text-sm">{c.channel || "—"}</td>
                        <td className="text-sm">{c.as_of_supported ? "Yes" : "No"}</td>
                        <td className="text-xs text-secondary">{c.detail || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </Section>

      <Section title="Officer activity"
               note="Every human actor in the event log, grouped by who they are — their total recorded actions and the most recent one. Computed from the real event export, not a separate endpoint.">
        {events.loading ? <LoadingBlock lines={3} /> : events.error ? (
          <ErrorState error={events.error} onRetry={events.reload} />
        ) : !officerActivity?.length ? (
          <EmptyState glyph="≣" title="No officer activity yet"
                      message="An officer's first recorded action (adopting a rule pack, recording a decision, and so on) will appear here." />
        ) : (
          <div className="table-frame">
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th>Officer</th><th>Events recorded</th><th>Most recent activity</th></tr></thead>
                <tbody>
                  {officerActivity.map((row) => (
                    <tr key={row.actor_id}>
                      <td className="mono">{row.actor_id}</td>
                      <td className="mono">{row.count}</td>
                      <td className="mono text-sm">{formatTimestamp(row.latest)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Section>
    </div>
  );
}
