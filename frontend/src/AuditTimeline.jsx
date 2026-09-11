import "./auditTimeline.css";

// Audit timeline -- round 4, R3. Replaces AuditPage.jsx's raw JSON Lines
// <pre> dump with a real visual renderer. Oldest-first: mirrors how the hash
// chain itself is built (each event's prev_hash points at the one before
// it), the more defensible reading order for an append-only log.
//
// One readable summary per event type, the same "lookup table keyed by
// event_type, with a fallback for anything not listed" idea already solved
// by components.jsx's PROVENANCE_SUMMARY -- not a second convention.
//
// event_type list confirmed by grepping event_type= across
// services/orchestrator/satyapramana_store/ (round 4 rule 7), not guessed:
// DOCUMENT_INGESTED, FIELD_EXTRACTED, EXTRACTION_FAILED, ENTITY_RESOLVED,
// RULE_PACK_ADOPTED, BIDDER_REGISTERED, BIDDER_ATTRIBUTES,
// SHARED_ATTRIBUTE_OBSERVED, VERIFICATION_REQUESTED, VERIFICATION_OBSERVED,
// VERIFICATION_FAILED, EVIDENCE_FUSED, REQUIREMENT_EVALUATED,
// VERDICT_OVERRIDDEN, DECISION_RECORDED.
const EVENT_STYLE = {
  DOCUMENT_INGESTED: { glyph: "▤", tone: "accent" },
  FIELD_EXTRACTED: { glyph: "◆", tone: "accent" },
  EXTRACTION_FAILED: { glyph: "✕", tone: "fail" },
  ENTITY_RESOLVED: { glyph: "⇄", tone: "pass" },
  RULE_PACK_ADOPTED: { glyph: "▣", tone: "accent" },
  BIDDER_REGISTERED: { glyph: "◈", tone: "accent" },
  BIDDER_ATTRIBUTES: { glyph: "✎", tone: "unknown" },
  SHARED_ATTRIBUTE_OBSERVED: { glyph: "⚠", tone: "partial" },
  VERIFICATION_REQUESTED: { glyph: "…", tone: "unknown" },
  VERIFICATION_OBSERVED: { glyph: "✓", tone: "pass" },
  VERIFICATION_FAILED: { glyph: "✕", tone: "fail" },
  EVIDENCE_FUSED: { glyph: "⊕", tone: "accent" },
  REQUIREMENT_EVALUATED: { glyph: "☑", tone: "accent" },
  VERDICT_OVERRIDDEN: { glyph: "⚑", tone: "partial" },
  DECISION_RECORDED: { glyph: "◉", tone: "accent" },
};
const FALLBACK_STYLE = { glyph: "•", tone: "unknown" };

const SUMMARY = {
  DOCUMENT_INGESTED: (p) => `Document ingested: ${p.filename || p.storage_ref || "(unnamed)"}`,
  FIELD_EXTRACTED: (p) => `${p.path} = "${p.value}"`,
  EXTRACTION_FAILED: (p) => `${p.path || "document"}: ${p.detail || "extraction failed"}`,
  ENTITY_RESOLVED: (p) => `${p.path || "entity"} resolved${p.detail ? `: ${p.detail}` : ""}`,
  RULE_PACK_ADOPTED: (p) => `Rule pack ${p.rule_pack_version || p.rule_pack_id} adopted`,
  BIDDER_REGISTERED: (p) => `Bidder ${p.bidder_id} registered`,
  // The payload itself carries only hashed attribute values (never the raw
  // director name/address/phone/bank account -- see SHARED_ATTRIBUTE_OBSERVED
  // below for why), so which bidder is named comes from the event, not p.
  BIDDER_ATTRIBUTES: (p, event) => `Attributes recorded for ${event.bidder_id || "bidder"} (${Object.keys(p).length} field${Object.keys(p).length === 1 ? "" : "s"})`,
  SHARED_ATTRIBUTE_OBSERVED: (p) => `${p.bidder_a} and ${p.bidder_b} share ${p.attribute}`,
  VERIFICATION_REQUESTED: (p) => `Requested ${p.capability_id}`,
  VERIFICATION_OBSERVED: (p) => `${p.capability_id} observed`,
  VERIFICATION_FAILED: (p) => `${p.capability_id} failed: ${p.detail || p.reason_code || "unknown reason"}`,
  EVIDENCE_FUSED: (p) => `${p.path}: ${p.outcome}`,
  REQUIREMENT_EVALUATED: (p) => `${p.requirement_id}: ${p.verdict} (${p.reason_code})`,
  VERDICT_OVERRIDDEN: (p) => `${p.requirement_id} overridden to ${p.verdict_after} by ${p.officer_id}`,
  DECISION_RECORDED: (p) => `Decision ${p.decision} recorded by ${p.officer || p.officer_id}`,
};

// Never throws and blanks the whole timeline over one payload shape we
// didn't anticipate -- falls back to compact JSON instead, the same
// "something rather than nothing" rule PROVENANCE_SUMMARY already follows.
function summarize(event) {
  const fn = SUMMARY[event.event_type];
  if (fn) {
    try {
      return fn(event.payload || {}, event);
    } catch {
      // fall through to raw JSON below
    }
  }
  return JSON.stringify(event.payload || {});
}

// events: array of { event_type, occurred_at, payload, seq, ... } -- exactly
//   the shape GET /audit/export's JSON Lines already is, one object per
//   line, already parsed into objects by the caller.
// filterType: optional single event_type string to restrict the view to;
//   when omitted, shows everything.
export function AuditTimeline({ events, filterType }) {
  const rows = filterType ? events.filter((e) => e.event_type === filterType) : events;

  if (rows.length === 0) {
    return <p className="hint">No audit events{filterType ? ` of type ${filterType}` : ""} yet.</p>;
  }

  return (
    <ol className="audit-timeline">
      {rows.map((event) => {
        const style = EVENT_STYLE[event.event_type] || FALLBACK_STYLE;
        return (
          <li key={event.seq ?? `${event.event_type}-${event.occurred_at}`} className="audit-timeline-item">
            <span className={`audit-timeline-icon audit-timeline-tone-${style.tone}`} aria-hidden="true">
              {style.glyph}
            </span>
            <div className="audit-timeline-body">
              <div className="audit-timeline-header">
                <strong>{event.event_type}</strong>
                <span className="mono audit-timeline-meta">seq {event.seq} · {event.occurred_at}</span>
              </div>
              <div className="audit-timeline-summary">{summarize(event)}</div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
