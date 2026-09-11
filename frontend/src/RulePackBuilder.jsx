import { useMemo, useState } from "react";

// Roadmap A2. The rule pack schema (schemas/rule_pack.schema.json) is
// genuinely rich -- seven predicate shapes, four operand kinds, K_OF_N,
// NOT, aggregates with recency windows. A guided form covering all of it
// would be a schema editor, not a tool an officer would actually use for
// the common case. This covers the shapes that show up in practice
// (equals, exists, before/after a date) with a live JSON preview so
// nothing is hidden, plus an "Advanced: raw JSON" escape hatch for
// anything it doesn't have a form for yet -- so this is strictly additive
// capability over the old textarea, never a regression.

const DEFAULT_CONSTANTS = {
  partial_credit: 0.5, w_mandatory: 1.0, w_desirable: 0.3,
  recency_floor: 0.5, corroboration_step: 0.1,
  coverage_floor_high: 50, coverage_floor_medium: 80, confidence_floor: 70,
};

const COMMON_FIELDS = [
  "bidder.gst.status", "bidder.gst.date_of_expiry", "bidder.gst.legal_name",
  "bidder.pan.status", "bidder.pan.holder_name",
  "bidder.entity.cin", "bidder.entity.status",
  "bidder.udyam.status",
];

const PREDICATE_KINDS = {
  exists: { label: "Field must be present", needsValue: false,
    build: (field) => ({ op: "exists", subject: { field } }) },
  eq: { label: "Field equals a value", needsValue: true, valueLabel: "Value",
    build: (field, value) => ({ op: "eq", left: { field }, right: literalOrContext(value) }) },
  date_after: { label: "Field date must be after…", needsValue: true, valueLabel: "Date, or $context_key",
    build: (field, value) => ({ op: "date_after", left: { field }, right: literalOrContext(value) }) },
  date_before: { label: "Field date must be before…", needsValue: true, valueLabel: "Date, or $context_key",
    build: (field, value) => ({ op: "date_before", left: { field }, right: literalOrContext(value) }) },
};

function literalOrContext(value) {
  return value.startsWith("$") ? { context: value.slice(1) } : { literal: value };
}

function newRequirement() {
  return {
    key: Math.random().toString(36).slice(2),
    id: "", text: "", page: 1, region: [72, 470, 523, 494],
    obligation: "mandatory", operator: "LEAF",
    field: "", predicateKind: "exists", value: "",
    children: [],
  };
}

function requirementToJson(r) {
  const base = { id: r.id, text: r.text, source: { page: Number(r.page) || 1, region: r.region.map(Number) },
    obligation: r.obligation, operator: r.operator };
  if (r.operator === "LEAF") {
    const kind = PREDICATE_KINDS[r.predicateKind];
    return { ...base, predicate: kind.build(r.field, r.value) };
  }
  return { ...base, children: r.children };
}

export default function RulePackBuilder({ tenderId, onAdopt, submitting }) {
  const [mode, setMode] = useState("guided"); // "guided" | "raw"
  const [rulePackId, setRulePackId] = useState("");
  const [semver, setSemver] = useState("1.0.0");
  const [sourceDocSha, setSourceDocSha] = useState("");
  const [issuingAuthority, setIssuingAuthority] = useState("");
  const [constants, setConstants] = useState(DEFAULT_CONSTANTS);
  const [freshnessDays, setFreshnessDays] = useState({ GST_STATUS: 30, PAN_STATUS: 90 });
  const [requirements, setRequirements] = useState([newRequirement()]);
  const [rawText, setRawText] = useState("");

  const pack = useMemo(() => {
    try {
      return {
        rule_pack_id: rulePackId, semver,
        tender_reference: { tender_id: tenderId, source_document_sha256: sourceDocSha, issuing_authority: issuingAuthority },
        constants: { ...constants, freshness_days: freshnessDays },
        requirements: requirements.filter((r) => r.id).map(requirementToJson),
      };
    } catch {
      return null;
    }
  }, [rulePackId, semver, tenderId, sourceDocSha, issuingAuthority, constants, freshnessDays, requirements]);

  function updateReq(key, patch) {
    setRequirements((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }
  function addRequirement() {
    setRequirements((rs) => [...rs, newRequirement()]);
  }
  function removeRequirement(key) {
    setRequirements((rs) => rs.filter((r) => r.key !== key));
  }

  function onSubmit(e) {
    e.preventDefault();
    if (mode === "raw") {
      let parsed;
      try {
        parsed = JSON.parse(rawText);
      } catch {
        onAdopt(null, new Error("rule pack must be valid JSON -- see schemas/rule_pack.schema.json"));
        return;
      }
      onAdopt(parsed);
    } else {
      onAdopt(pack);
    }
  }

  return (
    <div>
      <div className="actions">
        <button type="button" className={mode === "guided" ? "" : "danger"} onClick={() => setMode("guided")}>Guided</button>
        <button type="button" className={mode === "raw" ? "" : "danger"} onClick={() => setMode("raw")}>Advanced: raw JSON</button>
      </div>

      {mode === "raw" ? (
        <form className="form" onSubmit={onSubmit}>
          <label>Rule pack JSON
            <textarea rows={10} value={rawText} onChange={(e) => setRawText(e.target.value)}
                      placeholder='{"rule_pack_id": "...", "semver": "1.0.0", "requirements": [...]}' required />
          </label>
          <button type="submit" disabled={submitting}>{submitting ? "Adopting…" : "Adopt"}</button>
        </form>
      ) : (
        <form className="form" onSubmit={onSubmit}>
          <fieldset>
            <legend>Identity</legend>
            <label>Rule pack ID <span className="hint">(lowercase, dots/hyphens — e.g. cpcl.tender.2026.pumps)</span>
              <input value={rulePackId} onChange={(e) => setRulePackId(e.target.value)} required />
            </label>
            <label>Semver<input value={semver} onChange={(e) => setSemver(e.target.value)} required /></label>
            <label>Source document SHA-256 <span className="hint">(the tender PDF you're decomposing)</span>
              <input value={sourceDocSha} onChange={(e) => setSourceDocSha(e.target.value)} required pattern="[0-9a-f]{64}" />
            </label>
            <label>Issuing authority<input value={issuingAuthority} onChange={(e) => setIssuingAuthority(e.target.value)} required /></label>
          </fieldset>

          <fieldset>
            <legend>Scoring constants</legend>
            <p className="hint">Defaults match every rule pack adopted earlier this session — change only if this tender needs different tuning.</p>
            <div className="rule-pack-constants-grid">
              {Object.keys(DEFAULT_CONSTANTS).map((key) => (
                <label key={key} className="mono">{key}
                  <input type="number" step="any" value={constants[key]}
                         onChange={(e) => setConstants({ ...constants, [key]: Number(e.target.value) })} />
                </label>
              ))}
            </div>
            <label>Freshness days, GST_STATUS
              <input type="number" value={freshnessDays.GST_STATUS}
                     onChange={(e) => setFreshnessDays({ ...freshnessDays, GST_STATUS: Number(e.target.value) })} />
            </label>
            <label>Freshness days, PAN_STATUS
              <input type="number" value={freshnessDays.PAN_STATUS}
                     onChange={(e) => setFreshnessDays({ ...freshnessDays, PAN_STATUS: Number(e.target.value) })} />
            </label>
          </fieldset>

          <fieldset>
            <legend>Requirements</legend>
            {requirements.map((r) => (
              <div key={r.key} className="rule-pack-requirement">
                <div className="rule-pack-requirement-head">
                  <input className="mono" placeholder="Requirement ID (e.g. R1)" value={r.id}
                         onChange={(e) => updateReq(r.key, { id: e.target.value })} required />
                  <button type="button" onClick={() => removeRequirement(r.key)}>Remove</button>
                </div>
                <label>Text, quoted from the tender
                  <input value={r.text} onChange={(e) => updateReq(r.key, { text: e.target.value })} required />
                </label>
                <div className="actions">
                  <label>Page<input type="number" min="1" style={{ width: 70 }} value={r.page}
                                    onChange={(e) => updateReq(r.key, { page: e.target.value })} /></label>
                  <label>Obligation
                    <select value={r.obligation} onChange={(e) => updateReq(r.key, { obligation: e.target.value })}>
                      <option value="mandatory">mandatory</option>
                      <option value="desirable">desirable</option>
                    </select>
                  </label>
                  <label>Operator
                    <select value={r.operator} onChange={(e) => updateReq(r.key, { operator: e.target.value })}>
                      <option value="LEAF">LEAF (checks one thing)</option>
                      <option value="ALL_OF">ALL_OF (every child must hold)</option>
                      <option value="ANY_OF">ANY_OF (at least one child)</option>
                    </select>
                  </label>
                </div>

                {r.operator === "LEAF" ? (
                  <div className="actions">
                    <label>Evidence path
                      <input list="rule-pack-fields" value={r.field} onChange={(e) => updateReq(r.key, { field: e.target.value })} required />
                    </label>
                    <label>Check
                      <select value={r.predicateKind} onChange={(e) => updateReq(r.key, { predicateKind: e.target.value })}>
                        {Object.entries(PREDICATE_KINDS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                      </select>
                    </label>
                    {PREDICATE_KINDS[r.predicateKind].needsValue && (
                      <label>{PREDICATE_KINDS[r.predicateKind].valueLabel}
                        <input value={r.value} onChange={(e) => updateReq(r.key, { value: e.target.value })} required />
                      </label>
                    )}
                  </div>
                ) : (
                  <label>Children (comma-separated requirement IDs already added above)
                    <input value={r.children.join(",")}
                           onChange={(e) => updateReq(r.key, { children: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
                  </label>
                )}
              </div>
            ))}
            <datalist id="rule-pack-fields">
              {COMMON_FIELDS.map((f) => <option key={f} value={f} />)}
            </datalist>
            <button type="button" onClick={addRequirement}>+ Add requirement</button>
          </fieldset>

          <button type="submit" disabled={submitting}>{submitting ? "Adopting…" : "Adopt"}</button>
        </form>
      )}

      {mode === "guided" && pack && (
        <details className="rule-pack-preview">
          <summary>Preview the exact JSON this will submit</summary>
          <pre className="mono">{JSON.stringify(pack, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
