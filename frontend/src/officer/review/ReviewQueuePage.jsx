import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getReviewQueue } from "../../api";
import { useApi } from "../../lib/useApi";
import { DataTable } from "../../ui/DataTable";
import { PageHeader, RiskBadge, Tag } from "../../ui/primitives";

const STATUS_LABEL = {
  REGISTERED: "Registered",
  DOCUMENTS_RECEIVED: "Documents received",
  UNDER_EVALUATION: "Under evaluation",
  DECIDED: "Decided",
};

const RISK_ORDER = { HIGH: 2, MEDIUM: 1, LOW: 0 };

// Every bidder across every tender that may need a human decision, one
// table instead of walking tenders one at a time. Row -> the existing
// BidderCompliancePage, where the Finalise panel (round 6) actually
// records the decision -- this page only triages who needs one next.
export default function ReviewQueuePage() {
  const navigate = useNavigate();
  const queue = useApi(() => getReviewQueue(), []);
  const [onlyNeedsDecision, setOnlyNeedsDecision] = useState("yes");

  const rows = useMemo(() => {
    const all = queue.data?.bidders || [];
    return onlyNeedsDecision === "yes" ? all.filter((b) => b.needs_decision) : all;
  }, [queue.data, onlyNeedsDecision]);

  return (
    <div className="page">
      <PageHeader eyebrow="Officer review desk" title="Review queue"
                 subtitle="Every bidder that may need a decision, across every tender." />

      <DataTable
        loading={queue.loading}
        error={queue.error}
        rows={rows}
        getRowKey={(r) => `${r.tender_id}::${r.bidder_id}`}
        onRowClick={(r) => navigate(`/bidders/${encodeURIComponent(r.bidder_id)}?tender_id=${encodeURIComponent(r.tender_id)}#decision`)}
        searchPlaceholder="Search by tender or bidder ID…"
        filters={[
          { id: "needs_decision", label: "Show", value: onlyNeedsDecision, onChange: setOnlyNeedsDecision,
            options: [{ value: "yes", label: "Needs a decision" }, { value: "all", label: "Every bidder" }] },
        ]}
        initialSort={{ key: "risk", direction: "desc" }}
        emptyTitle="Nothing to review"
        emptyMessage="No bidder currently needs a decision."
        columns={[
          { key: "tender_id", header: "Tender", render: (r) => <span className="mono">{r.tender_id}</span>,
            sortValue: (r) => r.tender_id, searchValue: (r) => r.tender_id },
          { key: "bidder_id", header: "Bidder", render: (r) => <span className="mono">{r.bidder_id}</span>,
            sortValue: (r) => r.bidder_id, searchValue: (r) => r.bidder_id },
          { key: "status", header: "Status", render: (r) => STATUS_LABEL[r.status] || r.status,
            sortValue: (r) => r.status },
          { key: "risk", header: "Risk", render: (r) => <RiskBadge level={r.risk?.level} />,
            sortValue: (r) => RISK_ORDER[r.risk?.level] ?? -1 },
          { key: "collusion", header: "Shared attribute", align: "center",
            render: (r) => r.collusion?.flagged ? <Tag accent>Flagged</Tag> : "—",
            sortValue: (r) => (r.collusion?.flagged ? 1 : 0) },
          { key: "mandatory_bad", header: "Mandatory FAIL/UNKNOWN", align: "right",
            render: (r) => r.mandatory_fail_or_unknown_count,
            sortValue: (r) => r.mandatory_fail_or_unknown_count },
          { key: "needs_decision", header: "Decision", align: "right",
            render: (r) => r.needs_decision ? <Tag accent>Needs decision</Tag> : "Decided" },
        ]}
      />
    </div>
  );
}
