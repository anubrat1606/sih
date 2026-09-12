import { useMemo } from "react";
import { getAuditExport } from "../bidderApi";
import { useBidderSession } from "../BidderSessionContext";
import { useApi } from "../../lib/useApi";
import { documentsFrom, formatBytes, formatTimestamp, parseAuditExport } from "../../lib/audit";
import { EmptyState, LoadingBlock, PageHeader, Tag } from "../../ui/primitives";

export default function DocumentsPage() {
  const { tracked } = useBidderSession();
  const audit = useApi(() => getAuditExport(), []);

  const myDocuments = useMemo(() => {
    if (!audit.data) return [];
    const events = parseAuditExport(audit.data);
    const mine = new Set(tracked.map((t) => `${t.tenderId}::${t.bidderId}`));
    return documentsFrom(events).filter((d) => d.bidder_id && mine.has(`${d.tender_id}::${d.bidder_id}`));
  }, [audit.data, tracked]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bidder Portal"
        title="Documents"
        subtitle="Every document you've uploaded for a tracked bid, read straight from the audit log."
      />

      {audit.loading ? <LoadingBlock lines={3} /> : myDocuments.length === 0 ? (
        <EmptyState glyph="▥" title="No documents uploaded yet"
                    message="Documents you upload while participating in a tender will appear here." />
      ) : (
        <div className="table-frame">
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Document</th><th>Type</th><th>Tender</th><th>Size</th><th>Uploaded</th></tr></thead>
              <tbody>
                {myDocuments.map((d) => (
                  <tr key={d.seq}>
                    <td className="cell-primary">{d.filename}</td>
                    <td>{d.declared_type ? <Tag>{d.declared_type}</Tag> : "—"}</td>
                    <td className="mono text-sm">{d.tender_id}</td>
                    <td className="mono text-sm">{formatBytes(d.bytes)}</td>
                    <td className="mono text-xs">{formatTimestamp(d.occurred_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
