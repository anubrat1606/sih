import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAuditExport, openDocument } from "../api";
import { useApi } from "../lib/useApi";
import { documentsFrom, formatBytes, formatTimestamp, parseAuditExport } from "../lib/audit";
import { DataTable } from "../ui/DataTable";
import { Dash, ErrorState, PageHeader, Tag } from "../ui/primitives";

// Every document the system has ingested, read from the DOCUMENT_INGESTED
// events in the audit log — the authoritative record of what was received,
// when, from whom, and under which content hash.
export default function DocumentsPage() {
  const audit = useApi(() => getAuditExport(), []);
  const [typeFilter, setTypeFilter] = useState("all");

  const documents = useMemo(
    () => (audit.data ? documentsFrom(parseAuditExport(audit.data)) : null),
    [audit.data]
  );

  const types = useMemo(() => {
    const set = new Set((documents || []).map((d) => d.declared_type).filter(Boolean));
    return [...set].sort();
  }, [documents]);

  const filtered = useMemo(() => {
    if (!documents) return null;
    if (typeFilter === "all") return documents;
    return documents.filter((d) => (d.declared_type || "") === typeFilter);
  }, [documents, typeFilter]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Evidence"
        title="Documents"
        subtitle="Every document ingested into the system, addressed by content hash. A document is never edited — a corrected version is a new ingestion, and both stay on record."
      />

      <ErrorState error={audit.error} onRetry={audit.reload} />

      <DataTable
        rows={filtered}
        loading={audit.loading}
        getRowKey={(d) => `${d.seq}`}
        searchPlaceholder="Search by filename, hash, tender or bidder…"
        emptyTitle="No documents ingested yet"
        emptyMessage="Upload a tender notice or a bidder's compliance documents to begin."
        emptyAction={<Link to="/tenders" className="btn btn-primary">Go to tenders</Link>}
        initialSort={{ key: "at", direction: "desc" }}
        filters={types.length ? [{
          id: "type", label: "Type", value: typeFilter, onChange: setTypeFilter,
          options: [{ value: "all", label: "All" }, ...types.map((t) => ({ value: t, label: t }))],
        }] : []}
        columns={[
          {
            key: "file", header: "Document", sortValue: (d) => d.filename, searchValue: (d) => d.filename,
            render: (d) => <span className="cell-primary">{d.filename}</span>,
          },
          {
            key: "type", header: "Declared type", sortValue: (d) => d.declared_type,
            render: (d) => (d.declared_type ? <Tag>{d.declared_type}</Tag> : <span className="text-muted text-sm">unlabelled</span>),
          },
          {
            key: "tender", header: "Tender", sortValue: (d) => d.tender_id, searchValue: (d) => d.tender_id,
            render: (d) => d.tender_id
              ? <Link to={`/tenders/${encodeURIComponent(d.tender_id)}`} className="mono text-sm">{d.tender_id}</Link>
              : <Dash />,
          },
          {
            key: "bidder", header: "Bidder", sortValue: (d) => d.bidder_id, searchValue: (d) => d.bidder_id,
            render: (d) => d.bidder_id
              ? <Link className="mono text-sm"
                      to={`/bidders/${encodeURIComponent(d.bidder_id)}?tender_id=${encodeURIComponent(d.tender_id)}`}>
                  {d.bidder_id}
                </Link>
              : <span className="text-muted text-sm">tender-level</span>,
          },
          {
            key: "size", header: "Size", sortValue: (d) => d.bytes,
            render: (d) => <span className="mono text-sm">{formatBytes(d.bytes) || <Dash />}</span>,
          },
          {
            key: "hash", header: "SHA-256", searchValue: (d) => d.sha256,
            render: (d) => <span className="mono text-xs" title={d.sha256}>{d.sha256.slice(0, 16)}…</span>,
          },
          {
            key: "at", header: "Ingested", sortValue: (d) => d.seq,
            render: (d) => (
              <span>
                <span className="mono text-xs">{formatTimestamp(d.occurred_at)}</span>
                {d.uploaded_by && <div className="text-xs text-muted">by {d.uploaded_by}</div>}
              </span>
            ),
          },
          {
            key: "actions", header: "", align: "right",
            render: (d) => (
              <button type="button" className="btn btn-sm btn-secondary"
                      onClick={() => openDocument(d.sha256).catch((err) => alert(err.message))}>
                View source
              </button>
            ),
          },
        ]}
      />
    </div>
  );
}
