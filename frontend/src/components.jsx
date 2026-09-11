// Shared components, built on the token set in tokens.css (satyapramana.md
// section 2.3). Every badge here carries colour + glyph + text label --
// colour is never the only carrier of meaning, so an officer with
// deuteranopia reads the identical verdict a sighted colleague does.

import PdfEvidenceViewer from "./PdfEvidenceViewer";

const VERDICT_CLASS = { PASS: "v-pass", FAIL: "v-fail", PARTIAL: "v-partial", UNKNOWN: "v-unknown" };
const VERDICT_GLYPH = { PASS: "✓", FAIL: "✕", PARTIAL: "◑", UNKNOWN: "?" };

export function VerdictBadge({ verdict }) {
  return (
    <span className={`badge ${VERDICT_CLASS[verdict] || "v-unknown"}`}>
      <span aria-hidden="true">{VERDICT_GLYPH[verdict] || VERDICT_GLYPH.UNKNOWN}</span>
      {verdict}
    </span>
  );
}

const RISK_CLASS = { LOW: "r-low", MEDIUM: "r-medium", HIGH: "r-high" };
const RISK_GLYPH = { LOW: "○", MEDIUM: "◑", HIGH: "●" };

export function RiskBadge({ level }) {
  return (
    <span className={`badge ${RISK_CLASS[level] || "r-medium"}`}>
      <span aria-hidden="true">{RISK_GLYPH[level] || RISK_GLYPH.MEDIUM}</span>
      {level} RISK
    </span>
  );
}

// Bid Autopsy: FATAL is positive evidence against the bidder (re-checking the
// same fact won't change it); CURABLE is an absence of evidence or a
// procedural gap (new evidence could flip it). Reuses the verdict palette --
// FATAL reads the same as a FAIL, CURABLE the same as a PARTIAL -- rather
// than inventing a second colour vocabulary for the same underlying idea.
export function ClassificationBadge({ classification }) {
  const cls = classification === "FATAL" ? "v-fail" : classification === "CURABLE" ? "v-partial" : "v-unknown";
  const glyph = classification === "FATAL" ? "✕" : classification === "CURABLE" ? "◑" : "?";
  return <span className={`badge ${cls}`}><span aria-hidden="true">{glyph}</span>{classification}</span>;
}

// Compliance Repair: who can actually act on this gap. SYSTEM means "we
// haven't configured this yet" -- never told to a bidder as their problem.
export function ActionableBadge({ actionableBy }) {
  const glyph = actionableBy === "BIDDER" ? "✓" : "⚙";
  return <span className={`badge ${actionableBy === "BIDDER" ? "v-pass" : "v-unknown"}`}><span aria-hidden="true">{glyph}</span>{actionableBy}</span>;
}

// A metric is null, never zero, when nothing could be determined -- an em
// dash says that plainly instead of looking like a real 0%. Values already
// arrive on a 0-100 scale (services/core/satyapramana/metrics.py) -- this
// never re-scales them, only rounds for display.
export function Metric({ label, value }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value === null || value === undefined ? "—" : `${Math.round(value)}%`}</div>
    </div>
  );
}

// One readable line per event type in a provenance trail, instead of a raw
// JSON dump. Falls back to JSON for any event type not listed here, so an
// unrecognised or future event type still renders something rather than
// nothing -- never hides a fact for lack of a formatter.
const PROVENANCE_SUMMARY = {
  REQUIREMENT_EVALUATED: (p) => `Verdict ${p.verdict} (${p.reason_code}) under rule pack ${p.rule_pack_version}`,
  EVIDENCE_FUSED: (p) => `${p.path}: ${p.outcome}`,
  VERIFICATION_REQUESTED: (p) => `Requested ${p.capability_id} (${p.lawful_basis}, by ${p.requested_by})`,
  VERIFICATION_OBSERVED: (p) => `${p.capability_id} observed at ${p.observed_at}${p.source_asserted_at ? ` (authority asserts as of ${p.source_asserted_at})` : ""}`,
  VERIFICATION_FAILED: (p) => `${p.capability_id} -> ${p.verdict} (${p.reason_code}): ${p.detail}`,
  FIELD_EXTRACTED: (p) => `${p.path} = "${p.value}" (page ${p.page}, confidence ${Math.round(p.confidence * 100)}%)`,
  EXTRACTION_FAILED: (p) => `${p.path || "document"}: ${p.detail}`,
  DOCUMENT_INGESTED: (p) => `${p.filename} (${p.bytes} bytes, sha256 ${p.document_sha256?.slice(0, 12)}…)`,
};

export function ProvenanceStep({ step }) {
  const summarize = PROVENANCE_SUMMARY[step.event_type];
  return (
    <li>
      <strong>{step.event_type}</strong> (seq {step.seq}, {step.occurred_at}) — {summarize ? summarize(step.payload) : JSON.stringify(step.payload)}
    </li>
  );
}

// The demo axiom's walkable path, as one component: a provenance trail's
// steps, and -- when the trail reaches both an extracted field (page +
// region) and the document it came from (its content hash) -- the exact
// highlighted line of the source PDF beside it. A verification-sourced fact
// never reaches a document, and that's correct, not a bug: only an
// extraction-sourced fact has a page to highlight.
export function ProvenancePanel({ trail }) {
  const extracted = trail.find((t) => t.event_type === "FIELD_EXTRACTED");
  const document = trail.find((t) => t.event_type === "DOCUMENT_INGESTED");
  return (
    <div>
      <ol className="audit-list">
        {trail.map((t) => <ProvenanceStep key={t.seq} step={t} />)}
      </ol>
      {extracted && document && (
        <PdfEvidenceViewer
          documentSha256={document.payload.document_sha256}
          page={extracted.payload.page}
          region={extracted.payload.region}
        />
      )}
    </div>
  );
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return <p className="error">{String(error.message || error)}</p>;
}

// <CoverageMeter> -- satyapramana.md 2.3: "renders verification coverage
// honestly, including the unverified remainder. Visually incapable of
// showing 100% when coverage is partial." The uncovered remainder is a
// diagonal-hatched fill (App.css), never blank space -- blank space reads
// as "nothing here, all is well," which is exactly the wrong message for
// an unverified gap.
export function CoverageMeter({ label, value }) {
  if (value === null || value === undefined) {
    return (
      <div className="coverage-meter">
        <div className="metric-label">{label}</div>
        <div className="coverage-track"><div className="coverage-unresolved-label">not determined</div></div>
      </div>
    );
  }
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="coverage-meter">
      <div className="metric-label">{label}</div>
      <div className="coverage-track">
        <div className="coverage-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="coverage-value mono">
        {pct}% verified{pct < 100 ? `, ${100 - pct}% unverified` : ""}
      </div>
    </div>
  );
}

// <ConflictCard> -- bidder claim vs authority response, side by side, the
// delta unmissable. Renders nothing when either side is missing: a
// one-sided "conflict" would be a fabricated comparison, not a real one.
export function ConflictCard({ field, claim, authority }) {
  if (claim === null || claim === undefined || authority === null || authority === undefined) return null;
  const agrees = String(claim).trim().toUpperCase() === String(authority).trim().toUpperCase();
  return (
    <div className={`conflict-card ${agrees ? "conflict-agree" : "conflict-disagree"}`}>
      <div className="conflict-field">{field}</div>
      <div className="conflict-row">
        <div className="conflict-side">
          <div className="metric-label">Bidder claims</div>
          <div className="mono">{claim}</div>
        </div>
        <div className="conflict-delta" aria-hidden="true">{agrees ? "=" : "≠"}</div>
        <div className="conflict-side">
          <div className="metric-label">Authority says</div>
          <div className="mono">{authority}</div>
        </div>
      </div>
      {!agrees && <div className="conflict-flag">Bidder's claim does not match the authority's record.</div>}
    </div>
  );
}

// <RepairAction> -- "a corrective action written as a specific, executable
// instruction." One card per action, never a bare table row -- the point is
// that it reads as an instruction someone could act on today.
export function RepairAction({ action }) {
  return (
    <div className={`repair-action repair-${action.actionable_by === "BIDDER" ? "bidder" : "system"}`}>
      <div className="repair-header">
        <span className="mono">{action.requirement_id}</span>
        <ActionableBadge actionableBy={action.actionable_by} />
      </div>
      <div className="repair-text">{action.action}</div>
      {action.authority && <div className="hint">Authority: {action.authority}</div>}
    </div>
  );
}

// <EvidenceChip> -- "any rendered fact is a chip. Clicking reveals its
// source." This component only renders the chip and forwards the click --
// the page wires onReveal to whatever "show the source" means in context
// (open a ProvenanceTrail, scroll to a PdfEvidenceViewer), since only the
// page knows what evidence backs a given value.
export function EvidenceChip({ value, onReveal, open }) {
  return (
    <button type="button" className={`evidence-chip ${open ? "evidence-chip-open" : ""}`}
            onClick={onReveal} title="Click to see the source">
      <span className="mono">{value}</span>
      <span aria-hidden="true" className="evidence-chip-icon">⌕</span>
    </button>
  );
}
