import { Link } from "react-router-dom";
import { getMySubmission, getMyTenders } from "../bidderApi";
import { useApi } from "../../lib/useApi";
import { DataTable } from "../../ui/DataTable";
import { ErrorState, PageHeader } from "../../ui/primitives";

// One row per tender this bidder is actually registered on — "my
// submissions" has nothing to say about a tender they haven't joined.
// Discovery of tenders they're NOT yet on lives on the Tenders page
// (Rishika's R2), not here.

const STATUS_LABEL = {
  REGISTERED: "Registered",
  DOCUMENTS_RECEIVED: "Documents received",
  UNDER_EVALUATION: "Under evaluation",
  DECIDED: "Decision recorded",
};

// Reuses the four existing badge colours (never a fifth) the same way
// ui/primitives.jsx's own ReviewBadge/CapabilityBadge do for a
// non-verdict status: registered is the neutral/unknown tone, documents
// received and under evaluation are the partial (in-progress) tone,
// and a recorded decision is the pass tone — this is a lifecycle stage,
// not a compliance outcome, so the colour never claims QUALIFY/DISQUALIFY.
function submissionStatusBadge(status) {
  const cls = status === "DECIDED" ? "badge-pass"
    : status === "DOCUMENTS_RECEIVED" || status === "UNDER_EVALUATION" ? "badge-partial"
    : "badge-unknown";
  return (
    <span className={`badge ${cls}`}>
      <span className="badge-glyph" aria-hidden="true">●</span>
      {STATUS_LABEL[status] || status}
    </span>
  );
}

export default function SubmissionsPage() {
  const submissions = useApi(async () => {
    const { tenders } = await getMyTenders();
    const registered = tenders.filter((t) => t.registered);
    return Promise.all(
      registered.map(async (t) => {
        const sub = await getMySubmission(t.tender_id);
        return { ...t, documentCount: sub.documents.length };
      })
    );
  }, []);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bidder"
        title="My submissions"
        subtitle="Every tender you're registered on, and what you've submitted to it so far."
      />

      <ErrorState error={submissions.error} onRetry={submissions.reload} />

      <DataTable
        rows={submissions.data}
        loading={submissions.loading}
        getRowKey={(t) => t.tender_id}
        searchPlaceholder="Search by tender ID or title…"
        emptyTitle="Nothing here yet"
        emptyMessage="You haven't been registered on a tender yet. Ask the procuring office."
        initialSort={{ key: "tender", direction: "asc" }}
        columns={[
          {
            key: "tender", header: "Tender", sortValue: (t) => t.tender_id, searchValue: (t) => t.tender_id,
            render: (t) => (
              <div>
                <span className="mono cell-primary">{t.tender_id}</span>
                {t.title && <div className="text-xs text-secondary">{t.title}</div>}
              </div>
            ),
          },
          {
            key: "status", header: "Status", sortValue: (t) => t.status,
            render: (t) => submissionStatusBadge(t.status),
          },
          {
            key: "docs", header: "Documents received", sortValue: (t) => t.documentCount,
            render: (t) => <span className="mono">{t.documentCount}</span>,
          },
          {
            // No "last upload" column here: /me/tenders/{id}/submission
            // returns each DOCUMENT_INGESTED event's raw payload, which
            // carries no timestamp field — there is nothing real to show
            // for it without a backend change. Flagged in the PR rather
            // than filled in with something invented.
            key: "actions", header: "", align: "right",
            render: (t) => (
              <Link
                className="btn btn-sm btn-secondary"
                to={`/portal/tenders/${encodeURIComponent(t.tender_id)}/submit`}
              >
                {t.status === "DECIDED" ? "View" : "Continue"}
              </Link>
            ),
          },
        ]}
      />
    </div>
  );
}
