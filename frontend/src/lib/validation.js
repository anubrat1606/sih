// Client-side structural pre-checks — nothing more. Mirrors
// services/orchestrator/satyapramana_store/extract/grammars.py exactly
// (the same regexes, the same GSTIN check-digit algorithm, the same
// closed value sets for a PAN holder type / CIN RoC state code / CIN
// ownership class), so a bidder gets the identical "this looks wrong"
// signal the server would eventually give, before a round trip.
//
// A structural check is NOT verification. These functions never claim a
// GSTIN, PAN, or CIN is real — only that it is shaped the way a real one
// would be. "This could be a GSTIN," never "this GSTIN is valid." The
// server, and beyond it the live GST/PAN/CIN authority, remains the one
// real verifier — this exists only to save a wasted round trip on an
// obviously malformed value.
//
// Pure functions, no React, no fetch — safe to unit-test by reading.

const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/;
const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;
const CIN_RE = /^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$/;

// The fourth character of a PAN is the holder type. Ported from
// grammars.py::PAN_HOLDER_TYPES verbatim.
const PAN_HOLDER_TYPES = {
  A: "Association of Persons", B: "Body of Individuals", C: "Company",
  F: "Firm", G: "Government", H: "Hindu Undivided Family",
  J: "Artificial Juridical Person", L: "Local Authority", P: "Individual",
  T: "Trust",
};

// GST state codes in use, plus 97 (other territory) and 99 (centre
// jurisdiction). Ported from grammars.py::GST_STATE_CODES — same caveat
// applies: verify against the current GST notification before relying on
// it for anything beyond a UX hint.
const GST_STATE_CODES = new Set([
  ...Array.from({ length: 38 }, (_, i) => String(i + 1).padStart(2, "0")),
  "97", "99",
]);

// The 2-letter Registrar-of-Companies state code embedded in a CIN
// (characters 7-8). Ported from grammars.py::CIN_ROC_STATE_CODES.
const CIN_ROC_STATE_CODES = new Set([
  "AP", "AR", "AS", "BR", "CH", "CG", "CT", "DL", "GA", "GJ", "HP", "HR",
  "JH", "JK", "KA", "KL", "MH", "ML", "MN", "MP", "MZ", "NL", "OR", "PB",
  "PY", "RJ", "SK", "TG", "TN", "TR", "UK", "UP", "UT", "WB",
  "AN", "DN", "DD", "LD",
]);

// The 3-letter ownership class embedded in a CIN (characters 13-15).
// Ported from grammars.py::CIN_OWNERSHIP_CLASSES. The task brief for this
// file names three CIN checks (grammar, RoC state, year range); this
// fourth one is included too because "mirroring grammars.py exactly" is
// the stronger instruction, and the real validate_cin() checks it —
// leaving it out would make this pre-check weaker than the server's,
// letting a bidder submit a shape the server would still reject.
const CIN_OWNERSHIP_CLASSES = new Set([
  "PLC", "PTC", "OPC", "SGC", "GOI", "NPL", "GAP", "GAT", "FLC", "FTC",
  "ULL", "ULT",
]);

// The plausible span for a CIN's incorporation year — a fixed sentinel,
// not the current year, so this gives the same answer regardless of when
// it runs. Ported from grammars.py::CIN_YEAR_MIN / CIN_YEAR_MAX.
const CIN_YEAR_MIN = 1857;
const CIN_YEAR_MAX = 2100;

const B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";

// The published GSTIN check-digit algorithm, over the first 14 characters
// — base-36 values, alternating weights of 1 and 2, summing the quotient
// and remainder of each product. Ported line-for-line from
// grammars.py::gstin_check_digit so the two implementations can't
// quietly drift apart.
function gstinCheckDigit(first14) {
  let total = 0;
  for (let i = 0; i < first14.length; i++) {
    const value = B36.indexOf(first14[i]);
    const product = value * (i % 2 ? 2 : 1);
    total += Math.floor(product / 36) + (product % 36);
  }
  return B36[(36 - (total % 36)) % 36];
}

// Characters 3-12 of a GSTIN are the holder's PAN.
function panFromGstin(gstin) {
  return gstin.slice(2, 12);
}

/**
 * @param {string} value
 * @returns {{ok: boolean, detail: string}}
 */
export function checkPanFormat(value) {
  const v = value || "";
  if (!PAN_RE.test(v)) {
    return { ok: false, detail: "does not match the PAN grammar" };
  }
  const holder = v[3];
  if (!(holder in PAN_HOLDER_TYPES)) {
    return { ok: false, detail: `'${holder}' is not a known PAN holder type` };
  }
  return { ok: true, detail: `holder type ${holder} (${PAN_HOLDER_TYPES[holder]})` };
}

/**
 * @param {string} value
 * @returns {{ok: boolean, detail: string}}
 */
export function checkGstinFormat(value) {
  const v = value || "";
  if (!GSTIN_RE.test(v)) {
    return { ok: false, detail: "does not match the GSTIN grammar" };
  }
  const state = v.slice(0, 2);
  if (!GST_STATE_CODES.has(state)) {
    return { ok: false, detail: `'${state}' is not a GST state code in use` };
  }
  const embedded = panFromGstin(v);
  const pan = checkPanFormat(embedded);
  if (!pan.ok) {
    return { ok: false, detail: `embedded PAN ${embedded} is invalid: ${pan.detail}` };
  }
  const expected = gstinCheckDigit(v.slice(0, 14));
  if (v[14] !== expected) {
    return { ok: false, detail: `check digit is ${v[14]}, expected ${expected}` };
  }
  return { ok: true, detail: `state ${state}, embedded PAN ${embedded}` };
}

/**
 * @param {string} value
 * @returns {{ok: boolean, detail: string}}
 */
export function checkCinFormat(value) {
  const v = value || "";
  if (!CIN_RE.test(v)) {
    return { ok: false, detail: "does not match the CIN grammar" };
  }
  const roc = v.slice(6, 8);
  if (!CIN_ROC_STATE_CODES.has(roc)) {
    return { ok: false, detail: `'${roc}' is not a Registrar-of-Companies state code in use` };
  }
  const year = parseInt(v.slice(8, 12), 10);
  if (year < CIN_YEAR_MIN || year > CIN_YEAR_MAX) {
    return { ok: false, detail: `incorporation year ${year} is outside ${CIN_YEAR_MIN}-${CIN_YEAR_MAX}` };
  }
  const ownership = v.slice(12, 15);
  if (!CIN_OWNERSHIP_CLASSES.has(ownership)) {
    return { ok: false, detail: `'${ownership}' is not a known CIN ownership class` };
  }
  return { ok: true, detail: `state ${roc}, incorporated ${year}` };
}
