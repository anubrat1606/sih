import { Link } from "react-router-dom";
import { getBidder } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { useApi } from "../../lib/useApi";
import { EmptyState, LoadingBlock, PageHeader, RiskBadge } from "../../ui/primitives";

function TrackedRow({ tenderId, bidderId, trackedAt, onForget }) {
  const bidder = useApi(() => getBidder(bidderId, tenderId), [tenderId, bidderId]);
  const b = bidder.data;
  const verdicts = b?.verdicts || [];
  const status = bidder.loading
    ? "Checking…"
    : bidder.error
      ? "Not found"
      : verdicts.length === 0
        ? "Awaiting evaluation"
        : verdicts.some((v) => v.verdict_effective === "FAIL") ? "Compliance issues found"
        : verdicts.some((v) => v.verdict_effective === "UNKNOWN") ? "Verification incomplete"
        : verdicts.some((v) => v.verdict_effective === "PARTIAL") ? "Partially compliant"
        : "Compliant on evaluated requirements";

  return (
    <tr>
      <td><Link to={`/bidder/tenders/${encodeURIComponent(tenderId)}`} className="mono">{tenderId}</Link></td>
      <td className="mono text-sm">{bidderId}</td>
      <td className="text-sm">
        {bidder.loading ? <LoadingBlock lines={1} /> : status}
      </td>
      <td>{b?.metrics?.compliance_score == null ? <span className="text-muted text-sm">—</span> : <span className="mono">{Math.round(b.metrics.compliance_score)}%</span>}</td>
      <td>{b?.risk ? <RiskBadge level={b.risk.level} /> : <span className="text-muted text-sm">—</span>}</td>
      <td className="text-xs text-muted">{new Date(trackedAt).toLocaleDateString()}</td>
      <td className="cell-actions">
        <Link className="btn btn-sm btn-secondary" to={`/bidder/results?tender_id=${encodeURIComponent(tenderId)}&bidder_id=${encodeURIComponent(bidderId)}`}>
          View result
        </Link>
        <button type="button" className="btn btn-sm btn-ghost" onClick={onForget}>Remove</button>
      </td>
    </tr>
  );
}

export default function MyBidsPage() {
  const { tracked, forgetBid } = useBidderSession();

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bidder Portal"
        title="My Bids"
        subtitle="Tenders you've registered on in this browser. Since bidder accounts aren't live yet, this list lives only on this device — it clears if you clear your browser data."
      />

      {tracked.length === 0 ? (
        <EmptyState
          glyph="☑"
          title="No bids tracked yet"
          message="Participate in a tender to see its status here."
          action={<Link className="btn btn-primary" to="/bidder/tenders">Browse tenders</Link>}
        />
      ) : (
        <div className="table-frame">
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Tender</th><th>Bidder ID</th><th>Status</th><th>Compliance</th><th>Risk</th><th>Tracked since</th><th />
                </tr>
              </thead>
              <tbody>
                {tracked.map((t) => (
                  <TrackedRow key={`${t.tenderId}-${t.bidderId}`} {...t}
                              onForget={() => forgetBid(t.tenderId, t.bidderId)} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
