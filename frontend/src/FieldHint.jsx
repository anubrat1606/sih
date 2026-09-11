import "./fieldHint.css";

// result is one of validation.js's return shapes, or null/undefined for
// "field not yet touched" -- renders nothing in that case (and nothing for
// an empty hint too, e.g. the field was touched then cleared back out).
// Colour is never the only signal: every tone also carries a glyph and a
// text label, the same rule VerdictBadge already follows in components.jsx.
export function FieldHint({ result }) {
  if (!result || !result.hint) return null;
  const tone = result.valid === true ? "positive" : result.valid === false ? "negative" : "neutral";
  const glyph = tone === "positive" ? "✓" : tone === "negative" ? "✕" : "…";
  return (
    <div className={`field-hint field-hint-${tone}`}>
      <span aria-hidden="true">{glyph}</span>
      <span>{result.hint}</span>
    </div>
  );
}
