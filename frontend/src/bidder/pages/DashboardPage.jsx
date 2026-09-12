import { Link } from "react-router-dom";
import { getMyResult, getMyTenders } from "../bidderApi";
import { useApi } from "../../lib/useApi";
import { formatDate } from "../../lib/audit";
import { DataTable } from "../../ui/DataTable";
import {
  Card, Dash, EmptyState, ErrorState, LoadingBlock, PageHeader, Section, Stat, Tag,
} from "../../ui/primitives";

// Round 6, R1. A pure, local formatter -- kept in this file rather than a
// shared lib because this round's file ownership keeps every bidder page
// self-contained in its own owner's files (docs/NEXT_TASKS_6...). Computed
// from the tender's own real deadline only; never estimated when absent.
function timeRemaining(deadlineIso) {
  if (!deadlineIso) return null;
  const deadline = new Date(deadlineIso);
  if (Number.isNaN(deadline.getTime())) return null;
  const ms = deadline.getTime() - Date.now();
  if (ms <= 0) return "closed";
  const days = Math.floor(ms / 86400000);
  if (days >= 1) return `${days} day${days === 1 ? "" : "s"} left`;
  const hours = Math.max(1, Math.floor(ms / 3600000));
  return `${hours} hour${hours === 1 ? "" : "s"} left`;
}

const STATUS_LABEL = {
  NOT_REGISTERED: "Not registered",
  REGISTERED: "Registered",
  DOCUMENTS_RECEIVED: "Documents received",
  UNDER_EVALUATION: "Under evaluation",
  DECIDED: "Decided",
};
const AWAITING = new Set(["DOCUMENTS_RECEIVED", "UNDER_EVALUATION"]);

function byDeadlineAsc(a, b) {
  if (!a.bid_submission_deadline) return 1;
  if (!b.bid_submission_deadline) return -1;
  return new Date(a.bid_submission_deadline) - new Date(b.bid_submission_deadline);
}

// One composite fetch: GET /me/tenders, then -- only for tenders already
// DECIDED -- GET /me/tenders/{id}/result, so "Recent results" is genuinely
// ordered by decided_at rather than guessed. Bounded by how many tenders
// this one bidder is on, not a tender-wide scan.
async function loadDashboard() {
  const { tenders } = await getMyTenders();
  const decided = tenders.filter((t) => t.status === "DECIDED");
  const results = await Promise.all(decided.map((t) => getMyResult(t.tender_id).catch(() => null)));
  const recentResults = decided
    .map((t, i) => ({ tender: t, result: results[i] }))
    .filter((r) => r.result?.published)
    .sort((a, b) => new Date(b.result.decided_at) - new Date(a.result.decided_at))
    .slice(0, 3);
  return { tenders, recentResults };
}

export default function DashboardPage() {
  const { data, error, loading, reload } = useApi(loadDashboard, []);
  const tenders = data?.tenders || [];

  const openToYou = tenders.filter((t) => !t.registered).length;
  const onTender = tenders.filter((t) => t.registered).length;
  const awaitingDecision = tenders.filter((t) => AWAITING.has(t.status)).length;
  const decided = tenders.filter((t) => t.status === "DECIDED").length;

  const actionNeeded = tenders.filter((t) => t.status === "REGISTERED").sort(byDeadlineAsc);
  const closingSoon = [...tenders].sort(byDeadlineAsc);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bidder portal"
        title="Dashboard"
        subtitle="Everything real about your tenders, submissions and decisions — nothing here is estimated."
      />

      <ErrorState error={error} onRetry={reload} />

      {loading ? <LoadingBlock lines={3} /> : (
        <>
          <div className="stat-row" style={{ marginBottom: 24 }}>
            <Stat label="Tenders open to you" value={openToYou} note="Published, not yet registered" />
            <Stat label="Tenders you're on" value={onTender} accent="pass" />
            <Stat label="Awaiting a decision" value={awaitingDecision} accent="partial" />
            <Stat label="Decisions received" value={decided} />
          </div>

          <Section title="Action needed" note="Tenders you're registered on with no documents submitted yet.">
            {actionNeeded.length === 0 ? (
              <EmptyState glyph="✓" title="Nothing needs your attention" />
            ) : (
              <div className="stack-sm">
                {actionNeeded.map((t) => (
                  <Card key={t.tender_id}>
                    <div className="row-wrap" style={{ justifyContent: "space-between" }}>
                      <div>
                        <Link className="mono" style={{ fontWeight: 600 }}
                              to={`/portal/tenders/${encodeURIComponent(t.tender_id)}`}>
                          {t.tender_id}
                        </Link>
                        <div className="text-sm text-secondary">{t.title || <Dash />}</div>
                      </div>
                      <div className="row" style={{ gap: 12 }}>
                        <span className="text-sm text-secondary">
                          {t.bid_submission_deadline ? (
                            <>Deadline <span className="mono">{formatDate(t.bid_submission_deadline)}</span>
                              {" · "}{timeRemaining(t.bid_submission_deadline) || "—"}</>
                          ) : "No deadline on file"}
                        </span>
                        <Link className="btn btn-sm btn-primary"
                              to={`/portal/tenders/${encodeURIComponent(t.tender_id)}/submit`}>
                          Submit documents
                        </Link>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </Section>

          <Section title="Closing soon" note="Every tender you can see, by submission deadline.">
            <DataTable
              rows={closingSoon}
              getRowKey={(t) => t.tender_id}
              emptyTitle="No tenders yet"
              columns={[
                { key: "id", header: "Tender", sortValue: (t) => t.tender_id, searchValue: (t) => t.tender_id,
                  render: (t) => <Link className="mono" to={`/portal/tenders/${encodeURIComponent(t.tender_id)}`}>{t.tender_id}</Link> },
                { key: "title", header: "Title", sortValue: (t) => t.title, searchValue: (t) => t.title,
                  render: (t) => t.title || <Dash /> },
                { key: "deadline", header: "Deadline", sortValue: (t) => t.bid_submission_deadline,
                  render: (t) => t.bid_submission_deadline
                    ? <span className="mono">{formatDate(t.bid_submission_deadline)}</span> : <Dash /> },
                { key: "remaining", header: "Time remaining",
                  render: (t) => t.bid_submission_deadline
                    ? <span className="mono text-sm">{timeRemaining(t.bid_submission_deadline) || "—"}</span>
                    : <Dash /> },
                { key: "status", header: "Your status", sortValue: (t) => t.status,
                  render: (t) => t.registered
                    ? <Tag accent={t.status === "DECIDED"}>{STATUS_LABEL[t.status] || t.status}</Tag>
                    : <span className="text-muted text-sm">not registered</span> },
              ]}
            />
          </Section>

          <Section title="Recent results" note="Your most recent officer decisions.">
            {data.recentResults.length === 0 ? (
              <EmptyState glyph="◌" title="No decisions yet" />
            ) : (
              <div className="stack-sm">
                {data.recentResults.map(({ tender }) => (
                  <Card key={tender.tender_id}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <div>
                        <span className="mono" style={{ fontWeight: 600 }}>{tender.tender_id}</span>
                        <div className="text-sm text-secondary">{tender.title || <Dash />}</div>
                      </div>
                      <Link className="btn btn-sm btn-secondary"
                            to={`/portal/results?tender=${encodeURIComponent(tender.tender_id)}`}>
                        View
                      </Link>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </Section>
        </>
      )}
    </div>
  );
}
