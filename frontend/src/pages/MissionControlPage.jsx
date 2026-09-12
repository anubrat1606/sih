
import { Link } from "react-router-dom";
import { getAuditExport, getDashboard, getTender, getTenderBlockers, listTenders } from "../api";
import { useApi } from "../lib/useApi";
import { formatDate, formatTimestamp, parseAuditExport, rulePacksByTender, summarizeEvent } from "../lib/audit";
import { DataTable } from "../ui/DataTable";
import { Card, Dash, ErrorState, PageHeader, RiskBar, Section, SkeletonLine, Stat, Tag } from "../ui/primitives";

export default function MissionControlPage() {
  const dashboard = useApi(() => getDashboard(), []);
  const audit = useApi(() => getAuditExport(), []);

  // Tender metadata plus blocker counts, in one composite read. Only a
  // tender with an adopted rule pack can report blockers at all; the rest
  // are counted as "not yet measurable" rather than silently as zero.
  const tenderOverview = useApi(async () => {
    const { tenders: ids } = await listTenders();
    const rows = await Promise.all((ids || []).map((id) => getTender(id).catch(() => ({ tender_id: id }))));
    const counts = await Promise.all(
      (ids || []).map((id) => getTenderBlockers(id).then((b) => b.blockers.length).catch(() => null))
    );
    const measured = counts.filter((c) => c !== null);
    return {
      tenders: rows,
      blockerTotal: measured.reduce((a, b) => a + b, 0),
      blockersPartial: measured.length !== counts.length,
    };
  }, []);

  const tenders = tenderOverview.data?.tenders || null;
  const blockerTotal = tenderOverview.data?.blockerTotal ?? null;
  const blockersPartial = tenderOverview.data?.blockersPartial ?? false;

  const events = audit.data ? parseAuditExport(audit.data) : [];
  const packs = rulePacksByTender(events);
  const decidedBidders = new Set(
    events.filter((e) => e.event_type === "DECISION_RECORDED").map((e) => e.bidder_id)
  );

  const d = dashboard.data;
  const capabilities = d?.capabilities;
  const verificationIssues = capabilities
    ? capabilities.capabilities.filter((c) => c.status !== "LIVE").length
    : null;
  const underReview = d ? Math.max(0, d.bidder_count - decidedBidders.size) : null;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Operations"
        title="Mission Control"
        subtitle="Monitor tenders, bidder compliance and verification status. Every figure below is read from the live event log — nothing is estimated."
        actions={<Link to="/officials/tenders" className="btn btn-primary">Open tenders</Link>}
      />

      <ErrorState error={dashboard.error} onRetry={dashboard.reload} />

      {dashboard.loading ? (
        <div className="stat-row">
          {[0, 1, 2, 3].map((i) => (
            <div className="stat" key={i}><SkeletonLine width="50%" /><SkeletonLine width="70%" /></div>
          ))}
        </div>
      ) : d ? (
        <div className="stat-row">
          <Stat label="Active tenders" value={d.tender_count} accent="neutral"
                note={`${Object.keys(packs).length} with an adopted rule pack`} />
          <Stat label="Bidders under review" value={underReview} accent="partial"
                note={`${d.bidder_count} registered · ${decidedBidders.size} decided`} />
          <Stat label="Verification issues" value={verificationIssues} accent={verificationIssues ? "partial" : "pass"}
                note={capabilities ? `${capabilities.live_count} authority connection(s) live` : undefined} />
          <Stat label="Compliance blockers" value={blockerTotal} accent={blockerTotal ? "fail" : "neutral"}
                note={blockersPartial ? "some tenders have no rule pack yet" : "across all adopted rule packs"} />
        </div>
      ) : null}

      <div className="grid-2" style={{ marginTop: 24 }}>
        <Card title="Risk distribution">
          {d ? <RiskBar low={d.risk_distribution.LOW} medium={d.risk_distribution.MEDIUM} high={d.risk_distribution.HIGH} />
             : <SkeletonLine />}
        </Card>

        <Card title="Verification alerts">
          {!capabilities ? <SkeletonLine /> : (
            capabilities.capabilities.filter((c) => c.status !== "LIVE").length === 0 ? (
              <p className="text-secondary text-sm">Every registered capability is live.</p>
            ) : (
              <div className="stack-sm">
                {capabilities.capabilities.filter((c) => c.status !== "LIVE").map((c) => (
                  <div key={c.adapter_id} className="row" style={{ alignItems: "flex-start", gap: 10 }}>
                    <span aria-hidden="true" style={{ color: "var(--status-partial-fg)" }}>◑</span>
                    <div>
                      <div className="text-sm" style={{ fontWeight: 600 }}>{c.capability_id || c.authority}</div>
                      <div className="text-xs text-secondary">
                        {c.status === "AWAITING_CREDENTIALS"
                          ? "Awaiting credentials — checks return UNKNOWN with a stated reason, never a guess."
                          : (c.detail || "No lawful programmatic source available.")}
                      </div>
                    </div>
                  </div>
                ))}
                <Link to="/officials/verification" className="text-sm">Full verification status →</Link>
              </div>
            )
          )}
        </Card>
      </div>

      <Section title="Active tenders" note="Every tender in the system, with its rule-pack status."
               actions={<Link to="/officials/tenders" className="btn btn-sm btn-secondary">View all</Link>}>
        <DataTable
          rows={tenders}
          loading={tenderOverview.loading}
          error={tenderOverview.error}
          getRowKey={(r) => r.tender_id}
          searchPlaceholder="Search tenders…"
          emptyTitle="No tenders yet"
          emptyMessage="Create a tender to begin evaluating bids against it."
          emptyAction={<Link to="/officials/tenders" className="btn btn-primary">Create a tender</Link>}
          columns={[
            {
              key: "id", header: "Tender ID", sortValue: (r) => r.tender_id, searchValue: (r) => r.tender_id,
              render: (r) => <Link to={`/officials/tenders/${encodeURIComponent(r.tender_id)}`} className="mono">{r.tender_id}</Link>,
            },
            {
              key: "title", header: "Tender", sortValue: (r) => r.title, searchValue: (r) => r.title,
              render: (r) => r.title ? <span className="cell-primary">{r.title}</span> : <Dash />,
            },
            {
              key: "org", header: "Organization", sortValue: (r) => r.issuing_authority, searchValue: (r) => r.issuing_authority,
              render: (r) => r.issuing_authority || <Dash />,
            },
            {
              key: "deadline", header: "Deadline", sortValue: (r) => r.bid_submission_deadline,
              render: (r) => r.bid_submission_deadline ? <span className="mono">{formatDate(r.bid_submission_deadline)}</span> : <Dash />,
            },
            {
              key: "pack", header: "Rule pack", sortValue: (r) => (packs[r.tender_id] ? 1 : 0),
              render: (r) => packs[r.tender_id]
                ? <Tag accent>ADOPTED</Tag>
                : <Tag>NOT ADOPTED</Tag>,
            },
          ]}
        />
      </Section>

      <div className="grid-2" style={{ marginTop: 24 }}>
        <Card title="Recent officer decisions">
          {dashboard.loading ? <SkeletonLine /> : !d?.recent_decisions?.length ? (
            <p className="text-secondary text-sm">No QUALIFY or DISQUALIFY decision has been recorded yet.</p>
          ) : (
            <div className="stack-sm">
              {d.recent_decisions.slice(0, 6).map((row, i) => (
                <div key={i} className="row" style={{ justifyContent: "space-between", gap: 12 }}>
                  <span className="text-sm">
                    <Link to={`/officials/bidders/${encodeURIComponent(row.bidder_id)}?tender_id=${encodeURIComponent(row.tender_id)}`} className="mono">
                      {row.bidder_id}
                    </Link>
                    <span className="text-muted"> on </span>
                    <span className="mono">{row.tender_id}</span>
                  </span>
                  <span className="row" style={{ gap: 8 }}>
                    <span className={`badge ${row.decision === "QUALIFY" ? "badge-pass" : "badge-fail"}`}>
                      <span className="badge-glyph" aria-hidden="true">{row.decision === "QUALIFY" ? "✓" : "✕"}</span>
                      {row.decision}
                    </span>
                    <span className="text-xs text-muted mono">{formatTimestamp(row.occurred_at)}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Recent audit activity"
              actions={<Link to="/officials/audit" className="btn btn-sm btn-ghost">Audit trail →</Link>}>
          {audit.loading ? <SkeletonLine /> : audit.error ? (
            <ErrorState error={audit.error} onRetry={audit.reload} />
          ) : events.length === 0 ? (
            <p className="text-secondary text-sm">No events recorded yet.</p>
          ) : (
            <div className="timeline">
              {[...events].sort((a, b) => b.seq - a.seq).slice(0, 6).map((e) => (
                <div className="timeline-item" key={e.seq}>
                  <div className="timeline-rail"><span className="timeline-dot" /><span className="timeline-line" /></div>
                  <div className="timeline-body">
                    <div className="timeline-head">
                      <span className="timeline-type">{e.event_type}</span>
                      <span className="timeline-meta mono">#{e.seq} · {formatTimestamp(e.occurred_at)}</span>
                    </div>
                    <div className="timeline-detail">{summarizeEvent(e)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
