import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getMyResult, getMyTenders } from "../bidderApi";
import { useApi } from "../../lib/useApi";
import { formatDate } from "../../lib/audit";
import {
  Card, Dash, EmptyState, ErrorState, LoadingBlock, PageHeader, Tag, VerdictBadge,
} from "../../ui/primitives";

// Round 6, R4.
const STATUS_LABEL = {
  NOT_REGISTERED: "Not registered",
  REGISTERED: "Registered",
  DOCUMENTS_RECEIVED: "Documents received",
  UNDER_EVALUATION: "Under evaluation",
  DECIDED: "Decided",
};

// One composite load: the bidder's tenders they're actually on (a tender
// merely open for discovery isn't "one they're on" -- GET /me/tenders
// returns both, flagged by `registered`), then -- only for DECIDED ones --
// each tender's real result, so this page never shows a decision it hasn't
// actually fetched.
async function loadResults() {
  const { tenders: all } = await getMyTenders();
  const tenders = all.filter((t) => t.registered);
  const decided = tenders.filter((t) => t.status === "DECIDED");
  const results = await Promise.all(decided.map((t) => getMyResult(t.tender_id).catch(() => null)));
  const resultsByTender = {};
  decided.forEach((t, i) => { resultsByTender[t.tender_id] = results[i]; });
  return { tenders, resultsByTender };
}

// Never "awarded," "won," or anything implying a contract — this system
// records compliance decisions, not procurement outcomes.
function decisionSentence(tenderLabel, decision, decidedAt) {
  const when = formatDate(decidedAt) || decidedAt;
  if (decision === "QUALIFY") {
    return `Your submission for ${tenderLabel} was assessed as compliant by the procurement office on ${when}.`;
  }
  return `The procurement office recorded a final decision on your submission for ${tenderLabel} on ${when}.`;
}

// Expands inline rather than routing to a per-tender page, so this stays a
// single self-contained file with no new route dependency. `?tender=<id>`
// (used by DashboardPage's "Recent results" links) auto-opens that row.
function ResultRow({ tender, result, defaultOpen }) {
  const [open, setOpen] = useState(Boolean(defaultOpen));
  const label = tender.title || tender.tender_id;

  return (
    <Card>
      <button
        type="button"
        className="btn btn-ghost"
        style={{ width: "100%", justifyContent: "space-between", display: "flex" }}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="row" style={{ gap: 10 }}>
          <span className="mono" style={{ fontWeight: 600 }}>{tender.tender_id}</span>
          <span className="text-sm text-secondary">{tender.title || <Dash />}</span>
        </span>
        <Tag accent={tender.status === "DECIDED"}>{STATUS_LABEL[tender.status] || tender.status}</Tag>
      </button>

      {open && (
        tender.status !== "DECIDED" || !result?.published ? (
          <p className="text-sm text-secondary" style={{ marginTop: 12 }}>
            The procurement office has not yet recorded a decision.
          </p>
        ) : (
          <div style={{ marginTop: 12 }}>
            <p>{decisionSentence(label, result.decision, result.decided_at)}</p>
            {result.note && (
              <p className="text-sm text-secondary" style={{ marginTop: 4 }}>
                Officer's note: {result.note}
              </p>
            )}

            {result.outcomes?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="field-label" style={{ marginBottom: 8 }}>Per-requirement outcome</div>
                <div className="table-frame">
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead><tr><th>Requirement</th><th>Outcome</th></tr></thead>
                      <tbody>
                        {result.outcomes.map((o) => (
                          <tr key={o.requirement_id}>
                            <td className="mono">{o.requirement_id}</td>
                            <td><VerdictBadge verdict={o.verdict} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {result.repair_actions?.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="field-label" style={{ marginBottom: 8 }}>What would resolve this</div>
                <div className="stack-sm">
                  {result.repair_actions.map((a, i) => (
                    <p key={a.requirement_id || i} className="text-sm">{a.action || JSON.stringify(a)}</p>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      )}
    </Card>
  );
}

export default function ResultsPage() {
  const { data, error, loading, reload } = useApi(loadResults, []);
  const [params] = useSearchParams();
  const focusTender = params.get("tender");

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bidder portal"
        title="My results"
        subtitle="Only the procurement office's recorded decision is a result — nothing here is evaluative before that."
      />
      <ErrorState error={error} onRetry={reload} />

      {loading ? <LoadingBlock lines={4} /> : !data?.tenders?.length ? (
        <EmptyState glyph="◌" title="No tenders yet"
                    message="You haven't been registered on a tender yet. Ask the procuring office." />
      ) : (
        <div className="stack-sm">
          {data.tenders.map((t) => (
            <ResultRow key={t.tender_id} tender={t} result={data.resultsByTender[t.tender_id]}
                       defaultOpen={t.tender_id === focusTender} />
          ))}
        </div>
      )}
    </div>
  );
}
