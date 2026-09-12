
import { Link } from "react-router-dom";
import { listTenderBidders, listTenders } from "../api";
import { useApi } from "../lib/useApi";
import { DataTable } from "../ui/DataTable";
import { Callout, ErrorState, PageHeader, RiskBadge, Section } from "../ui/primitives";

// Evidence lives per bidder — this is the way in. Each row opens that
// bidder's graph, where a requirement can be walked back to the exact page
// of the exact document it was read from.
export default function EvidencePage() {
  const bidderList = useApi(async () => {
    const { tenders } = await listTenders();
    const lists = await Promise.all(
      (tenders || []).map((tid) =>
        listTenderBidders(tid)
          .then((b) => (b.bidders || []).map((row) => ({ ...row, tender_id: tid })))
          .catch(() => [])
      )
    );
    return lists.flat();
  }, []);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Investigation"
        title="Evidence"
        subtitle="Trace any verdict back to the document, page and authority that produced it."
      />

      <ErrorState error={bidderList.error} onRetry={bidderList.reload} />

      <Callout strong>
        Every verdict this system produces is reproducible from the evidence behind it — the same evidence,
        the same rule version and the same deterministic code always give the same answer.
      </Callout>

      <Section title="Open an evidence graph">
        <DataTable
          rows={bidderList.data}
          loading={bidderList.loading}
          getRowKey={(b) => `${b.tender_id}::${b.bidder_id}`}
          searchPlaceholder="Search bidders or tenders…"
          emptyTitle="No evidence recorded yet"
          emptyMessage="Evidence appears once a bidder has been registered and their documents ingested."
          emptyAction={<Link to="/officials/tenders" className="btn btn-primary">Go to tenders</Link>}
          columns={[
            { key: "bidder", header: "Bidder", sortValue: (b) => b.bidder_id, searchValue: (b) => b.bidder_id,
              render: (b) => <span className="mono cell-primary">{b.bidder_id}</span> },
            { key: "tender", header: "Tender", sortValue: (b) => b.tender_id, searchValue: (b) => b.tender_id,
              render: (b) => <Link className="mono text-sm" to={`/officials/tenders/${encodeURIComponent(b.tender_id)}`}>{b.tender_id}</Link> },
            { key: "coverage", header: "Verification coverage", sortValue: (b) => b.metrics?.verification_coverage,
              render: (b) => b.metrics?.verification_coverage == null
                ? <span className="text-muted text-sm">not determined</span>
                : <span className="mono">{Math.round(b.metrics.verification_coverage)}%</span> },
            { key: "confidence", header: "Evidence confidence", sortValue: (b) => b.metrics?.evidence_confidence,
              render: (b) => b.metrics?.evidence_confidence == null
                ? <span className="text-muted text-sm">not determined</span>
                : <span className="mono">{Math.round(b.metrics.evidence_confidence)}%</span> },
            { key: "risk", header: "Risk", sortValue: (b) => ({ LOW: 0, MEDIUM: 1, HIGH: 2 }[b.risk?.level] ?? 9),
              render: (b) => <RiskBadge level={b.risk?.level} /> },
            { key: "actions", header: "", align: "right",
              render: (b) => (
                <span className="btn-group">
                  <Link className="btn btn-sm btn-secondary"
                        to={`/officials/bidders/${encodeURIComponent(b.bidder_id)}?tender_id=${encodeURIComponent(b.tender_id)}&tab=evidence`}>
                    Evidence list
                  </Link>
                  <Link className="btn btn-sm btn-primary"
                        to={`/officials/bidders/${encodeURIComponent(b.bidder_id)}/evidence-graph?tender_id=${encodeURIComponent(b.tender_id)}`}>
                    Open graph
                  </Link>
                </span>
              ) },
          ]}
        />
      </Section>
    </div>
  );
}
