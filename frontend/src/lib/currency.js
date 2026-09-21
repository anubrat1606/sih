// Round 9: the one place a paise value becomes something a human reads.
//
// extract/financials.py (round 8) normalizes every extracted turnover/net
// worth figure to INR paise -- the same minor-unit convention
// schemas/rule_pack.schema.json already documents for every currency
// literal, so a rule pack's `gte` comparison actually compares like with
// like. Nothing on this frontend converted that back until now: an
// officer looking at a bidder's evidence saw a raw integer like
// 4500000000000000, wherever a financial value renders -- the Evidence
// tab, Bid Autopsy, the upload result table, the evidence graph.
//
// Only these two evidence paths are ever paise -- their _financial_year
// companions are already human-readable strings ("FY 2024-25") and must
// never be run through this.
export const FINANCIAL_AMOUNT_PATHS = new Set([
  "bidder.financials.turnover",
  "bidder.financials.net_worth",
]);

/**
 * Paise -> "₹45,00,00,000" (Indian digit grouping via Intl.NumberFormat's
 * "en-IN" locale, which groups in lakh/crore steps after the first three
 * digits -- exactly the grouping the source statement itself prints,
 * unlike plain thousands-grouping "en-IN" would get wrong for this).
 */
export function formatPaiseAsRupees(paise) {
  if (typeof paise !== "number" || !Number.isFinite(paise)) return String(paise);
  const rupees = paise / 100;
  return `₹${new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(rupees)}`;
}

/**
 * The one function every evidence-value render site should call instead
 * of `String(value)` directly. Formats a financial amount path as
 * rupees; passes every other path through unchanged (still a plain
 * String() -- this is a formatting decision, not a new fallback that
 * could paper over a value this function doesn't recognize).
 */
export function formatEvidenceValue(path, value) {
  if (FINANCIAL_AMOUNT_PATHS.has(path)) return formatPaiseAsRupees(value);
  return String(value);
}
