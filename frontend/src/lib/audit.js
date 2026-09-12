// The audit log is the one place that knows everything that has happened:
// which documents were ingested, which rule packs were adopted, which
// verifications ran, which decisions were recorded. Several screens
// (Documents, Verification, Reports, a tender's rule-pack status) read it
// rather than asking for a purpose-built endpoint that doesn't exist.
//
// GET /audit/export is JSON Lines: the first line is chain metadata (no
// event_type), every line after it is a real event.

export function parseAuditExport(text) {
  if (!text) return [];
  return text
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => { try { return JSON.parse(l); } catch { return null; } })
    .filter((e) => e && e.event_type);
}

export function documentsFrom(events) {
  return events
    .filter((e) => e.event_type === "DOCUMENT_INGESTED")
    .map((e) => ({
      seq: e.seq,
      occurred_at: e.occurred_at,
      tender_id: e.tender_id,
      bidder_id: e.bidder_id,
      sha256: e.payload.document_sha256,
      filename: e.payload.filename,
      bytes: e.payload.bytes,
      declared_type: e.payload.declared_type,
      uploaded_by: e.payload.uploaded_by || null,
      actor: e.actor_id,
    }))
    .sort((a, b) => b.seq - a.seq);
}

// Latest adopted rule pack per tender, straight from RULE_PACK_ADOPTED.
// Returns { [tender_id]: { version, semver, content_hash, officer, at, requirement_count } }
export function rulePacksByTender(events) {
  const out = {};
  events
    .filter((e) => e.event_type === "RULE_PACK_ADOPTED")
    .sort((a, b) => a.seq - b.seq)
    .forEach((e) => {
      out[e.tender_id] = {
        version: e.payload.rule_pack_version,
        rule_pack_id: e.payload.rule_pack_id,
        semver: e.payload.semver,
        content_hash: e.payload.content_hash,
        officer: e.payload.officer_id,
        at: e.occurred_at,
        requirement_count: e.payload.requirement_count,
        seq: e.seq,
      };
    });
  return out;
}

export function verificationEventsFrom(events) {
  const kinds = new Set(["VERIFICATION_REQUESTED", "VERIFICATION_OBSERVED", "VERIFICATION_FAILED"]);
  return events.filter((e) => kinds.has(e.event_type)).sort((a, b) => b.seq - a.seq);
}

export function decisionsFrom(events) {
  return events
    .filter((e) => e.event_type === "DECISION_RECORDED" || e.event_type === "VERDICT_OVERRIDDEN")
    .sort((a, b) => b.seq - a.seq);
}

export function formatBytes(n) {
  if (n === null || n === undefined) return null;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatTimestamp(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export function formatDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

// One readable line per event type, instead of a raw JSON dump. Falls back
// to JSON for anything unrecognised — never hides a fact for lack of a
// formatter.
const SUMMARY = {
  TENDER_CREATED: (p) => `${p.title} — ${p.issuing_authority}${p.department ? ` (${p.department})` : ""}`,
  RULE_PACK_ADOPTED: (p) => `${p.rule_pack_version} · ${p.requirement_count} requirement(s), adopted by ${p.officer_id}`,
  DOCUMENT_INGESTED: (p) => `${p.filename} · ${formatBytes(p.bytes) || `${p.bytes} B`} · sha256 ${String(p.document_sha256).slice(0, 12)}…`,
  FIELD_EXTRACTED: (p) => `${p.path} = "${p.value}" (page ${p.page}${p.confidence != null ? `, confidence ${Math.round(p.confidence * 100)}%` : ""})`,
  EXTRACTION_FAILED: (p) => `${p.path || "document"}: ${p.detail}`,
  VERIFICATION_REQUESTED: (p) => `${p.capability_id} requested (${p.lawful_basis})`,
  VERIFICATION_OBSERVED: (p) => `${p.capability_id} observed at ${p.observed_at}`,
  VERIFICATION_FAILED: (p) => `${p.capability_id} → ${p.verdict} (${p.reason_code})${p.detail ? `: ${p.detail}` : ""}`,
  EVIDENCE_FUSED: (p) => `${p.path}: ${p.outcome}`,
  REQUIREMENT_EVALUATED: (p) => `${p.requirement_id || ""} → ${p.verdict} (${p.reason_code}) under ${p.rule_pack_version}`,
  VERDICT_OVERRIDDEN: (p) => `${p.requirement_id} → ${p.verdict_after}: ${p.justification}`,
  DECISION_RECORDED: (p) => `${p.decision}${p.note ? ` — ${p.note}` : ""}`,
  BIDDER_REGISTERED: (p) => `registered${p.shared_attribute_links?.length ? `, shares an attribute with ${p.shared_attribute_links.length} other bidder(s)` : ""}`,
};

export function summarizeEvent(event) {
  const fn = SUMMARY[event.event_type];
  try {
    return fn ? fn(event.payload) : JSON.stringify(event.payload);
  } catch {
    return JSON.stringify(event.payload);
  }
}
