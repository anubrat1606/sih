import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getAuditExport, getBidder } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { useApi } from "../../lib/useApi";
import { decisionsFrom, formatTimestamp, parseAuditExport } from "../../lib/audit";
import { Card, EmptyState, LoadingBlock, PageHeader } from "../../ui/primitives";

// There is no auction in this system (see AuctionPage.jsx), so a bid moves
// straight from participation to evaluation to an officer's decision --
// the full lifecycle a result on this page can honestly pass through.
function resultFor(bidderData, decisionEvent) {
  if (decisionEvent) {
    return decisionEvent.payload.decision === "QUALIFY"
      ? { label: "Awarded / Qualified", tone: "pass", stage: 3 }
      : { label: "Not Awarded / Disqualified", tone: "fail", stage: 3 };
  }
  if (!bidderData) return { label: "Under Evaluation", tone: "unknown", stage: 0 };
  const verdicts = bidderData.verdicts || [];
  if (verdicts.length === 0) return { label: "Under Evaluation", tone: "unknown", stage: 0 };
  return { label: "Compliance Review — decision pending", tone: "partial", stage: 2 };
}

function ResultCard({ tenderId, bidderId }) {
  const audit = useApi(() => getAuditExport(), [tenderId, bidderId]);
  const bidder = useApi(() => getBidder(bidderId, tenderId), [tenderId, bidderId]);

  const decision = useMemo(() => {
    if (!audit.data) return null;
    const events = parseAuditExport(audit.data).filter((e) => e.tender_id === tenderId && e.bidder_id === bidderId);
    return decisionsFrom(events).find((e) => e.event_type === "DECISION_RECORDED") || null;
  }, [audit.data, tenderId, bidderId]);

  const loading = audit.loading || bidder.loading;
  const result = loading ? null : resultFor(bidder.data, decision);

  return (
    <Card title={`${tenderId} · ${bidderId}`}>
      {loading ? <LoadingBlock lines={2} /> : (
        <>
          <div className="row" style={{ gap: 12, alignItems: "center" }}>
            <span className={`badge badge-${result.tone}`}>
              <span className="badge-glyph" aria-hidden="true">
                {result.tone === "pass" ? "✓" : result.tone === "fail" ? "✕" : result.tone === "partial" ? "◑" : "?"}
              </span>
              {result.label}
            </span>
            {decision && <span className="text-xs text-muted">{formatTimestamp(decision.occurred_at)}</span>}
          </div>
          <p className="text-xs text-muted" style={{ marginTop: 10 }}>
            This system runs no live auction — a higher or lower bid amount elsewhere does not determine this
            result. The procurement officer's recorded decision is authoritative, based on verified compliance
            and evidence. Internal evaluation notes and other bidders' standing are not shown here.
          </p>
          <div style={{ marginTop: 12 }}>
            <Link className="btn btn-sm btn-secondary" to={`/bidder/tenders/${encodeURIComponent(tenderId)}`}>
              View tender
            </Link>
          </div>
        </>
      )}
    </Card>
  );
}

export default function ResultsPage() {
  const { tracked } = useBidderSession();
  const [params] = useSearchParams();
  const focusTender = params.get("tender_id");
  const focusBidder = params.get("bidder_id");

  const list = focusTender && focusBidder
    ? [{ tenderId: focusTender, bidderId: focusBidder }]
    : tracked;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bidder Portal"
        title="My Results"
        subtitle="Auction completion, if a tender runs one elsewhere, is not the same as a procurement award. A result appears here only once an officer records a decision, or shows your evaluation status until then."
      />

      {list.length === 0 ? (
        <EmptyState glyph="✓" title="No results yet" message="Participate in a tender to see its status here." />
      ) : (
        <div className="stack" style={{ gap: 16 }}>
          {list.map((t) => <ResultCard key={`${t.tenderId}-${t.bidderId}`} tenderId={t.tenderId} bidderId={t.bidderId} />)}
        </div>
      )}
    </div>
  );
}
