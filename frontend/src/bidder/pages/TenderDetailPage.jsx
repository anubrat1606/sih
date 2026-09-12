import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { getAuditExport, getTender } from "../bidderApi";
import { useApi } from "../../lib/useApi";
import { documentsFrom, formatBytes, formatDate, formatTimestamp, parseAuditExport, rulePacksByTender } from "../../lib/audit";
import { BackendPendingNotice } from "../components/BackendPendingNotice";
import {
  Card, Dash, EmptyState, ErrorState, Field, LoadingBlock, PageHeader, Section, Tabs, Tag, UnavailableNote,
} from "../../ui/primitives";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "eligibility", label: "Eligibility" },
  { id: "documents", label: "Documents" },
  { id: "bid", label: "Bid Information" },
];

export default function TenderDetailPage() {
  const { tenderId } = useParams();
  const [params, setParams] = useSearchParams();
  const activeTab = params.get("tab") || "overview";

  const tender = useApi(() => getTender(tenderId), [tenderId]);
  const audit = useApi(() => getAuditExport(), [tenderId]);

  const events = useMemo(
    () => (audit.data ? parseAuditExport(audit.data).filter((e) => e.tender_id === tenderId) : []),
    [audit.data, tenderId]
  );
  const pack = useMemo(() => rulePacksByTender(events)[tenderId] || null, [events, tenderId]);
  const documents = useMemo(() => documentsFrom(events).filter((d) => !d.bidder_id), [events]);

  function setTab(id) {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    setParams(next, { replace: true });
  }

  const t = tender.data;

  return (
    <div className="page">
      <PageHeader
        eyebrow={<Link to="/bidder/tenders">Tenders</Link>}
        title={t?.title || tenderId}
        subtitle={t?.description}
        actions={
          <>
            <Link to={`/bidder/tenders/${encodeURIComponent(tenderId)}/participate`} className="btn btn-primary">
              Participate
            </Link>
          </>
        }
      />

      <ErrorState error={tender.error} onRetry={tender.reload} />

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-body">
          {tender.loading ? <LoadingBlock lines={2} /> : (
            <div className="field-grid">
              <Field label="Tender ID"><span className="mono">{tenderId}</span></Field>
              <Field label="Organization" empty={!t?.issuing_authority}>{t?.issuing_authority || "not recorded"}</Field>
              <Field label="Department" empty={!t?.department}>{t?.department || "not recorded"}</Field>
              <Field label="Category">{t?.category ? <Tag>{t.category}</Tag> : <span className="text-muted">not recorded</span>}</Field>
              <Field label="Published" empty={!t?.issue_date}>
                {t?.issue_date ? <span className="mono">{formatDate(t.issue_date)}</span> : "not stated"}
              </Field>
              <Field label="Bid submission deadline" empty={!t?.bid_submission_deadline}>
                {t?.bid_submission_deadline ? <span className="mono">{formatDate(t.bid_submission_deadline)}</span> : "not stated"}
              </Field>
            </div>
          )}
        </div>
      </div>

      <Tabs
        tabs={TABS.map((tab) => ({ ...tab, count: tab.id === "documents" ? documents.length : undefined }))}
        active={activeTab}
        onChange={setTab}
      />

      {activeTab === "overview" && (
        <Section title="Important dates">
          <div className="field-grid">
            <Field label="Published" empty={!t?.issue_date}>{t?.issue_date ? formatDate(t.issue_date) : "not stated"}</Field>
            <Field label="Bid submission deadline" empty={!t?.bid_submission_deadline}>
              {t?.bid_submission_deadline ? formatDate(t.bid_submission_deadline) : "not stated"}
            </Field>
          </div>
          <p className="text-xs text-muted" style={{ marginTop: 12 }}>
            Fields such as estimated value and a separate bid-opening date appear here only once the issuing
            authority records them against this tender — none are shown as placeholders.
          </p>
        </Section>
      )}

      {activeTab === "eligibility" && (
        <Section title="Eligibility requirements"
                 note="The rule pack an officer has adopted to evaluate every bid on this tender.">
          {pack ? (
            <>
              <Card>
                <div className="field-grid">
                  <Field label="Rule pack version"><span className="mono">{pack.version}</span></Field>
                  <Field label="Requirements"><span className="mono">{pack.requirement_count}</span></Field>
                  <Field label="Adopted">{formatTimestamp(pack.at)}</Field>
                </div>
              </Card>
              <div style={{ marginTop: 12 }}>
                <BackendPendingNotice endpoint="GET /tenders/{tender_id}/rule-pack">
                  The individual requirement text (what exactly must be submitted for each check) cannot be
                  listed here yet — the backend can confirm a rule pack of {pack.requirement_count} requirement(s)
                  was adopted, but has no endpoint to return its contents. Once you participate and upload your
                  documents, your own results will show each requirement you were evaluated against.
                </BackendPendingNotice>
              </div>
            </>
          ) : (
            <UnavailableNote title="No rule pack adopted yet">
              This tender cannot be evaluated until an officer adopts a rule pack. Bids may still be prepared,
              but eligibility cannot be confirmed until one exists.
            </UnavailableNote>
          )}
        </Section>
      )}

      {activeTab === "documents" && (
        <Section title="Tender documents" note="Published by the issuing authority — not your own submission.">
          {audit.loading ? <LoadingBlock /> : documents.length === 0 ? (
            <EmptyState glyph="◌" title="No tender documents published yet" />
          ) : (
            <div className="table-frame">
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>Document</th><th>Type</th><th>Size</th><th>Published</th></tr></thead>
                  <tbody>
                    {documents.map((d) => (
                      <tr key={d.seq}>
                        <td className="cell-primary">{d.filename}</td>
                        <td>{d.declared_type ? <Tag>{d.declared_type}</Tag> : <Dash />}</td>
                        <td className="mono text-sm">{formatBytes(d.bytes)}</td>
                        <td className="mono text-xs">{formatTimestamp(d.occurred_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </Section>
      )}

      {activeTab === "bid" && (
        <Section title="Bid information">
          <p className="text-sm text-secondary" style={{ marginBottom: 12 }}>
            To submit a bid on this tender, register as a bidder, upload your compliance documents, and run
            verification — all from the Participate flow.
          </p>
          <Link to={`/bidder/tenders/${encodeURIComponent(tenderId)}/participate`} className="btn btn-primary">
            Start participation
          </Link>
        </Section>
      )}
    </div>
  );
}
