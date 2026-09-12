import { useMemo } from "react";
import { Link } from "react-router-dom";
import { getAuditExport, getTender, listTenders } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { useApi } from "../../lib/useApi";
import { formatDate, parseAuditExport, rulePacksByTender } from "../../lib/audit";
import { Card, Dash, EmptyState, ErrorState, LoadingBlock, PageHeader, Stat, Tag } from "../../ui/primitives";

export default function DashboardPage() {
  const { profile, tracked } = useBidderSession();
  const tenderIds = useApi(() => listTenders(), []);
  const audit = useApi(() => getAuditExport(), []);

  const packs = useMemo(() => (audit.data ? rulePacksByTender(parseAuditExport(audit.data)) : {}), [audit.data]);
  const ids = tenderIds.data?.tenders || [];
  const activeBidCount = tracked.length;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bidder Portal"
        title={`Welcome${profile?.fullName ? `, ${profile.fullName}` : ""}`}
        subtitle="Every figure below comes straight from the live tender register — nothing here is a sample."
      />

      {!profile && (
        <Card>
          <p className="text-sm">
            You're browsing without an account. <Link to="/bidder/signup">Create one</Link> to track your
            participation across sessions — note that self-service bidder accounts aren't live on the backend
            yet, so this is a local preview only. You can still discover tenders and register directly below.
          </p>
        </Card>
      )}

      <div className="metric-triad" style={{ marginTop: 20 }}>
        <Stat label="Available tenders" value={tenderIds.loading ? "…" : ids.length} accent="neutral" />
        <Stat label="My active bids" value={activeBidCount} note="tracked in this browser" accent={activeBidCount ? "accent" : "neutral"} />
        <Stat label="Tenders with an adopted rule pack" value={audit.loading ? "…" : Object.keys(packs).length} accent="neutral" />
      </div>

      <ErrorState error={tenderIds.error} onRetry={tenderIds.reload} />

      <div style={{ marginTop: 24 }}>
        <Card title="Upcoming bidding" actions={<Link to="/bidder/tenders" className="btn btn-sm btn-secondary">View all tenders</Link>}>
          {tenderIds.loading ? <LoadingBlock lines={3} /> : ids.length === 0 ? (
            <EmptyState glyph="◌" title="No tenders published yet" message="Check back once a tender is recorded in the system." />
          ) : (
            <TenderPreviewList tenderIds={ids.slice(0, 6)} packs={packs} />
          )}
        </Card>
      </div>

      {tracked.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <Card title="Your tracked bids" actions={<Link to="/bidder/my-bids" className="btn btn-sm btn-secondary">Open My Bids</Link>}>
            <div className="stack-sm">
              {tracked.slice(0, 5).map((t) => (
                <div key={`${t.tenderId}-${t.bidderId}`} className="row" style={{ justifyContent: "space-between" }}>
                  <Link to={`/bidder/tenders/${encodeURIComponent(t.tenderId)}`} className="mono">{t.tenderId}</Link>
                  <span className="text-xs text-muted">bidder ID {t.bidderId}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function TenderPreviewList({ tenderIds, packs }) {
  const rows = useApi(
    () => Promise.all(tenderIds.map((id) => getTender(id).catch(() => ({ tender_id: id })))),
    [tenderIds.join(",")]
  );
  if (rows.loading) return <LoadingBlock lines={3} />;
  if (!rows.data?.length) return <Dash />;
  return (
    <div className="stack-sm">
      {rows.data.map((t) => (
        <div key={t.tender_id} className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <span>
            <Link to={`/bidder/tenders/${encodeURIComponent(t.tender_id)}`} className="cell-primary">
              {t.title || t.tender_id}
            </Link>
            <div className="text-xs text-muted">{t.issuing_authority || "issuing authority not recorded"}</div>
          </span>
          <span className="row" style={{ gap: 8 }}>
            {t.category && <Tag>{t.category}</Tag>}
            {t.bid_submission_deadline
              ? <span className="mono text-xs">closes {formatDate(t.bid_submission_deadline)}</span>
              : <span className="text-xs text-muted">no deadline stated</span>}
            {packs[t.tender_id] ? <Tag accent>RULE PACK ADOPTED</Tag> : <Tag>DRAFT</Tag>}
          </span>
        </div>
      ))}
    </div>
  );
}
