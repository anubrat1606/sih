import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAuditExport, listTenderBidders, listTenders } from "../api";
import { useApi } from "../lib/useApi";
import { parseAuditExport } from "../lib/audit";
import { DataTable } from "../ui/DataTable";
import { Dash, ErrorState, PageHeader, RiskBadge, Tag } from "../ui/primitives";

// There is no "every bidder" endpoint — a bidder only exists in the context
// of a tender. This page composes the real per-tender lists rather than
// inventing a global one, and says plainly which tender each row belongs to.
export default function BiddersPage() {
  // A bidder only exists inside a tender, so the "all bidders" view is
  // composed from the real per-tender lists in one fetch, not invented.
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
  const audit = useApi(() => getAuditExport(), []);
  const [riskFilter, setRiskFilter] = useState("all");

  const documentCounts = useMemo(() => {
    if (!audit.data) return {};
    const counts = {};
    parseAuditExport(audit.data)
      .filter((e) => e.event_type === "DOCUMENT_INGESTED" && e.bidder_id)
      .forEach((e) => {
        const key = `${e.tender_id}::${e.bidder_id}`;
        counts[key] = (counts[key] || 0) + 1;
      });
    return counts;
  }, [audit.data]);

  const decided = useMemo(() => {
    if (!audit.data) return {};
    const out = {};
    parseAuditExport(audit.data)
      .filter((e) => e.event_type === "DECISION_RECORDED")
      .sort((a, b) => a.seq - b.seq)
      .forEach((e) => { out[`${e.tender_id}::${e.bidder_id}`] = e.payload.decision; });
    return out;
  }, [audit.data]);

  const filtered = useMemo(() => {
    const rows = bidderList.data;
    if (!rows) return null;
    if (riskFilter === "all") return rows;
    return rows.filter((r) => r.risk?.level === riskFilter);
  }, [bidderList.data, riskFilter]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Evaluation"
        title="Bidders"
        subtitle="Every bidder registered against a tender in this system, with the compliance picture recorded for them so far."
      />

      <ErrorState error={bidderList.error} onRetry={bidderList.reload} />

      <DataTable
        rows={filtered}
        loading={bidderList.loading}
        getRowKey={(b) => `${b.tender_id}::${b.bidder_id}`}
        searchPlaceholder="Search bidders or tenders…"
        emptyTitle="No bidders registered"
        emptyMessage="A bidder is registered against a specific tender. Open a tender to register one."
        emptyAction={<Link to="/tenders" className="btn btn-primary">Go to tenders</Link>}
        filters={[{
          id: "risk", label: "Risk", value: riskFilter, onChange: setRiskFilter,
          options: [
            { value: "all", label: "All" },
            { value: "HIGH", label: "High" },
            { value: "MEDIUM", label: "Medium" },
            { value: "LOW", label: "Low" },
          ],
        }]}
        columns={[
          {
            key: "bidder", header: "Bidder", sortValue: (b) => b.bidder_id, searchValue: (b) => b.bidder_id,
            render: (b) => (
              <Link className="mono cell-primary"
                    to={`/bidders/${encodeURIComponent(b.bidder_id)}?tender_id=${encodeURIComponent(b.tender_id)}`}>
                {b.bidder_id}
              </Link>
            ),
          },
          {
            key: "tender", header: "Tender", sortValue: (b) => b.tender_id, searchValue: (b) => b.tender_id,
            render: (b) => <Link to={`/tenders/${encodeURIComponent(b.tender_id)}`} className="mono text-sm">{b.tender_id}</Link>,
          },
          {
            key: "docs", header: "Documents", sortValue: (b) => documentCounts[`${b.tender_id}::${b.bidder_id}`] || 0,
            render: (b) => {
              const n = documentCounts[`${b.tender_id}::${b.bidder_id}`] || 0;
              return n === 0
                ? <span className="text-muted text-sm">none uploaded</span>
                : <span className="mono">{n}</span>;
            },
          },
          {
            key: "coverage", header: "Verification", sortValue: (b) => b.metrics?.verification_coverage,
            render: (b) => b.metrics?.verification_coverage == null
              ? <span className="text-muted text-sm">not determined</span>
              : <span className="mono">{Math.round(b.metrics.verification_coverage)}%</span>,
          },
          {
            key: "compliance", header: "Compliance", sortValue: (b) => b.metrics?.compliance_score,
            render: (b) => b.metrics?.compliance_score == null
              ? <span className="text-muted text-sm">not determined</span>
              : <span className="mono">{Math.round(b.metrics.compliance_score)}%</span>,
          },
          {
            key: "risk", header: "Risk", sortValue: (b) => ({ LOW: 0, MEDIUM: 1, HIGH: 2 }[b.risk?.level] ?? 9),
            render: (b) => (b.risk?.level ? <RiskBadge level={b.risk.level} /> : <Dash />),
          },
          {
            key: "status", header: "Status",
            sortValue: (b) => decided[`${b.tender_id}::${b.bidder_id}`] || "UNDER REVIEW",
            render: (b) => {
              const d = decided[`${b.tender_id}::${b.bidder_id}`];
              if (!d) return <Tag>UNDER REVIEW</Tag>;
              return <span className={`badge ${d === "QUALIFY" ? "badge-pass" : "badge-fail"}`}>
                <span className="badge-glyph" aria-hidden="true">{d === "QUALIFY" ? "✓" : "✕"}</span>{d}
              </span>;
            },
          },
          {
            key: "actions", header: "", align: "right",
            render: (b) => (
              <Link className="btn btn-sm btn-secondary"
                    to={`/bidders/${encodeURIComponent(b.bidder_id)}?tender_id=${encodeURIComponent(b.tender_id)}`}>
                Open
              </Link>
            ),
          },
        ]}
      />
    </div>
  );
}
