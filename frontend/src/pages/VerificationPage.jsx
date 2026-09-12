import { useMemo } from "react";
import { Link } from "react-router-dom";
import { getAuditExport, getCapabilities } from "../api";
import { useApi } from "../lib/useApi";
import { formatTimestamp, parseAuditExport, verificationEventsFrom } from "../lib/audit";
import { DataTable } from "../ui/DataTable";
import {
  CapabilityBadge, Dash, EmptyState, ErrorState, LoadingBlock, PageHeader,
  Section, Stat, Tag, UnavailableNote,
} from "../ui/primitives";

// What this deployment can and cannot independently verify, stated plainly,
// plus every verification actually attempted. A capability with no
// credentials is shown as exactly that — never hidden, and never silently
// treated as a pass.
export default function VerificationPage() {
  const capabilities = useApi(() => getCapabilities(), []);
  const audit = useApi(() => getAuditExport(), []);

  const rows = capabilities.data?.capabilities || null;
  const events = useMemo(
    () => (audit.data ? verificationEventsFrom(parseAuditExport(audit.data)) : null),
    [audit.data]
  );

  const live = rows?.filter((c) => c.status === "LIVE").length ?? null;
  const awaiting = rows?.filter((c) => c.status === "AWAITING_CREDENTIALS").length ?? null;
  const unavailable = rows?.filter((c) => c.status === "UNAVAILABLE").length ?? null;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Authorities"
        title="Verification"
        subtitle="Which authorities this deployment can independently check a claim against, and every verification it has actually attempted."
      />

      <ErrorState error={capabilities.error} onRetry={capabilities.reload} />

      <div className="stat-row">
        <Stat label="Live connections" value={live} accent="pass" note="answering with real authority data" />
        <Stat label="Awaiting credentials" value={awaiting} accent="partial" note="configured, not yet authorised" />
        <Stat label="No lawful source" value={unavailable} accent="neutral" note="confirmed unavailable, not outstanding work" />
      </div>

      <Section title="Capability register"
               note="Each row is an authority this system knows how to ask, and the exact state of that connection today.">
        {capabilities.loading ? <LoadingBlock /> : (
          <DataTable
            rows={rows}
            getRowKey={(c) => c.adapter_id}
            searchPlaceholder="Search authorities…"
            emptyTitle="No capabilities registered"
            columns={[
              { key: "authority", header: "Authority", sortValue: (c) => c.authority, searchValue: (c) => c.authority,
                render: (c) => <span className="cell-primary">{c.authority}</span> },
              { key: "cap", header: "Capability", sortValue: (c) => c.capability_id,
                render: (c) => (c.capability_id ? <span className="mono text-sm">{c.capability_id}</span> : <Dash />) },
              { key: "status", header: "Status", sortValue: (c) => c.status,
                render: (c) => <CapabilityBadge status={c.status} /> },
              { key: "tier", header: "Evidence tier", sortValue: (c) => c.tier,
                render: (c) => (c.tier ? <Tag>TIER {c.tier}</Tag> : <Dash />) },
              { key: "channel", header: "Channel", sortValue: (c) => c.channel,
                render: (c) => c.channel || <Dash /> },
              { key: "detail", header: "Detail", className: "cell-note",
                render: (c) => c.detail || (
                  c.status === "AWAITING_CREDENTIALS"
                    ? "Configured but not authorised — every check returns UNKNOWN with a stated reason."
                    : c.status === "LIVE" ? "Answering with real authority data." : <Dash />
                ) },
            ]}
          />
        )}
      </Section>

      <Section title="Verification activity"
               note="Every verification this system has requested, observed or failed to obtain — in order, from the audit log.">
        {audit.loading ? <LoadingBlock /> : !events?.length ? (
          <EmptyState
            glyph="⛉"
            title="No verification attempted yet"
            message="Verifications run once a bidder's documents have been ingested and a check is requested."
            action={<Link to="/officials/bidders" className="btn btn-secondary">Go to bidders</Link>}
          />
        ) : (
          <DataTable
            rows={events}
            getRowKey={(e) => String(e.seq)}
            searchPlaceholder="Search verification events…"
            initialSort={{ key: "seq", direction: "desc" }}
            columns={[
              { key: "seq", header: "#", sortValue: (e) => e.seq, width: 70,
                render: (e) => <span className="mono text-xs">{e.seq}</span> },
              { key: "type", header: "Event", sortValue: (e) => e.event_type, searchValue: (e) => e.event_type,
                render: (e) => {
                  const cls = e.event_type === "VERIFICATION_OBSERVED" ? "badge-pass"
                            : e.event_type === "VERIFICATION_FAILED" ? "badge-unknown" : "badge-info";
                  const glyph = e.event_type === "VERIFICATION_OBSERVED" ? "✓"
                            : e.event_type === "VERIFICATION_FAILED" ? "?" : "→";
                  return <span className={`badge ${cls}`}>
                    <span className="badge-glyph" aria-hidden="true">{glyph}</span>
                    {e.event_type.replace("VERIFICATION_", "")}
                  </span>;
                } },
              { key: "cap", header: "Capability", sortValue: (e) => e.payload.capability_id, searchValue: (e) => e.payload.capability_id,
                render: (e) => <span className="mono text-sm">{e.payload.capability_id}</span> },
              { key: "bidder", header: "Bidder", sortValue: (e) => e.bidder_id, searchValue: (e) => e.bidder_id,
                render: (e) => e.bidder_id
                  ? <Link className="mono text-sm"
                          to={`/officials/bidders/${encodeURIComponent(e.bidder_id)}?tender_id=${encodeURIComponent(e.tender_id)}`}>
                      {e.bidder_id}
                    </Link>
                  : <Dash /> },
              { key: "outcome", header: "Outcome", className: "cell-note",
                render: (e) => e.payload.reason_code
                  ? <span><span className="mono text-xs">{e.payload.reason_code}</span>{e.payload.detail ? ` — ${e.payload.detail}` : ""}</span>
                  : (e.payload.observed_at ? <span className="mono text-xs">observed {e.payload.observed_at}</span> : <Dash />) },
              { key: "at", header: "When", sortValue: (e) => e.seq,
                render: (e) => <span className="mono text-xs">{formatTimestamp(e.occurred_at)}</span> },
            ]}
          />
        )}
      </Section>

      {capabilities.data?.note && (
        <div style={{ marginTop: 20 }}>
          <UnavailableNote title="Current verification posture">{capabilities.data.note}</UnavailableNote>
        </div>
      )}
    </div>
  );
}
