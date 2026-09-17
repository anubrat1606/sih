import { useState } from "react";
import { getBidderAsOf, getBidderTimeline } from "../api";
import { useApi } from "../lib/useApi";
import { formatTimestamp } from "../lib/audit";
import {
  Callout, CoverageMetric, Dash, EmptyState, ErrorState, LoadingBlock,
  MetricCard, RiskBadge, Tag, VerdictBadge,
} from "../ui/primitives";

// Round 8, Rishika -- the Temporal Scrubber's frontend. Every checkpoint
// below is a real event sequence number from this bidder's own history
// (Anubrat's GET /bidders/{id}/timeline) -- never an evenly-spaced fake
// slider; however sparse or clustered the real history is, is what's shown.
// Selecting one calls GET /bidders/{id}/as-of/{seq}, which folds the event
// log only up to that point through the same metrics/risk computation the
// live Compliance tab uses -- this renders that response, it never
// recomputes anything itself.
const EVENT_LABEL = {
  FIELD_EXTRACTED: "Field extracted",
  EXTRACTION_FAILED: "Extraction failed",
  VERIFICATION_OBSERVED: "Verification observed",
  VERIFICATION_FAILED: "Verification failed",
  REQUIREMENT_EVALUATED: "Evaluated",
  VERDICT_OVERRIDDEN: "Verdict overridden",
  DECISION_RECORDED: "Decision recorded",
};

// `currentVerdicts` is the live Compliance tab's own `b.verdicts` -- passed
// down rather than re-fetched, so "what changed since this point" compares
// against the exact same live data the rest of the page shows, never a
// second, possibly-stale copy of it.
export default function BidderHistoryTimeline({ bidderId, tenderId, currentVerdicts }) {
  const timeline = useApi(() => getBidderTimeline(bidderId, tenderId), [bidderId, tenderId]);
  const [selectedSeq, setSelectedSeq] = useState(null);
  const checkpoints = timeline.data?.checkpoints || [];

  // Defaults to the most recent real checkpoint once the timeline loads --
  // derived during render rather than synced via an effect, so there's
  // nothing to select before data exists and no separate re-render just to
  // apply the default. `selectedSeq` itself only ever changes from a click.
  const effectiveSeq = selectedSeq ?? (checkpoints.length ? checkpoints[checkpoints.length - 1].seq : null);

  const asOf = useApi(
    () => getBidderAsOf(bidderId, tenderId, effectiveSeq),
    [bidderId, tenderId, effectiveSeq],
    { skip: effectiveSeq === null }
  );

  if (timeline.loading) return <LoadingBlock lines={3} />;
  if (timeline.error) return <ErrorState error={timeline.error} onRetry={timeline.reload} />;
  if (!checkpoints.length) {
    return (
      <EmptyState glyph="◌" title="No history yet"
                  message="A checkpoint appears here the first time this bidder's documents are extracted, verified, or evaluated." />
    );
  }

  const currentByReq = Object.fromEntries((currentVerdicts || []).map((v) => [v.requirement_id, v]));
  const snapshot = asOf.data;

  return (
    <div>
      <Callout>
        Every point below is a real event from this bidder's own history — nothing is evenly spaced or
        invented. Selecting one shows the compliance picture exactly as it stood at that moment.
      </Callout>

      <div className="table-frame" style={{ marginTop: 16, padding: 12, overflowX: "auto" }}>
        <div className="row" style={{ gap: 8, minWidth: "max-content" }}>
          {checkpoints.map((c) => (
            <button
              key={c.seq}
              type="button"
              className={`btn btn-sm ${c.seq === effectiveSeq ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setSelectedSeq(c.seq)}
              aria-current={c.seq === effectiveSeq ? "step" : undefined}
            >
              <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
                <span className="mono text-xs">#{c.seq}</span>
                <span className="text-xs" style={{ fontWeight: 600 }}>{EVENT_LABEL[c.event_type] || c.event_type}</span>
                <span className="mono text-xs" style={{ opacity: 0.85 }}>{formatTimestamp(c.occurred_at)}</span>
              </span>
            </button>
          ))}
        </div>
      </div>

      {asOf.loading ? (
        <div style={{ marginTop: 20 }}><LoadingBlock lines={3} /></div>
      ) : asOf.error ? (
        <div style={{ marginTop: 20 }}><ErrorState error={asOf.error} onRetry={asOf.reload} /></div>
      ) : snapshot && (
        <div style={{ marginTop: 20 }}>
          <div className="metric-triad">
            <MetricCard label="Compliance score" value={snapshot.metrics.compliance_score}
                        note={`as of event #${snapshot.as_of_seq}`} />
            <MetricCard label="Evidence confidence" value={snapshot.metrics.evidence_confidence}
                        note={`as of event #${snapshot.as_of_seq}`} />
            <CoverageMetric label="Verification coverage" value={snapshot.metrics.verification_coverage}
                            note={`as of event #${snapshot.as_of_seq}`} />
          </div>

          <div className="row" style={{ gap: 10, marginTop: 12, alignItems: "center", flexWrap: "wrap" }}>
            <RiskBadge level={snapshot.risk.level} />
            <span className="text-xs text-muted">{snapshot.collusion_note}</span>
          </div>

          {!snapshot.verdicts.length ? (
            <div style={{ marginTop: 16 }}>
              <EmptyState glyph="◌" title="Nothing evaluated as of this point"
                          message="No requirement had been evaluated for this bidder yet at this checkpoint." />
            </div>
          ) : (
            <div className="table-frame" style={{ marginTop: 16 }}>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr><th>Requirement</th><th>Verdict at this point</th><th>Now</th></tr>
                  </thead>
                  <tbody>
                    {snapshot.verdicts.map((v) => {
                      const now = currentByReq[v.requirement_id];
                      const changed = now && now.verdict_effective !== v.verdict_effective;
                      return (
                        <tr key={v.requirement_id}>
                          <td className="mono cell-primary">{v.requirement_id}</td>
                          <td>
                            <VerdictBadge verdict={v.verdict_effective} />
                            <div className="text-xs text-muted" style={{ marginTop: 2 }}>{v.reason_effective}</div>
                            {v.overridden_by && (
                              <div className="text-xs" style={{ color: "var(--status-partial-fg)", marginTop: 2 }}>
                                overridden by {v.overridden_by}
                              </div>
                            )}
                          </td>
                          <td>
                            {!now ? <Dash /> : changed ? (
                              <span className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                                <VerdictBadge verdict={now.verdict_effective} />
                                <Tag accent>CHANGED SINCE THIS POINT</Tag>
                              </span>
                            ) : (
                              <span className="text-xs text-muted">unchanged</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
