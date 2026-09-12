import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAuditExport, getTender, listTenders } from "../bidderApi";
import { useApi } from "../../lib/useApi";
import { formatDate, parseAuditExport, rulePacksByTender } from "../../lib/audit";
import { DataTable } from "../../ui/DataTable";
import { Dash, ErrorState, PageHeader, Tag } from "../../ui/primitives";

export default function TendersPage() {
  const tenderList = useApi(() => listTenders(), []);
  const audit = useApi(() => getAuditExport(), []);
  const [rows, setRows] = useState(null);
  const [categoryFilter, setCategoryFilter] = useState("all");

  const packs = useMemo(() => (audit.data ? rulePacksByTender(parseAuditExport(audit.data)) : {}), [audit.data]);

  useEffect(() => {
    const ids = tenderList.data?.tenders;
    if (!ids) return;
    let cancelled = false;
    Promise.all(ids.map((id) => getTender(id).catch(() => ({ tender_id: id }))))
      .then((r) => { if (!cancelled) setRows(r); });
    return () => { cancelled = true; };
  }, [tenderList.data]);

  const categories = useMemo(() => {
    const set = new Set((rows || []).map((r) => r.category).filter(Boolean));
    return [...set].sort();
  }, [rows]);

  const filtered = useMemo(() => {
    if (!rows) return null;
    if (categoryFilter === "all") return rows;
    return rows.filter((r) => (r.category || "") === categoryFilter);
  }, [rows, categoryFilter]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bidder Portal"
        title="Tenders"
        subtitle="Every tender recorded in this system. Fields not published by the issuing authority are shown as not stated, never guessed."
      />

      <ErrorState error={tenderList.error} onRetry={tenderList.reload} />

      <DataTable
        rows={filtered}
        loading={tenderList.loading || (tenderList.data && !rows)}
        getRowKey={(r) => r.tender_id}
        searchPlaceholder="Search by ID, title or organization…"
        emptyTitle="No tenders published yet"
        emptyMessage="Check back once a tender is recorded in the system."
        initialSort={{ key: "deadline", direction: "asc" }}
        filters={categories.length ? [{
          id: "cat", label: "Category", value: categoryFilter, onChange: setCategoryFilter,
          options: [{ value: "all", label: "All" }, ...categories.map((c) => ({ value: c, label: c }))],
        }] : []}
        columns={[
          {
            key: "id", header: "Tender ID", sortValue: (r) => r.tender_id, searchValue: (r) => r.tender_id,
            render: (r) => <Link to={`/bidder/tenders/${encodeURIComponent(r.tender_id)}`} className="mono">{r.tender_id}</Link>,
          },
          {
            key: "title", header: "Title", sortValue: (r) => r.title, searchValue: (r) => r.title,
            render: (r) => r.title ? <span className="cell-primary">{r.title}</span> : <Dash />,
          },
          {
            key: "org", header: "Organization", sortValue: (r) => r.issuing_authority, searchValue: (r) => r.issuing_authority,
            render: (r) => r.issuing_authority || <Dash />,
          },
          {
            key: "cat", header: "Category", sortValue: (r) => r.category,
            render: (r) => (r.category ? <Tag>{r.category}</Tag> : <Dash />),
          },
          {
            key: "issue", header: "Published", sortValue: (r) => r.issue_date,
            render: (r) => r.issue_date ? <span className="mono">{formatDate(r.issue_date)}</span> : <span className="text-muted text-sm">not stated</span>,
          },
          {
            key: "deadline", header: "Bid submission deadline", sortValue: (r) => r.bid_submission_deadline,
            render: (r) => r.bid_submission_deadline
              ? <span className="mono">{formatDate(r.bid_submission_deadline)}</span>
              : <span className="text-muted text-sm">not stated</span>,
          },
          {
            key: "status", header: "Status", sortValue: (r) => (packs[r.tender_id] ? "Evaluating" : "Draft"),
            render: (r) => packs[r.tender_id] ? <Tag accent>ACCEPTING BIDS</Tag> : <Tag>AWAITING RULE PACK</Tag>,
          },
          {
            key: "actions", header: "", align: "right",
            render: (r) => <Link to={`/bidder/tenders/${encodeURIComponent(r.tender_id)}`} className="btn btn-sm btn-secondary">View details</Link>,
          },
        ]}
      />
    </div>
  );
}
