import { Link, useParams } from "react-router-dom";
import { PageHeader } from "../../ui/primitives";
import { BackendPendingNotice } from "../components/BackendPendingNotice";

// This screen is a pure, honest placeholder. SATYAPRAMĀṆ is a compliance
// verification layer, not an e-auction engine -- see bidderApi.js's
// getAuctionState/submitAuctionBid, both of which reject with
// BackendNotImplementedError because no such backend exists anywhere in
// this system. Nothing here fakes a countdown, a bid ledger or a live
// status; all of that would require a real auction feed to be built first.
export default function AuctionPage() {
  const { tenderId } = useParams();

  return (
    <div className="page page-narrow" style={{ maxWidth: 680 }}>
      <PageHeader
        eyebrow={tenderId ? <Link to={`/bidder/tenders/${encodeURIComponent(tenderId)}`}>Tender {tenderId}</Link> : "Bidder Portal"}
        title="Upcoming Auctions"
        subtitle="Live bidding is not part of this system today."
      />
      <BackendPendingNotice endpoint="GET /tenders/{tender_id}/auction · POST /tenders/{tender_id}/auction/bids">
        SATYAPRAMĀṆ verifies a bidder's compliance against a tender's rule pack — it does not run or record a
        live e-auction. If this tender runs a bidding round on GeM or another platform, it happens there, not
        here. Building this screen for real would require a genuine auction feed and bid-submission endpoint
        on the backend, neither of which exist yet, rather than a countdown timer that isn't backed by anything.
      </BackendPendingNotice>
    </div>
  );
}
