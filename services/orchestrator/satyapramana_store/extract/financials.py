"""Financial-statement extraction: turnover and net worth, read from a
table in a submitted financial statement (balance sheet / statement of
profit and loss).

Unlike every other field this package extracts, there is no authority to
verify a claimed turnover or net worth against -- nothing like GST_STATUS
exists for financial figures. A mandatory requirement built on this
evidence therefore stays capped at PARTIAL (self-declared ceiling -- see
requirement_types.py's MIN_TURNOVER/NET_WORTH notes, and
docs/VERDICT_ALGEBRA.md). This module's job is to get a real, honestly
extracted number onto the evidence path, not to build a path to a
verified PASS that will never exist.

Table detection needs pdfplumber's own Table object (Page.find_tables()),
which extract/layout.py's Page dataclass deliberately does not carry -- it
only ever extracted words, for exactly this project's identifier-grammar
use case (see layout.py's own module docstring). So this re-reads the raw
document bytes with pdfplumber directly rather than reusing read_pdf()'s
output -- the same "a second, genuinely different technique needs its own
read of the source" reasoning find_pan_holder_fields/find_document_dates
in ingest.py already established for layout-based (as opposed to
grammar-based) fields. find_tables() rather than the simpler
extract_table() specifically because each row's real bounding box is
then available -- ingest.py's own module docstring is explicit that every
extracted value in this project carries a real page + pixel region, never
a placeholder; a financial figure gets the same standard as every
identifier.
"""
from __future__ import annotations

import io
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from .ingest import Candidate

#: Row-label synonyms for turnover / revenue, drawn from Schedule III
#: (Companies Act, 2013) statement-of-profit-and-loss terminology -- the
#: standard format an Indian company's filed financial statements use.
#: More variants can be added here without touching anything else in this
#: module.
_TURNOVER_LABELS = (
    "REVENUE FROM OPERATIONS", "TOTAL REVENUE", "TURNOVER", "NET SALES",
    "TOTAL INCOME",
)

#: Row-label synonyms for net worth, same Schedule III convention.
_NET_WORTH_LABELS = (
    "NET WORTH", "TOTAL EQUITY", "SHAREHOLDERS FUNDS", "SHAREHOLDERS' FUNDS",
    "TOTAL SHAREHOLDERS EQUITY",
)

#: Evidence-field key -> the row labels that identify it, and the
#: human-readable phrase used in a failure detail message.
_FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "turnover": _TURNOVER_LABELS,
    "net_worth": _NET_WORTH_LABELS,
}
_FIELD_PHRASE = {"turnover": "turnover", "net_worth": "net worth"}

#: A trailing footnote reference on a label cell ("Revenue from Operations
#: (Note 15)", "Net Worth (Refer Note 12)") -- stripped before comparing,
#: since the core label text is still an exact statement of what the row
#: is, just with a citation appended. This is tolerance for a citation
#: suffix, not fuzzy matching: the label text itself must still match
#: exactly.
_NOTE_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _normalize_label(text: str | None) -> str:
    text = _NOTE_SUFFIX_RE.sub("", text or "")
    return re.sub(r"\s+", " ", text.strip().upper())


#: A financial year as a statement's column header actually prints it --
#: "2024-25", "FY 2024-25", "FY24", or a bare "2024". Matched loosely on
#: purpose: the exact wording varies by filer, but the shape (a year,
#: optionally followed by a second two-digit year after a dash, optionally
#: prefixed "FY") does not.
_YEAR_RE = re.compile(r"(?:FY\s*)?(\d{4})(?:[-/]\d{2,4})?", re.IGNORECASE)

#: The statement's own stated unit -- read once, from anywhere in the
#: document's text, and applied to every figure. Deliberately captures the
#: whole run of unit-shaped words after "in" (a real statement often
#: prints the currency AND the scale together, e.g. "in Rupees Lakhs" or
#: "(₹ in Crore)") rather than grabbing only the first word, so a phrase
#: like "in Rupees Lakhs" resolves to lakhs, not to "rupees" (i.e. no
#: scaling) just because "Rupees" happens to come first.
_UNIT_STATEMENT_RE = re.compile(
    r"in\s+((?:₹|Rs\.?|INR|lakhs?|crores?|rupees?|of|and|\s)+)", re.IGNORECASE)
_UNIT_MULTIPLIER = {"crore": 10_000_000, "lakh": 100_000, "rupees": 1}


def _detect_unit(text: str) -> tuple[int, str] | None:
    """None means undetermined -- not a default. A document that never
    states its unit gets no figure extracted from it at all (see
    _extract_field), rather than a figure silently normalized against a
    guessed one."""
    m = _UNIT_STATEMENT_RE.search(text)
    if not m:
        return None
    phrase = m.group(1)
    if re.search(r"\bcrores?\b", phrase, re.IGNORECASE):
        return _UNIT_MULTIPLIER["crore"], "crore"
    if re.search(r"\blakhs?\b", phrase, re.IGNORECASE):
        return _UNIT_MULTIPLIER["lakh"], "lakh"
    if re.search(r"₹|Rs\.?|INR|\brupees?\b", phrase, re.IGNORECASE):
        return _UNIT_MULTIPLIER["rupees"], "rupees"
    return None


def _parse_amount(cell: str | None) -> Decimal | None:
    """A table cell's printed figure -> a plain magnitude. Handles the
    punctuation a real statement actually prints: thousands separators, a
    currency symbol, and parentheses for a negative figure (standard
    accounting notation). Returns None -- never a guess -- for anything
    that does not parse as a number."""
    if not cell:
        return None
    text = cell.strip()
    if not text or text in ("-", "—", "–"):
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = re.sub(r"[₹Rs\.,\s]", "", text, flags=re.IGNORECASE)
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return -value if negative else value


def _find_label_row(grid: list[list[str | None]], labels: tuple[str, ...]) -> int | None:
    for i, row in enumerate(grid):
        if row and _normalize_label(row[0]) in labels:
            return i
    return None


def _year_in_column(grid: list[list[str | None]], col: int) -> tuple[int, str] | None:
    """The row index and text of the first row (scanning top to bottom --
    a header is always above its data) whose value in this column looks
    like a financial year. The row index travels with the match so the
    caller can cite the real cell the year was read from, not an assumed
    header position -- a statement's header can sit one or two rows above
    the first data row."""
    for i, row in enumerate(grid):
        if col >= len(row):
            continue
        m = _YEAR_RE.search(row[col] or "")
        if m:
            return i, m.group(0).strip()
    return None


def _cell_bbox(table: Any, row: int, col: int) -> tuple[float, float, float, float]:
    """pdfplumber gives no bbox for a merged/spanned cell -- an all-zero
    region is an honest "not available", never a guessed rectangle."""
    try:
        bbox = table.rows[row].cells[col]
    except IndexError:
        bbox = None
    return tuple(bbox) if bbox else (0.0, 0.0, 0.0, 0.0)


def _extract_field(
    field: str, tables: list[tuple[int, Any]], unit: tuple[int, str] | None,
) -> list[Candidate]:
    """The first table (in page order) that carries this field's label
    wins -- one printed statement per document, the same "first match is
    authoritative" convention find_pan_holder_fields uses for a repeated
    label. A label not present on any table is absence, not failure: it
    produces nothing here, exactly like every other label/value finder in
    this package when a document simply does not have that field."""
    phrase = _FIELD_PHRASE[field]
    for page_number, table in tables:
        grid = table.extract()
        idx = _find_label_row(grid, _FIELD_LABELS[field])
        if idx is None:
            continue

        row = grid[idx]
        label_bbox = _cell_bbox(table, idx, 0)
        if len(row) < 2 or not (row[1] or "").strip():
            return [Candidate(field, "", page_number, label_bbox, False,
                              f"the {phrase} row has no adjacent value column")]

        raw = row[1]
        value_bbox = _cell_bbox(table, idx, 1)
        amount = _parse_amount(raw)
        year_match = _year_in_column(grid, 1)
        year = year_match[1] if year_match else None

        out: list[Candidate] = []
        if amount is None:
            out.append(Candidate(field, raw, page_number, value_bbox, False,
                                 f"'{raw}' next to the {phrase} label does not read as a number"))
        elif unit is None:
            out.append(Candidate(field, raw, page_number, value_bbox, False,
                                 "a numeric value was found but the statement's unit "
                                 "(lakhs / crore / rupees) could not be determined -- "
                                 "normalizing against a guessed unit would be worse than "
                                 "no figure at all"))
        else:
            multiplier, unit_label = unit
            paise = int((amount * multiplier * 100).to_integral_value())
            detail = f"{raw!r} read as {amount} {unit_label}"
            if year:
                detail += f", financial year {year}"
            out.append(Candidate(field, paise, page_number, value_bbox, True, detail))

        if year_match:
            year_row, year_text = year_match
            year_bbox = _cell_bbox(table, year_row, 1)
            out.append(Candidate(f"{field}_financial_year", year_text, page_number, year_bbox,
                                 True, f"read from the column header above the {phrase} row"))
        return out
    return []


def find_financial_fields(data: bytes) -> list[Candidate]:
    """Scan every table pdfplumber can find, across every page, for a
    turnover or net-worth row, and normalize the figure to INR paise
    using the statement's own stated unit -- the same minor-unit
    convention schemas/rule_pack.schema.json already documents for every
    currency literal in this system, so a rule pack author writing e.g.
    {"op": "gte", "left": {"field": "bidder.financials.turnover"},
     "right": {"literal": 5000000000000}} compares like with like.
    """
    import pdfplumber

    tables: list[tuple[int, Any]] = []
    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
            for table in page.find_tables():
                tables.append((page.page_number, table))

    unit = _detect_unit("\n".join(text_parts))
    candidates: list[Candidate] = []
    for field in _FIELD_LABELS:
        candidates.extend(_extract_field(field, tables, unit))
    return candidates
