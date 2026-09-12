import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getMyTenders } from "../bidderApi";
import { useApi } from "../../lib/useApi";
import { formatDate } from "../../lib/audit";
import { DataTable } from "../../ui/DataTable";
import { Dash, ErrorState, PageHeader, Tag } from "../../ui/primitives";

// Round 6, R2.
const STATUS_LABEL = {
  NOT_REGISTERED: "Not registered",
  REGISTERED: "Registered",
  DOCUMENTS_RECEIVED: "Documents received",
  UNDER_EVALUATION: "Under evaluation",
  DECIDED: "Decided",
};

export default function TendersPage() {
  const { data, error, loading, reload } = useApi(getMyTenders, []);
  const [orgFilter, setOrgFilter] = useState("all");
  const [catFilter, setCatFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  const rows = data?.tenders || null;

  const organisations = useMemo(() => {
    const set = new Set((rows || []).map((t) => t.issuing_authority).filter(Boolean));
    return [...set].sort();
  }, [rows]);
  const categories = useMemo(() => {
    const set = new Set((rows || []).map((t) => t.category).filter(Boolean));
    return [...set].sort();
  }, [rows]);
  const statuses = useMemo(() => {
    const set = new Set((rows || []).map((t) => t.status).filter(Boolean));
    return [...set];
  }, [rows]);

  const filtered = useMemo(() => {
    if (!rows) return null;
    return rows.filter((t) => {
      if (orgFilter !== "all" && t.issuing_authority !== orgFilter) return false;
      if (catFilter !== "all" && (t.category || "") !== catFilter) return false;
      if (statusFilter !== "all" && t.status !== statusFilter) return false;
      return true;
    });
  }, [rows, orgFilter, catFilter, statusFilter]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bidder portal"
        title="Tenders"
        subtitle="Every tender you're registered on, plus every published tender you can still register interest in."
      />
      <ErrorState error={error} onRetry={reload} />

      {/* This table renders its full filtered/sorted set client-side.
          DataTable doesn't expose its internal filtered rows to the parent,
          so there's no clean hook to page on top of it here -- fine while
          the list is small. The first thing to add if /me/tenders ever
          grows past a few hundred rows is server-side paging on that
          endpoint, not a client-side workaround bolted onto this table. */}
      <DataTable
        rows={filtered}
        loading={loading}
        getRowKey={(t) => t.tender_id}
        searchPlaceholder="Search by ID, title or organisation…"
        emptyTitle="No tenders yet"
        emptyMessage="Nothing has been published to you yet. Check back later or ask the procuring office."
        initialSort={{ key: "deadline", direction: "asc" }}
        filters={[
          { id: "org", label: "Organisation", value: orgFilter, onChange: setOrgFilter,
            options: [{ value: "all", label: "All" }, ...organisations.map((o) => ({ value: o, label: o }))] },
          ...(categories.length ? [{
            id: "cat", label: "Category", value: catFilter, onChange: setCatFilter,
            options: [{ value: "all", label: "All" }, ...categories.map((c) => ({ value: c, label: c }))],
          }] : []),
          ...(statuses.length ? [{
            id: "status", label: "Your status", value: statusFilter, onChange: setStatusFilter,
            options: [{ value: "all", label: "All" },
              ...statuses.map((s) => ({ value: s, label: STATUS_LABEL[s] || s }))],
          }] : []),
        ]}
        columns={[
          { key: "id", header: "Tender ID", sortValue: (t) => t.tender_id, searchValue: (t) => t.tender_id,
            render: (t) => <Link className="mono" to={`/portal/tenders/${encodeURIComponent(t.tender_id)}`}>{t.tender_id}</Link> },
          { key: "title", header: "Title", sortValue: (t) => t.title, searchValue: (t) => t.title,
            render: (t) => t.title ? <span className="cell-primary">{t.title}</span> : <Dash /> },
          { key: "org", header: "Organisation", sortValue: (t) => t.issuing_authority, searchValue: (t) => t.issuing_authority,
            render: (t) => t.issuing_authority || <Dash /> },
          { key: "dept", header: "Department", sortValue: (t) => t.department,
            render: (t) => t.department || <Dash /> },
          { key: "cat", header: "Category", sortValue: (t) => t.category,
            render: (t) => t.category ? <Tag>{t.category}</Tag> : <Dash /> },
          { key: "issued", header: "Issued", sortValue: (t) => t.issue_date,
            render: (t) => t.issue_date ? <span className="mono text-sm">{formatDate(t.issue_date)}</span> : <Dash /> },
          { key: "deadline", header: "Deadline", sortValue: (t) => t.bid_submission_deadline,
            render: (t) => t.bid_submission_deadline
              ? <span className="mono text-sm">{formatDate(t.bid_submission_deadline)}</span>
              : <span className="text-muted text-sm">not stated</span> },
          { key: "requirements", header: "Requirements", sortValue: (t) => (t.requirements_published ? 1 : 0),
            render: (t) => t.requirements_published ? <Tag accent>PUBLISHED</Tag> : <Tag>NOT YET</Tag> },
          { key: "status", header: "Your status", sortValue: (t) => t.status,
            render: (t) => <span className="text-sm">{STATUS_LABEL[t.status] || t.status}</span> },
          { key: "actions", header: "", align: "right",
            render: (t) => (
              <Link className="btn btn-sm btn-secondary" to={`/portal/tenders/${encodeURIComponent(t.tender_id)}`}>
                View
              </Link>
            ) },
        ]}
      />
    </div>
  );
}
