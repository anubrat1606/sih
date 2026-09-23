import { useMemo, useState } from "react";
import { adoptRulePack, getRequirementTypes, validateRulePack } from "../api";
import { useApi } from "../lib/useApi";
import { useToast } from "../notifications";
import {
  Callout, Card, ErrorState, ReviewBadge, Section, Tag, UnavailableNote,
} from "../ui/primitives";

// Compliance requirements, authored by an officer against a real tender.
//
// Two rules this screen exists to enforce visually, not just technically:
//   1. A model may propose a requirement; only an officer adopts one. Every
//      AI-sourced row arrives flagged REVIEW REQUIRED and says so in words.
//   2. A requirement whose evidence nothing in this deployment can produce
//      is never quietly made adoptable. The catalog says which types have a
//      live evidence path; the rest stay flagged, and the server refuses
//      them (rule 8 + rule 11) rather than letting them pass.

// Mirrors services/orchestrator/satyapramana_store/declarations.py's
// declaration_field() byte-for-byte (the same "ported to JS, not
// reimplemented independently" convention lib/validation.js already uses
// for gstin_check_digit) -- field-path grammar only allows lowercase
// alphanumeric/underscore segments starting with a letter, incompatible
// with this project's own "R1"/"R4.1" requirement-id convention, so both
// sides sanitize identically rather than one guessing at the other's rule.
function declarationField(requirementId) {
  const slug = (requirementId || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return `bidder.declarations.req_${slug || "x"}`;
}

// Mirrors requirement_types.py's _SELF_DECLARED_TEMPLATE_TYPES -- every type
// whose one evidence field is the same per-requirement declaration template,
// so the builder auto-fills it the same way DECLARATION always has. Keep in
// sync with that constant whenever a self-declared type is added there.
const SELF_DECLARED_TEMPLATE_TYPES = new Set([
  "DECLARATION", "LOCAL_CONTENT", "STARTUP_NSIC_OEM_AUTH", "BLACKLISTING_DEBARMENT",
]);

const DEFAULT_CONSTANTS = {
  partial_credit: 0.5, w_mandatory: 1.0, w_desirable: 0.3,
  recency_floor: 0.5, corroboration_step: 0.1,
  coverage_floor_high: 50, coverage_floor_medium: 80, confidence_floor: 70,
};

const CONDITIONS = {
  exists: { label: "must be present", needsValue: false,
    build: (field) => ({ op: "exists", subject: { field } }) },
  eq: { label: "equals", needsValue: true, valueLabel: "Value",
    build: (field, v) => ({ op: "eq", left: { field }, right: literal(v) }) },
  gte: { label: "is at least (≥)", needsValue: true, valueLabel: "Value",
    build: (field, v) => ({ op: "gte", left: { field }, right: literal(v) }) },
  lte: { label: "is at most (≤)", needsValue: true, valueLabel: "Value",
    build: (field, v) => ({ op: "lte", left: { field }, right: literal(v) }) },
  gt: { label: "is greater than (>)", needsValue: true, valueLabel: "Value",
    build: (field, v) => ({ op: "gt", left: { field }, right: literal(v) }) },
  lt: { label: "is less than (<)", needsValue: true, valueLabel: "Value",
    build: (field, v) => ({ op: "lt", left: { field }, right: literal(v) }) },
  date_after: { label: "date is after", needsValue: true, valueLabel: "Date or $context_key",
    build: (field, v) => ({ op: "date_after", left: { field }, right: literal(v) }) },
  date_before: { label: "date is before", needsValue: true, valueLabel: "Date or $context_key",
    build: (field, v) => ({ op: "date_before", left: { field }, right: literal(v) }) },
  active_on: { label: "was active on", needsValue: true, valueLabel: "Date or $context_key",
    build: (field, v) => ({ op: "active_on", subject: { field }, at: literal(v) }) },
};

function literal(value) {
  if (typeof value === "string" && value.startsWith("$")) return { context: value.slice(1) };
  const n = Number(value);
  if (value !== "" && !Number.isNaN(n) && /^-?\d+(\.\d+)?$/.test(String(value).trim())) return { literal: n };
  return { literal: value };
}

let seq = 0;
function blankRequirement(seed = {}) {
  seq += 1;
  return {
    key: `r${seq}`,
    id: "", text: "", page: "", obligation: "mandatory",
    type: "", field: "", condition: "exists", value: "",
    unit: "", period: "", note: "",
    reviewRequired: false, source: "officer",
    ...seed,
  };
}

function requirementToJson(r) {
  const annotations = [];
  if (r.unit) annotations.push(`Unit: ${r.unit}.`);
  if (r.period) annotations.push(`Applicable period: ${r.period}.`);
  if (r.note) annotations.push(r.note);

  const out = {
    id: r.id,
    text: r.text,
    source: { page: Number(r.page) || 1 },
    obligation: r.obligation,
    operator: "LEAF",
    predicate: CONDITIONS[r.condition].build(r.field, r.value),
  };
  if (r.reviewRequired) out.review_required = true;
  if (annotations.length) out.review_note = annotations.join(" ");
  return out;
}

function RequirementRow({ index, req, types, onChange, onRemove }) {
  const type = types?.find((t) => t.id === req.type);
  const cond = CONDITIONS[req.condition];

  function applyType(typeId) {
    const t = types?.find((x) => x.id === typeId);
    if (!t) { onChange({ type: typeId }); return; }
    if (t.evidence_backed) {
      const op = t.suggested_ops.find((o) => o in CONDITIONS) || "exists";
      // A self-declared type's one field is a template naming this row's
      // own requirement id -- real from the moment the type is picked if
      // the id is already typed, computed live as the id changes below if not.
      const field = SELF_DECLARED_TEMPLATE_TYPES.has(typeId) ? declarationField(req.id) : (t.backed_fields[0] || "");
      onChange({ type: typeId, field, condition: op, reviewRequired: false, note: "" });
    } else {
      onChange({ type: typeId, reviewRequired: true, note: t.note });
    }
  }

  return (
    <div className={`requirement-card${req.reviewRequired ? " requirement-review-flag" : ""}`}>
      <div className="requirement-card-head">
        <span className="requirement-card-index">{String(index + 1).padStart(2, "0")}</span>
        <input
          className="mono" style={{ width: 130 }} value={req.id} required
          placeholder="R1" aria-label="Requirement ID"
          onChange={(e) => {
            const id = e.target.value;
            const patch = { id };
            // Keeps a self-declared type's field's requirement-id slug in
            // sync while the officer is still typing the id -- stops the
            // moment they've edited the field directly (a real edited
            // value is never overwritten), same one-way sync
            // requirement_types.py's own note tells them to expect.
            if (SELF_DECLARED_TEMPLATE_TYPES.has(req.type) && req.field === declarationField(req.id)) {
              patch.field = declarationField(id);
            }
            onChange(patch);
          }}
        />
        {type && <Tag accent={type.evidence_backed}>{type.label}</Tag>}
        {req.obligation === "mandatory"
          ? <Tag>MANDATORY</Tag>
          : <Tag>DESIRABLE</Tag>}
        {req.source === "ai" && <Tag>AI SUGGESTED</Tag>}
        <span className="spacer" />
        <ReviewBadge reviewRequired={req.reviewRequired} evidenceBacked={type ? type.evidence_backed : undefined} />
        <button type="button" className="btn btn-sm btn-ghost" onClick={onRemove} aria-label={`Remove requirement ${req.id || index + 1}`}>
          Remove
        </button>
      </div>

      <div className="requirement-card-body">
        <div className="field">
          <label htmlFor={`${req.key}-text`}>
            Requirement <span className="field-hint">quoted from the tender document, not paraphrased</span>
          </label>
          <input id={`${req.key}-text`} value={req.text} required
                 onChange={(e) => onChange({ text: e.target.value })} />
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor={`${req.key}-type`}>Type</label>
            <select id={`${req.key}-type`} value={req.type} onChange={(e) => applyType(e.target.value)}>
              <option value="">— select a requirement type —</option>
              {(types || []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}{t.evidence_backed ? "" : "  (no live evidence path)"}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${req.key}-obligation`}>Mandatory</label>
            <select id={`${req.key}-obligation`} value={req.obligation}
                    onChange={(e) => onChange({ obligation: e.target.value })}>
              <option value="mandatory">Mandatory</option>
              <option value="desirable">Desirable</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${req.key}-page`}>Source page</label>
            <input id={`${req.key}-page`} className="mono" type="number" min="1" value={req.page}
                   placeholder="14" onChange={(e) => onChange({ page: e.target.value })} />
          </div>
        </div>

        {type && !type.evidence_backed && (
          <UnavailableNote title="No live evidence path for this requirement type">
            {type.note} This requirement stays flagged for review and cannot be adopted until an
            evidence path exists — that is the correct outcome, not a defect.
          </UnavailableNote>
        )}

        <div className="form-row">
          <div className="field">
            <label htmlFor={`${req.key}-field`}>
              Evidence source <span className="field-hint">the path the rule reads</span>
            </label>
            <input id={`${req.key}-field`} className="mono" list={`${req.key}-fields`} value={req.field} required
                   placeholder="bidder.gst.status" onChange={(e) => onChange({ field: e.target.value })} />
            <datalist id={`${req.key}-fields`}>
              {(type?.candidate_fields || []).map((f) => <option key={f} value={f} />)}
            </datalist>
          </div>
          <div className="field">
            <label htmlFor={`${req.key}-cond`}>Condition</label>
            <select id={`${req.key}-cond`} value={req.condition}
                    onChange={(e) => onChange({ condition: e.target.value })}>
              {Object.entries(CONDITIONS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
          {cond.needsValue && (
            <div className="field">
              <label htmlFor={`${req.key}-value`}>{cond.valueLabel}</label>
              <input id={`${req.key}-value`} className="mono" value={req.value} required
                     onChange={(e) => onChange({ value: e.target.value })} />
            </div>
          )}
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor={`${req.key}-unit`}>Unit <span className="field-hint">optional</span></label>
            <input id={`${req.key}-unit`} value={req.unit} placeholder="INR lakh"
                   onChange={(e) => onChange({ unit: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor={`${req.key}-period`}>Applicable period <span className="field-hint">optional</span></label>
            <input id={`${req.key}-period`} value={req.period} placeholder="last 3 financial years"
                   onChange={(e) => onChange({ period: e.target.value })} />
          </div>
        </div>

        <div className="field">
          <label htmlFor={`${req.key}-note`}>Officer notes <span className="field-hint">recorded with the requirement</span></label>
          <input id={`${req.key}-note`} value={req.note} onChange={(e) => onChange({ note: e.target.value })} />
        </div>

        <label className="checkbox-field">
          <input type="checkbox" checked={req.reviewRequired}
                 onChange={(e) => onChange({ reviewRequired: e.target.checked })} />
          <span>
            <strong>Flag for review.</strong>{" "}
            <span className="text-secondary">
              A flagged requirement is refused at adoption until an officer clears it. Set automatically for
              AI-suggested rows and for types with no live evidence path.
            </span>
          </span>
        </label>
      </div>
    </div>
  );
}

export function RequirementBuilder({ tenderId, issuingAuthority, sourceDocumentSha256, suggestions, onAdopted }) {
  const { notify } = useToast();
  const catalog = useApi(() => getRequirementTypes(), []);
  const types = catalog.data?.requirement_types;

  const [rulePackId, setRulePackId] = useState("");
  const [semver, setSemver] = useState("1.0.0");
  const [docSha, setDocSha] = useState(sourceDocumentSha256 || "");
  const [authority, setAuthority] = useState(issuingAuthority || "");
  const [requirements, setRequirements] = useState([blankRequirement()]);
  const [rawMode, setRawMode] = useState(false);
  const [rawText, setRawText] = useState("");

  const [validation, setValidation] = useState(null);
  const [validating, setValidating] = useState(false);
  const [adopting, setAdopting] = useState(false);
  const [adopted, setAdopted] = useState(null);
  const [error, setError] = useState(null);

  // Keep the prefilled document hash in step with whatever the tender page
  // knows, without stomping an officer's own edit.
  const [seenSha, setSeenSha] = useState(sourceDocumentSha256);
  if (sourceDocumentSha256 !== seenSha) {
    setSeenSha(sourceDocumentSha256);
    if (!docSha && sourceDocumentSha256) setDocSha(sourceDocumentSha256);
  }

  const pack = useMemo(() => ({
    rule_pack_id: rulePackId,
    semver,
    tender_reference: {
      tender_id: tenderId,
      source_document_sha256: docSha,
      issuing_authority: authority,
    },
    constants: { ...DEFAULT_CONSTANTS, freshness_days: { GST_STATUS: 30, PAN_STATUS: 90, UDYAM_STATUS: 180 } },
    requirements: requirements.filter((r) => r.id && r.text).map(requirementToJson),
  }), [rulePackId, semver, tenderId, docSha, authority, requirements]);

  const flaggedCount = requirements.filter((r) => r.reviewRequired).length;

  function update(key, patch) {
    setRequirements((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  // A proposal becomes a *draft* row, flagged for review, with the model's
  // own note preserved. It is never adopted by this action, and the officer
  // still has to check it against the cited page before clearing the flag.
  function useSuggestion(p) {
    setRequirements((rs) => [...rs, blankRequirement({
      text: p.text || "",
      page: p.page || "",
      obligation: p.obligation_guess === "desirable" ? "desirable" : "mandatory",
      field: p.suggested_field || "",
      reviewRequired: true,
      source: "ai",
      note: `AI-suggested from the tender document — verify against page ${p.page} before clearing this flag.${p.note ? ` Model note: ${p.note}` : ""}`,
    })]);
    notify("Added as a draft requirement, flagged for review.", { kind: "info" });
  }

  function currentPack() {
    if (!rawMode) return pack;
    try { return JSON.parse(rawText); } catch { return null; }
  }

  async function onValidate() {
    const body = currentPack();
    if (!body) { setError(new Error("Rule pack must be valid JSON.")); return; }
    setValidating(true);
    setError(null);
    setValidation(null);
    try {
      const result = await validateRulePack(tenderId, body);
      setValidation(result);
      notify(result.valid ? "Valid — ready to adopt." : `${result.violations.length} violation(s) found.`,
        { kind: result.valid ? "success" : "error" });
    } catch (err) {
      setError(err);
    } finally {
      setValidating(false);
    }
  }

  async function onAdopt() {
    const body = currentPack();
    if (!body) { setError(new Error("Rule pack must be valid JSON.")); return; }
    setAdopting(true);
    setError(null);
    try {
      const result = await adoptRulePack(tenderId, body);
      setAdopted(result);
      notify(`Adopted ${result.rule_pack_version}.`, { kind: "success" });
      onAdopted?.(result);
    } catch (err) {
      if (err.detail?.violations) {
        setValidation({ valid: false, violations: err.detail.violations });
        notify(`Refused: ${err.detail.violations.length} violation(s).`, { kind: "error" });
      } else {
        setError(err);
        notify("Could not adopt the rule pack.", { kind: "error" });
      }
    } finally {
      setAdopting(false);
    }
  }

  return (
    <div>
      <Section
        title="Compliance Requirements"
        note="Each requirement is a rule the system will evaluate deterministically against a bidder's evidence. Adoption is a recorded human act — content-addressed, attributed, and permanent."
        actions={
          <>
            <button type="button" className="btn btn-sm btn-secondary" onClick={() => setRawMode((v) => !v)}>
              {rawMode ? "Guided editor" : "Advanced: raw JSON"}
            </button>
            {!rawMode && (
              <button type="button" className="btn btn-sm btn-secondary"
                      onClick={() => setRequirements((rs) => [...rs, blankRequirement()])}>
                + Add requirement
              </button>
            )}
          </>
        }
      >
        <ErrorState error={error} />
        <ErrorState error={catalog.error} onRetry={catalog.reload} />

        <Card title="Rule pack identity">
          <div className="form form-wide">
            <div className="form-row">
              <div className="field">
                <label htmlFor="rp-id">Rule pack ID <span className="field-hint">lowercase, dots — e.g. bhel.t7j1z68239.pumps</span></label>
                <input id="rp-id" className="mono" value={rulePackId} onChange={(e) => setRulePackId(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="rp-semver">Version</label>
                <input id="rp-semver" className="mono" value={semver} onChange={(e) => setSemver(e.target.value)} />
              </div>
            </div>
            <div className="form-row">
              <div className="field">
                <label htmlFor="rp-sha">Source document SHA-256 <span className="field-hint">the tender PDF this was decomposed from</span></label>
                <input id="rp-sha" className="mono" value={docSha} pattern="[0-9a-f]{64}"
                       onChange={(e) => setDocSha(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="rp-auth">Issuing authority</label>
                <input id="rp-auth" value={authority} onChange={(e) => setAuthority(e.target.value)} />
              </div>
            </div>
          </div>
        </Card>

        {suggestions && !rawMode && (
          <div style={{ marginTop: 16 }}>
            <SuggestionList result={suggestions} onUse={useSuggestion} />
          </div>
        )}

        {rawMode ? (
          <Card title="Rule pack JSON">
            <textarea rows={18} value={rawText} onChange={(e) => setRawText(e.target.value)}
                      aria-label="Rule pack JSON"
                      placeholder='{"rule_pack_id": "...", "semver": "1.0.0", "requirements": [...]}' />
          </Card>
        ) : (
          <div style={{ marginTop: 16 }}>
            {requirements.map((r, i) => (
              <RequirementRow
                key={r.key}
                index={i}
                req={r}
                types={types}
                onChange={(patch) => update(r.key, patch)}
                onRemove={() => setRequirements((rs) => rs.filter((x) => x.key !== r.key))}
              />
            ))}
            <button type="button" className="btn btn-secondary" style={{ marginTop: 12 }}
                    onClick={() => setRequirements((rs) => [...rs, blankRequirement()])}>
              + Add requirement
            </button>
          </div>
        )}

        {flaggedCount > 0 && (
          <div style={{ marginTop: 16 }}>
            <UnavailableNote title={`${flaggedCount} requirement(s) flagged for review`}>
              A flagged requirement cannot be part of an adopted pack. Either clear the flag once you have
              verified it against the source document, or leave it flagged and adopt the rest — the flagged
              ones stay on record as a known, stated gap rather than being silently dropped.
            </UnavailableNote>
          </div>
        )}

        <div className="row" style={{ marginTop: 20, gap: 8 }}>
          <button type="button" className="btn btn-secondary" onClick={onValidate} disabled={validating}>
            {validating ? "Validating…" : "Validate"}
          </button>
          <button type="button" className="btn btn-primary" onClick={onAdopt} disabled={adopting}>
            {adopting ? "Adopting…" : "Adopt rule pack"}
          </button>
          <span className="text-xs text-muted">
            Validation checks without committing anything. Adoption is permanent and attributed.
          </span>
        </div>

        {validation && (
          <div style={{ marginTop: 16 }}>
            {validation.valid ? (
              <Callout strong>
                Valid — <span className="mono">{validation.requirement_count}</span> requirement(s),
                content hash <span className="mono">{validation.content_hash?.slice(0, 16)}…</span>.
                Nothing has been adopted yet.
              </Callout>
            ) : (
              <Card title={`${validation.violations.length} validation finding(s)`}>
                <div className="stack-sm">
                  {validation.violations.map((v, i) => (
                    <div key={i} className="row" style={{ alignItems: "flex-start", gap: 10 }}>
                      <Tag>RULE {v.rule}</Tag>
                      <div className="text-sm">
                        {v.requirement_id && <span className="mono">{v.requirement_id}: </span>}
                        {v.message}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        )}

        {adopted && (
          <div style={{ marginTop: 16 }}>
            <Callout strong>
              Adopted <span className="mono">{adopted.rule_pack_version}</span> — recorded as event
              #{adopted.seq}. Earlier versions stay stored and citable; nothing was overwritten.
            </Callout>
          </div>
        )}

        {!rawMode && (
          <details style={{ marginTop: 16 }}>
            <summary className="text-sm text-secondary" style={{ cursor: "pointer" }}>
              Preview the exact JSON this will submit
            </summary>
            <pre className="mono" style={{
              background: "var(--color-surface)", border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)", padding: 16, overflow: "auto",
              maxHeight: 360, fontSize: 12, marginTop: 8,
            }}>{JSON.stringify(pack, null, 2)}</pre>
          </details>
        )}
      </Section>
    </div>
  );
}

// Tender Intelligence proposals, presented as what they are: candidates
// awaiting an officer. Nothing here can adopt anything.
export function SuggestionList({ result, onUse }) {
  if (!result) return null;
  if (!result.available) {
    return (
      <UnavailableNote title="Requirement suggestions unavailable">
        {result.reason} Requirements can still be entered by hand below — the workflow is unchanged,
        only slower.
      </UnavailableNote>
    );
  }
  if (!result.proposals.length) {
    return <Callout>No candidate requirements were proposed from this document.</Callout>;
  }
  return (
    <div>
      <Callout>
        {result.proposals.length} candidate(s) read from the document text by {result.model}.
        None of these is a decision — each becomes a draft requirement only when an officer adds it,
        and arrives flagged for review.
      </Callout>
      <div style={{ marginTop: 12 }}>
        {result.proposals.map((p, i) => (
          <div className="suggestion" key={i}>
            <div className="suggestion-head">
              <Tag>AI SUGGESTED — OFFICER REVIEW REQUIRED</Tag>
              <span className="text-xs text-muted mono">page {p.page}</span>
              {p.obligation_guess && <Tag>{p.obligation_guess}</Tag>}
            </div>
            <p className="suggestion-text">{p.text}</p>
            {(p.suggested_field || p.note) && (
              <p className="suggestion-meta">
                {p.suggested_field && <>Suggested evidence path <span className="mono">{p.suggested_field}</span>. </>}
                {p.note}
              </p>
            )}
            <button type="button" className="btn btn-sm btn-secondary" style={{ marginTop: 10 }}
                    onClick={() => onUse(p)}>
              Add as draft requirement
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
