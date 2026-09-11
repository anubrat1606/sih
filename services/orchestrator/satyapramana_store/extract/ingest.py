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
from pathlib import Path
from typing import Any

from .grammars import (
    PATTERNS, SCAN_ORDER, VALIDATORS, pan_from_gstin, validate_pan_date_of_birth,
    validate_pan_holder_name,
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

#: If the line under a label is itself one of these known label phrases, the
#: field is blank on the card -- reading it anyway would assert a value the
#: document does not actually state.
_KNOWN_LABEL_LINES = {" ".join(words) for words in PAN_HOLDER_FIELDS} | {
    "PERMANENT ACCOUNT NUMBER", "FATHER'S NAME", "FATHERS NAME", "SIGNATURE",
}


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
    for page in pages:
        if not page.has_text_layer:
            continue  # find_candidates already records this page as unreadable
        grouped = lines(page)
        for label_words, (field, validate) in PAN_HOLDER_FIELDS.items():
            idx = _label_line_index(grouped, label_words)
            if idx is None:
                continue
            if idx + 1 >= len(grouped):
                candidates.append(Candidate(
                    field, "", page.number, _line_region(grouped[idx]), False,
                    "the label is the last line on the page; no value line follows it"))
                continue
            value_line = grouped[idx + 1]
            text = _line_text(value_line)
            region = _line_region(value_line)
            if not text:
                candidates.append(Candidate(
                    field, text, page.number, region, False,
                    "the line under the label is blank"))
                continue
            if text.rstrip(":").upper() in _KNOWN_LABEL_LINES:
                candidates.append(Candidate(
                    field, text, page.number, region, False,
                    "the line under the label is itself a printed label -- "
                    "the field is blank"))
                continue
            check = validate(text)
            candidates.append(Candidate(field, text, page.number, region,
                                        check.ok, check.detail))
    return candidates


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

    candidates, unreadable = find_candidates(pages)
    # Label/value fields (name, date of birth) are a different lookup method
    # (layout, not grammar) but the same Candidate shape, so they join the
    # same list and flow through the one emission loop below unchanged.
    candidates = candidates + find_pan_holder_fields(pages)

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
