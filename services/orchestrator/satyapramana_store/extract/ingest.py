"""INGEST and the deterministic half of EXTRACT.

The whole path here runs with no model involved. That is the charter's
tell-tale test made concrete: for a document with a text layer, the system
locates statutory identifiers, validates them structurally, and records their
exact page and region -- so the provenance walk reaches the source document and
a click lands on the right line, with no AI in the path at all.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .grammars import (
    PATTERNS, SCAN_ORDER, VALIDATORS, parse_document_date, pan_from_gstin,
    validate_claimed_business_name, validate_document_date,
    validate_pan_date_of_birth, validate_pan_holder_name,
)
from .layout import Page, Word, lines, locate, read_pdf, searchable
from .vlm import UnconfiguredVisionStage

from ..events import Actor, append

INGEST = Actor("SYSTEM", "ingest@1.0.0")
EXTRACT = Actor("SYSTEM", "extract-deterministic@1.0.0")

#: Where uploaded documents are written. A local directory stands in for object
#: storage; the interface is one function, so swapping it is contained.
DOCUMENT_DIR = Path(os.environ.get("SATYAPRAMANA_DOCUMENT_DIR", "documents"))

#: Evidence paths this stage produces. Rule pack validation resolves predicate
#: operands against the union of these and the registered capabilities' paths --
#: "no producing stage or adapter" means both, not just adapters.
FIELD_PATHS = {
    "gstin": "bidder.gst.gstin",
    "pan_number": "bidder.pan.pan_number",
    "udyam_number": "bidder.udyam.udyam_number",
    "cin": "bidder.entity.cin",
    "pan_holder_name": "bidder.pan.holder_name",
    "pan_date_of_birth": "bidder.pan.date_of_birth",
    "gst_date_of_issue": "bidder.gst.date_of_issue",
    "gst_date_of_expiry": "bidder.gst.date_of_expiry",
    # "claimed_" -- deliberately distinct from bidder.gst.legal_name, which
    # is the live GST_STATUS adapter's own path for the authority's answer
    # (adapters/sandbox_co_in.py). evidence.py folds by "later event wins";
    # writing here into that same path would let extraction silently
    # overwrite verification's answer, or verification silently overwrite
    # this, with no error either way. These paths exist so a future FUSE
    # step can compare the bidder's own claim against the authority instead.
    "gst_claimed_legal_name": "bidder.gst.claimed_legal_name",
    "gst_claimed_trade_name": "bidder.gst.claimed_trade_name",
    # Financial-statement extraction (extract/financials.py). Self-declared
    # -- no authority exists to verify a claimed turnover or net worth
    # against, so a mandatory requirement built on either path stays
    # capped at PARTIAL regardless (requirement_types.py's own notes).
    "turnover": "bidder.financials.turnover",
    "turnover_financial_year": "bidder.financials.turnover_financial_year",
    "net_worth": "bidder.financials.net_worth",
    "net_worth_financial_year": "bidder.financials.net_worth_financial_year",
}


@dataclass(frozen=True)
class Candidate:
    field: str
    value: str
    page: int
    region: tuple[float, float, float, float]
    valid: bool
    detail: str


def store_document(data: bytes, bidder_id: str, filename: str) -> tuple[str, str]:
    digest = hashlib.sha256(data).hexdigest()
    target = DOCUMENT_DIR / bidder_id / f"{digest[:16]}-{Path(filename).name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return digest, str(target)


def find_candidates(pages: list[Page]) -> tuple[list[Candidate], list[dict[str, Any]]]:
    """Scan every page for statutory identifiers and locate each one exactly.

    Longest grammar first: a GSTIN contains a PAN, so scanning for PAN first
    would match inside every GSTIN and report the same characters twice.
    """
    candidates: list[Candidate] = []
    unreadable: list[dict[str, Any]] = []
    vision = UnconfiguredVisionStage()

    for page in pages:
        if not page.has_text_layer:
            outcome = vision.candidates(page)
            unreadable.append({"page": page.number, "stage": outcome.stage,
                               "reason": outcome.reason})
            continue

        haystack, index = searchable(page)
        claimed: list[tuple[int, int]] = []
        for field in SCAN_ORDER:
            for match in PATTERNS[field].finditer(haystack):
                start, end = match.span()
                if any(s < end and e > start for s, e in claimed):
                    continue  # already accounted for by a longer identifier
                span = locate(page, start, end, index)
                check = VALIDATORS[field](match.group())
                candidates.append(Candidate(field, match.group(), span.page,
                                            span.region, check.ok, check.detail))
                # Claimed whether or not it validated. A GSTIN contains a PAN,
                # so a GSTIN rejected for a bad check digit would otherwise have
                # its embedded characters harvested as a standalone PAN -- which
                # asserts something the document does not say. The characters
                # belong to the GSTIN candidate either way.
                claimed.append((start, end))
    return candidates, unreadable


# --- PAN cardholder fields: label above value, not a grammar scan -----------
#
# A person's name or date of birth has no regex -- there is no PATTERNS entry
# that finds "somebody's name" anywhere in page text the way GSTIN_RE finds a
# GSTIN. What a PAN card gives instead is document layout: a printed label
# ("Name", "Date of Birth") with the value on the line directly beneath it.
# So this reads line structure (layout.lines()) rather than scanning
# searchable() text, and the field's grammar (grammars.py) only ever
# validates a value that was already found this way.

#: label line -> (evidence-path field key, structural validator). The label
#: is matched as a whole printed line (case-insensitive, trailing colon
#: ignored) so "Name of Company" (three words) never matches the one-word
#: label "Name".
PAN_HOLDER_FIELDS: dict[tuple[str, ...], tuple[str, Any]] = {
    ("NAME",): ("pan_holder_name", validate_pan_holder_name),
    ("DATE", "OF", "BIRTH"): ("pan_date_of_birth", validate_pan_date_of_birth),
}

#: Evidence field key -> the label lines that might precede its value,
#: tried in order (first one found on the page wins). A field can be printed
#: under more than one wording depending on document type -- a GST
#: certificate might say "Date of Issue", something else "Issued on" -- the
#: same reason "Name" and "Date of Birth" needed two separate label lookups
#: on the PAN card, just now more than one label can point at the same
#: field.
DOCUMENT_DATE_LABELS: dict[str, tuple[tuple[str, ...], ...]] = {
    "gst_date_of_issue": (("DATE", "OF", "ISSUE"), ("ISSUED", "ON")),
    "gst_date_of_expiry": (("DATE", "OF", "EXPIRY"), ("VALID", "UNTIL")),
}

#: label line -> (evidence-path field key, structural validator). GST
#: REG-06 is a fixed government form with one canonical wording each -- no
#: alternates needed, same shape as PAN_HOLDER_FIELDS. "Trade Name" is
#: commonly blank (not every registered business trades under a different
#: name), which _read_value_under_label already treats as a normal,
#: recordable EXTRACTION_FAILED rather than an error.
GST_CLAIMED_NAME_FIELDS: dict[tuple[str, ...], tuple[str, Any]] = {
    ("LEGAL", "NAME"): ("gst_claimed_legal_name", validate_claimed_business_name),
    ("TRADE", "NAME"): ("gst_claimed_trade_name", validate_claimed_business_name),
}

#: If the line under a label is itself one of these known label phrases, the
#: field is blank on the card -- reading it anyway would assert a value the
#: document does not actually state.
_KNOWN_LABEL_LINES = (
    {" ".join(words) for words in PAN_HOLDER_FIELDS}
    | {" ".join(words) for options in DOCUMENT_DATE_LABELS.values() for words in options}
    | {" ".join(words) for words in GST_CLAIMED_NAME_FIELDS}
    | {"PERMANENT ACCOUNT NUMBER", "FATHER'S NAME", "FATHERS NAME", "SIGNATURE"}
)


def _line_text(line: list[Word]) -> str:
    return " ".join(w.text for w in line).strip()


def _line_region(line: list[Word]) -> tuple[float, float, float, float]:
    return (min(w.x0 for w in line), min(w.top for w in line),
            max(w.x1 for w in line), max(w.bottom for w in line))


def _label_line_index(grouped: list[list[Word]], label_words: tuple[str, ...]) -> int | None:
    for i, line in enumerate(grouped):
        texts = tuple(w.text.strip().rstrip(":").upper() for w in line)
        if texts == label_words:
            return i
    return None


def _first_label_line_index(
    grouped: list[list[Word]], label_options: tuple[tuple[str, ...], ...],
) -> int | None:
    """The first of several acceptable label wordings that is actually on
    the page. Order is a tie-break, not a preference -- a document prints at
    most one wording of any given label."""
    for label_words in label_options:
        idx = _label_line_index(grouped, label_words)
        if idx is not None:
            return idx
    return None


def _read_value_under_label(
    page: Page, grouped: list[list[Word]], idx: int, field: str, validate: Any,
) -> Candidate:
    """`idx` is a confirmed label line. Read the line beneath it and
    validate it; a blank line or a line that is itself another known label
    is reported as an invalid Candidate (the field is blank on the
    document), never as a guessed value."""
    if idx + 1 >= len(grouped):
        return Candidate(
            field, "", page.number, _line_region(grouped[idx]), False,
            "the label is the last line on the page; no value line follows it")
    value_line = grouped[idx + 1]
    text = _line_text(value_line)
    region = _line_region(value_line)
    if not text:
        return Candidate(field, text, page.number, region, False,
                          "the line under the label is blank")
    if text.rstrip(":").upper() in _KNOWN_LABEL_LINES:
        return Candidate(
            field, text, page.number, region, False,
            "the line under the label is itself a printed label -- the field is blank")
    check = validate(text)
    return Candidate(field, text, page.number, region, check.ok, check.detail)


def find_pan_holder_fields(pages: list[Page]) -> list[Candidate]:
    """Read the PAN cardholder's printed name and date of birth.

    A label with no matching line anywhere on the page produces nothing here
    -- exactly like find_candidates when a page simply has no GSTIN on it;
    the field's absence is not itself a failure worth recording. A label
    that IS found but has no plausible value beneath it (blank line, or the
    next line is itself another label) produces an invalid Candidate, so the
    caller records EXTRACTION_FAILED with the real reason instead of a guess.
    """
    candidates: list[Candidate] = []
    found: set[str] = set()
    for page in pages:
        if not page.has_text_layer:
            continue  # find_candidates already records this page as unreadable
        grouped = lines(page)
        labelled_here = False
        for label_words, (field, validate) in PAN_HOLDER_FIELDS.items():
            if field in found:
                continue  # a document has one printed value per field, not
                          # one per page that happens to repeat the label --
                          # the first page found is authoritative, and this
                          # is what keeps one FIELD_EXTRACTED per field true
                          # (docs/EVENTS.md) even if a label is repeated
            idx = _label_line_index(grouped, label_words)
            if idx is None:
                continue
            labelled_here = True
            candidates.append(_read_value_under_label(page, grouped, idx, field, validate))
            found.add(field)
        if not labelled_here and not found:
            for candidate in _pan_anchored_holder_fields(page, grouped):
                candidates.append(candidate)
                found.add(candidate.field)
    return candidates


# Seen on a real UTIITSL e-PAN (2026-09-12): the card's labels ("Name",
# "Date of Birth") are part of the artwork -- an image -- and the text layer
# carries only the printed values, in the card's fixed order: the PAN, then
# the holder's name, then the father's name, then the date of birth. With no
# label on the page the reader above finds nothing, PAN_STATUS can't be
# asked (Sandbox needs name + DOB), and a genuine card verifies as UNKNOWN.
#
# The PAN itself is the anchor here instead of a label: it is located by
# grammar and check-validated first, exactly like every other identifier.
# The three lines beneath it must then read, in order, as a name, a name and
# a dd/mm/yyyy date, or nothing is emitted at all -- an absence, like a label
# that isn't on the page, never a partial guess. The card's own order is what
# decides which name line is the holder's; if a card ever printed them the
# other way round, the authority's own name check refuses it, and the
# provenance shows exactly which line was read.
def _pan_anchored_holder_fields(page: Page, grouped: list[list[Word]]) -> list[Candidate]:
    for i, line in enumerate(grouped):
        anchor = next((w.text for w in line
                       if PATTERNS["pan_number"].fullmatch(w.text) and VALIDATORS["pan_number"](w.text).ok),
                      None)
        if anchor is None or i + 3 >= len(grouped):
            continue
        name_line, father_line, dob_line = grouped[i + 1], grouped[i + 2], grouped[i + 3]
        name, father, dob = _line_text(name_line), _line_text(father_line), _line_text(dob_line)
        if any(t.rstrip(":").upper() in _KNOWN_LABEL_LINES for t in (name, father, dob)):
            continue  # labels are in the text layer after all -- not this layout
        name_check = validate_pan_holder_name(name)
        dob_check = validate_pan_date_of_birth(dob)
        if not (name_check.ok and validate_pan_holder_name(father).ok and dob_check.ok):
            continue
        return [
            Candidate("pan_holder_name", name, page.number, _line_region(name_line),
                      True, name_check.detail),
            Candidate("pan_date_of_birth", dob, page.number, _line_region(dob_line),
                      True, dob_check.detail),
        ]
    return []


def find_gst_claimed_names(pages: list[Page]) -> list[Candidate]:
    """Read the business name(s) a GST certificate prints for itself --
    'Legal Name' and, if present, 'Trade Name'.

    This is the bidder's own CLAIM about their name, not the authority's
    answer -- see the comment on gst_claimed_legal_name/gst_claimed_trade_name
    in FIELD_PATHS for why that distinction has to be a different evidence
    path, not just a different value at the same one. Nothing here writes to
    bidder.gst.legal_name.

    Same absence/failure rules as every other label/value field in this
    module: a label not on the page produces nothing (not itself a
    failure); a label with no plausible value beneath it produces an
    invalid Candidate, so the caller records EXTRACTION_FAILED with the
    real reason, never a guess.
    """
    candidates: list[Candidate] = []
    found: set[str] = set()
    for page in pages:
        if not page.has_text_layer:
            continue
        grouped = lines(page)
        for label_words, (field, validate) in GST_CLAIMED_NAME_FIELDS.items():
            if field in found:
                continue  # one printed value per field, not one per page --
                          # see the identical guard in find_pan_holder_fields
            idx = _label_line_index(grouped, label_words)
            if idx is None:
                continue
            candidates.append(_read_value_under_label(page, grouped, idx, field, validate))
            found.add(field)
    return candidates


def find_document_dates(pages: list[Page], *, today: date | None = None) -> list[Candidate]:
    """Read a document's printed issue/expiry dates: label on one line
    (tried under each of its known alternate wordings), value on the line
    beneath -- the same label/value technique as find_pan_holder_fields.

    Validation happens in two passes. Each date is checked on its own as it
    is found (real calendar date, DD/MM/YYYY -- grammars.validate_document_date).
    Once both of a document's dates are known, a second pass
    (_cross_check_document_dates) checks they make sense together: an issue
    date in the future, or an expiry before the document's own issue date,
    is a value the first pass cannot catch on its own but is still not one
    to accept silently.

    `today` defaults to the real current date in production
    (ingest_document never passes it) and exists as a parameter so a test
    can pin the reference date instead of depending on when the suite
    happens to run.
    """
    candidates: list[Candidate] = []
    found: set[str] = set()
    for page in pages:
        if not page.has_text_layer:
            continue
        grouped = lines(page)
        for field, label_options in DOCUMENT_DATE_LABELS.items():
            if field in found:
                continue  # one printed value per field, not one per page --
                          # see the identical guard in find_pan_holder_fields
            idx = _first_label_line_index(grouped, label_options)
            if idx is None:
                continue
            candidates.append(
                _read_value_under_label(page, grouped, idx, field, validate_document_date))
            found.add(field)
    return _cross_check_document_dates(candidates, today=today)


def _cross_check_document_dates(
    candidates: list[Candidate], *, today: date | None = None,
) -> list[Candidate]:
    """A grammatically valid date can still be an implausible one in
    context: an issue date after today, or an expiry date before this same
    document's own issue date. Neither check is possible inside
    validate_document_date, which sees one string at a time and must not
    reach for the wall clock itself (see its docstring) -- so both run here,
    once, after both fields (if present) have already passed the grammar
    check on their own.
    """
    by_field = {c.field: c for c in candidates if c.valid}
    issue = by_field.get("gst_date_of_issue")
    expiry = by_field.get("gst_date_of_expiry")
    issue_date = parse_document_date(issue.value) if issue else None
    expiry_date = parse_document_date(expiry.value) if expiry else None
    reference = today or date.today()

    def revise(candidate: Candidate) -> Candidate:
        if candidate is issue and issue_date is not None and issue_date > reference:
            return Candidate(
                candidate.field, candidate.value, candidate.page, candidate.region, False,
                f"{candidate.value} is an issue date in the future")
        if (candidate is expiry and issue_date is not None and expiry_date is not None
                and expiry_date < issue_date):
            return Candidate(
                candidate.field, candidate.value, candidate.page, candidate.region, False,
                f"expiry {candidate.value} is before this document's own issue date "
                f"{issue.value}")
        return candidate

    return [revise(c) for c in candidates]


def ingest_document(
    conn, *, tender_id: str, bidder_id: str, filename: str, data: bytes,
    declared_type: str | None = None, correlation_id: str | None = None,
) -> dict[str, Any]:
    """Ingest, extract, and record. Returns what was found and what was not."""
    correlation = correlation_id or str(uuid.uuid4())
    digest, storage_ref = store_document(data, bidder_id, filename)

    document = append(
        conn, event_type="DOCUMENT_INGESTED", actor=INGEST,
        correlation_id=correlation, tender_id=tender_id, bidder_id=bidder_id,
        payload={"document_sha256": digest, "storage_ref": storage_ref,
                 "filename": Path(filename).name,
                 "declared_type": declared_type, "bytes": len(data)})

    try:
        pages = read_pdf(data)
    except Exception as exc:  # noqa: BLE001
        append(conn, event_type="EXTRACTION_FAILED", actor=EXTRACT,
               correlation_id=correlation, causation_id=document["event_id"],
               tender_id=tender_id, bidder_id=bidder_id,
               payload={"path": "document", "reason_code": "EXTRACTION_FAILED",
                        "detail": f"could not read as PDF: {exc}"})
        return {"document_sha256": digest, "pages": 0, "extracted": [],
                "rejected": [], "unreadable_pages": [],
                "error": f"could not read as PDF: {exc}"}

    # Deferred: extract/financials.py imports Candidate from this module,
    # so importing it at module load time here would be circular. By the
    # time ingest_document() actually runs, this module has finished
    # initializing (Candidate included), so a local import resolves fine.
    from .financials import find_financial_fields

    candidates, unreadable = find_candidates(pages)
    # Label/value fields (name, date of birth, issue/expiry dates, claimed
    # business name) are a different lookup method (layout, not grammar) but
    # the same Candidate shape, so they join the same list and flow through
    # the one emission loop below unchanged. find_financial_fields is a
    # third technique again (table extraction, needs the raw bytes rather
    # than the already-parsed `pages`) but produces the same Candidate
    # shape too, so it joins here rather than getting a second loop.
    candidates = (candidates + find_pan_holder_fields(pages) + find_document_dates(pages)
                  + find_gst_claimed_names(pages) + find_financial_fields(data))

    extracted, rejected = [], []
    for candidate in candidates:
        path = FIELD_PATHS[candidate.field]
        if candidate.valid:
            append(conn, event_type="FIELD_EXTRACTED", actor=EXTRACT,
                   correlation_id=correlation, causation_id=document["event_id"],
                   tender_id=tender_id, bidder_id=bidder_id,
                   payload={"path": path, "value": candidate.value,
                            "page": candidate.page, "region": list(candidate.region),
                            # Deterministic location and a passed structural
                            # check. Not a model's self-reported confidence.
                            "confidence": 1.0,
                            "basis": "text-layer match + structural validation",
                            "detail": candidate.detail,
                            "code_version": EXTRACT.id})
            extracted.append({"path": path, "value": candidate.value,
                              "page": candidate.page,
                              "region": list(candidate.region)})
        else:
            # A structurally invalid identifier is an extraction problem, not a
            # question to put to an authority. Recording it as a fact keeps the
            # officer informed without ever asserting the value.
            append(conn, event_type="EXTRACTION_FAILED", actor=EXTRACT,
                   correlation_id=correlation, causation_id=document["event_id"],
                   tender_id=tender_id, bidder_id=bidder_id,
                   payload={"path": path, "reason_code": "EXTRACTION_FAILED",
                            "candidate": candidate.value, "page": candidate.page,
                            "region": list(candidate.region),
                            "detail": candidate.detail})
            rejected.append({"path": path, "candidate": candidate.value,
                             "detail": candidate.detail})

    for page in unreadable:
        append(conn, event_type="EXTRACTION_FAILED", actor=EXTRACT,
               correlation_id=correlation, causation_id=document["event_id"],
               tender_id=tender_id, bidder_id=bidder_id,
               payload={"path": f"page.{page['page']}",
                        "reason_code": "EXTRACTION_FAILED",
                        "stage": page["stage"], "detail": page["reason"]})

    conflict = _identifier_cross_check(conn, bidder_id, extracted)
    if conflict:
        append(conn, event_type="ENTITY_RESOLVED", actor=EXTRACT,
               correlation_id=correlation, causation_id=document["event_id"],
               tender_id=tender_id, bidder_id=bidder_id, payload=conflict)

    return {"document_sha256": digest, "storage_ref": storage_ref,
            "pages": len(pages), "extracted": extracted, "rejected": rejected,
            "unreadable_pages": unreadable,
            "identifier_cross_check": conflict}


def _prior_evidence(conn, bidder_id: str, path: str) -> str | None:
    """A fact resolved from a bidder's *previous* upload, read directly from
    the evidence projection -- not rebuild_evidence(), which needs a Registry
    that ingest_document() is never given (app.py builds one, but calling it
    from here would mean this function reaching into how app.py wires
    things). By the time ingest_document() runs, proj_evidence already
    reflects every prior upload; app.py only rebuilds it, folding in *this*
    upload's own fields, after ingest_document() returns -- so a direct read
    here is exactly "prior uploads only", which is exactly the complement
    _identifier_cross_check needs."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT value FROM proj_evidence
               WHERE bidder_id=%s AND path=%s AND resolved=true""",
            (bidder_id, path))
        row = cur.fetchone()
        return row[0] if row else None


def _identifier_cross_check(
    conn, bidder_id: str, extracted: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Characters 3-12 of a GSTIN are the holder's PAN.

    If the PAN read from the PAN card does not equal the PAN embedded in the
    GSTIN, the two documents are not about the same legal entity -- and no
    amount of name similarity changes that. Identifier match beats semantic
    similarity, always.

    A bidder's PAN card and GST certificate are realistically two separate
    uploads, so `extracted` -- this call's own fields -- alone would never
    have both at once. When one of the two is missing from this upload,
    fall back to the bidder's accumulated evidence from prior uploads
    (_prior_evidence) before giving up. The two already-present-in-extracted
    case (the original, single-document check) needs no database lookup at
    all and behaves exactly as before.
    """
    by_path = {e["path"]: e["value"] for e in extracted}
    gstin = by_path.get("bidder.gst.gstin")
    pan = by_path.get("bidder.pan.pan_number")
    if not gstin or not pan:
        gstin = gstin or _prior_evidence(conn, bidder_id, "bidder.gst.gstin")
        pan = pan or _prior_evidence(conn, bidder_id, "bidder.pan.pan_number")
    if not (gstin and pan):
        return None
    embedded = pan_from_gstin(gstin)
    agrees = embedded == pan
    return {"basis": "PAN embedded in GSTIN", "gstin": gstin, "pan": pan,
            "embedded_pan": embedded, "agrees": agrees,
            "outcome": "LINKED" if agrees else "IDENTIFIER_CONFLICT"}
