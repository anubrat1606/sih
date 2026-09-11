// Pure functions, no React -- fully unit-testable in isolation, and safe to
// call on every keystroke with no side effects.
//
// These mirror the SHAPE services/orchestrator/satyapramana_store/extract/
// grammars.py validates server-side (GSTIN_RE, PAN_RE, CIN_RE there), but
// this is a UX hint only: it must never claim a value is valid or invalid
// with more confidence than "looks structurally plausible" vs "doesn't."
// The server remains the one real validator -- this only saves a wasted
// round trip for an obviously malformed value.
//
// Return shape: { valid: true | false | null, hint: string }.
//   valid === null  -> too short to judge yet (neutral tone).
//   valid === true  -> matches the expected shape (positive tone).
//   valid === false -> long enough to judge, and doesn't match (negative tone).
// An empty/untouched value returns an empty hint (never null), leaving the
// caller (FieldHint) to decide that "no hint" means "render nothing."

const GSTIN_SHAPE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
const PAN_SHAPE = /^[A-Z]{5}[0-9]{4}[A-Z]$/;
const CIN_SHAPE = /^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$/;

function checkShape(value, expectedLength, shapeRe, label) {
  const v = (value || "").trim().toUpperCase();
  if (!v) return { valid: null, hint: "" };
  if (v.length < expectedLength) {
    return { valid: null, hint: `${v.length}/${expectedLength} characters` };
  }
  if (shapeRe.test(v)) {
    return { valid: true, hint: "Looks structurally plausible" };
  }
  return { valid: false, hint: `Doesn't match the ${label} shape -- the server will confirm` };
}

// 2-digit state code + 10-char PAN + 1-digit entity code + literal "Z" +
// 1 checksum char = 15 characters total.
export function checkGstinFormat(value) {
  return checkShape(value, 15, GSTIN_SHAPE, "GSTIN");
}

// 5 letters + 4 digits + 1 letter, 10 characters total.
export function checkPanFormat(value) {
  return checkShape(value, 10, PAN_SHAPE, "PAN");
}

// Listing status (L/U) + 5-digit industry code + 2-letter state code +
// 4-digit year + 3-letter ownership class + 6-digit registration number,
// 21 characters total.
export function checkCinFormat(value) {
  return checkShape(value, 21, CIN_SHAPE, "CIN");
}
