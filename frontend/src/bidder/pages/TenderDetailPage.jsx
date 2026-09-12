import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getMyTenderRequirements, getMyTenders } from "../bidderApi";
import { useApi } from "../../lib/useApi";
import { formatDate } from "../../lib/audit";
import { DataTable } from "../../ui/DataTable";
import {
  Dash, EmptyState, ErrorState, Field, LoadingBlock, PageHeader, Section, Tabs, Tag, UnavailableNote,
} from "../../ui/primitives";

// Round 6, R3.
const TABS = [
  { id: "overview", label: "Overview" },
  { id: "eligibility", label: "Eligibility" },
  { id: "documents", label: "Documents" },
  { id: "dates", label: "Important dates" },
];

const STATUS_LABEL = {
  NOT_REGISTERED: "Not registered",
  REGISTERED: "Registered",
  DOCUMENTS_RECEIVED: "Documents received",
  UNDER_EVALUATION: "Under evaluation",
  DECIDED: "Decided",
};

// Takes a list so more dates can be added later without redesigning this.
function ImportantDates({ items }) {
  return (
    <div className="stack-sm">
      {items.map((it) => (
        <div key={it.label} className="row" style={{ justifyContent: "space-between", maxWidth: 420 }}>
          <span className="text-secondary text-sm">{it.label}</span>
          <span className="mono">{it.date ? formatDate(it.date) : "not stated"}</span>
        </div>
      ))}
    </div>
  );
}

export default function TenderDetailPage() {
  const { tenderId } = useParams();
  const [params, setParams] = useSearchParams();
  const activeTab = params.get("tab") || "overview";

  // GET /me/tenders is the only source of this tender's own public fields --
  // bidderApi.js has no single-tender fetch, so this finds it in the list
  // it already has rather than calling an endpoint that doesn't exist.
  const tenders = useApi(getMyTenders, []);
  const tender = useMemo(
    () => tenders.data?.tenders?.find((t) => t.tender_id === tenderId) || null,
    [tenders.data, tenderId]
  );

  // Only fetched once the tender's own record says a pack is adopted --
  // skips the call entirely otherwise, rather than depending on guessing
  // what error shape an unadopted tender's requirements endpoint returns.
  const requirements = useApi(
    () => getMyTenderRequirements(tenderId),
    [tenderId],
    { skip: !tender?.requirements_published }
  );

  function setTab(id) {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    setParams(next, { replace: true });
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow={<Link to="/portal/tenders">Tenders</Link>}
        title={tender?.title || tenderId}
        subtitle={tender?.description}
        actions={
          <>
            {tender?.registered ? (
              <Link className="btn btn-primary" to={`/portal/tenders/${encodeURIComponent(tenderId)}/submit`}>
                Submit documents
              </Link>
            ) : (
              <button type="button" className="btn btn-primary" disabled
                      title="Register with the procuring office before submitting documents">
                Submit documents
              </button>
            )}
            <Link className="btn btn-secondary" to="/portal/submissions">View my submission</Link>
          </>
        }
      />

      <ErrorState error={tenders.error} onRetry={tenders.reload} />

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body">
          {tenders.loading ? <LoadingBlock lines={2} /> : (
            <div className="field-grid">
              <Field label="Tender ID"><span className="mono">{tenderId}</span></Field>
              <Field label="Organisation" empty={!tender?.issuing_authority}>
                {tender?.issuing_authority || "not recorded"}
              </Field>
              <Field label="Department" empty={!tender?.department}>
                {tender?.department || "not recorded"}
              </Field>
              <Field label="Category">
                {tender?.category ? <Tag>{tender.category}</Tag> : <span className="text-muted">not recorded</span>}
              </Field>
              <Field label="Deadline" empty={!tender?.bid_submission_deadline}>
                {tender?.bid_submission_deadline ? <span className="mono">{formatDate(tender.bid_submission_deadline)}</span> : "not stated"}
              </Field>
              <Field label="Your status">
                {tender ? <Tag accent={tender.status === "DECIDED"}>{STATUS_LABEL[tender.status] || tender.status}</Tag> : <Dash />}
              </Field>
            </div>
          )}
        </div>
      </div>

      <Tabs tabs={TABS} active={activeTab} onChange={setTab} />

      {activeTab === "overview" && (
        <Section title="About this tender">
          {!tender ? (
            tenders.loading ? <LoadingBlock lines={3} /> : (
              <EmptyState glyph="⌕" title="Tender not found"
                          message="This tender either doesn't exist or isn't visible to you yet." />
            )
          ) : (
            <p className="text-secondary text-sm">
              {tender.description || "No description recorded for this tender."}
            </p>
          )}
        </Section>
      )}

      {activeTab === "eligibility" && (
        <Section
          title="Eligibility requirements"
          note="These are the requirements the procuring officer adopted for this tender. Verification is performed by the procurement office; this list is what you'll be assessed against."
        >
          {!tender?.requirements_published ? (
            <UnavailableNote title="Requirements have not been published for this tender">
              Check back once the procuring office adopts a rule pack for this tender.
            </UnavailableNote>
          ) : (
            <DataTable
              rows={requirements.data?.requirements || null}
              loading={requirements.loading}
              error={requirements.error}
              getRowKey={(r) => r.id}
              searchPlaceholder="Search requirements…"
              emptyTitle="No requirements recorded"
              columns={[
                { key: "id", header: "Requirement", sortValue: (r) => r.id, searchValue: (r) => r.id,
                  render: (r) => <span className="mono">{r.id}</span> },
                { key: "text", header: "Text", searchValue: (r) => r.text,
                  render: (r) => r.text },
                { key: "obligation", header: "Obligation", sortValue: (r) => r.obligation,
                  render: (r) => <Tag accent={r.obligation === "mandatory"}>{(r.obligation || "").toUpperCase()}</Tag> },
                { key: "evidence", header: "Evidence expected",
                  render: (r) => r.evidence_expected || <Dash /> },
                { key: "page", header: "Source page", sortValue: (r) => r.source_page,
                  render: (r) => (r.source_page != null ? <span className="mono text-sm">{r.source_page}</span> : <Dash />) },
              ]}
            />
          )}
        </Section>
      )}

      {activeTab === "documents" && (
        <Section title="Tender documents">
          <UnavailableNote title="Not available in this view yet">
            The tender's own published notice isn't currently exposed through the bidder portal's API.
            This is a real gap, not a hidden feature — ask the procuring office directly if you need the
            original notice.
          </UnavailableNote>
        </Section>
      )}

      {activeTab === "dates" && (
        <Section title="Important dates">
          {!tender ? <LoadingBlock lines={2} /> : (
            <ImportantDates items={[
              { label: "Issue date", date: tender.issue_date },
              { label: "Bid submission deadline", date: tender.bid_submission_deadline },
            ]} />
          )}
        </Section>
      )}
    </div>
  );
}
