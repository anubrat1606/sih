"""Statutory identifier grammars and their structural checks.

These are the confirmed regexes from services/extraction, promoted to their
correct role. They are no longer extractors: they are NORMALIZE-stage
validators that reject whatever a candidate stage proposes if it is malformed.

Structural validation matters more than it looks. An OCR misread of one
character in a GSTIN produces a string that still matches the regex, and the
system would then ask an authority about a business that does not exist and
record the resulting NOT_FOUND. Checking the structure first turns that into an
extraction problem, which is what it actually is.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PAN_RE = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]{1}")
GSTIN_RE = re.compile(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}")
UDYAM_RE = re.compile(r"UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}")

#: EPFO establishment codes have no confirmed single format, so there is no
#: regex here and epfo_number is never populated. Adding one on a guess would
#: manufacture identifiers, which is the failure this project exists to avoid.
EPFO_RE = None

#: The fourth character of a PAN is the holder type.
PAN_HOLDER_TYPES = {
    "A": "Association of Persons", "B": "Body of Individuals",
    "C": "Company", "F": "Firm", "G": "Government",
    "H": "Hindu Undivided Family", "J": "Artificial Juridical Person",
    "L": "Local Authority", "P": "Individual", "T": "Trust",
}

#: GST state codes in use, plus 97 (other territory) and 99 (centre
#: jurisdiction). Verify this list against the current GST notification before
#: the demo -- state codes are added over time.
GST_STATE_CODES = {f"{n:02d}" for n in range(1, 39)} | {"97", "99"}

_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True)
class Check:
    ok: bool
    detail: str = ""


def gstin_check_digit(first14: str) -> str:
    """The published GSTIN check-digit algorithm: base-36 values, alternating
    weights of 1 and 2, summing quotient and remainder of each product.

    Implemented from the specification. It is internally consistent and is
    property-tested, but it has NOT been checked against a real GSTIN -- doing
    that needs one real registration number, which is on the list of things
    still needed from the team. Until then treat a check-digit failure as a
    reason to look, not as proof.
    """
    if len(first14) != 14:
        raise ValueError("GSTIN check digit is computed over the first 14 characters")
    total = 0
    for i, ch in enumerate(first14):
        value = _B36.index(ch)
        product = value * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _B36[(36 - total % 36) % 36]


def validate_pan(value: str) -> Check:
    if not PAN_RE.fullmatch(value):
        return Check(False, "does not match the PAN grammar")
    holder = value[3]
    if holder not in PAN_HOLDER_TYPES:
        return Check(False, f"'{holder}' is not a known PAN holder type")
    return Check(True, f"holder type {holder} ({PAN_HOLDER_TYPES[holder]})")


def validate_gstin(value: str) -> Check:
    if not GSTIN_RE.fullmatch(value):
        return Check(False, "does not match the GSTIN grammar")
    if value[:2] not in GST_STATE_CODES:
        return Check(False, f"'{value[:2]}' is not a GST state code in use")
    embedded = pan_from_gstin(value)
    pan = validate_pan(embedded)
    if not pan.ok:
        return Check(False, f"embedded PAN {embedded} is invalid: {pan.detail}")
    expected = gstin_check_digit(value[:14])
    if value[14] != expected:
        return Check(False, f"check digit is {value[14]}, expected {expected}")
    return Check(True, f"state {value[:2]}, embedded PAN {embedded}")


def pan_from_gstin(gstin: str) -> str:
    """Characters 3-12 of a GSTIN are the holder's PAN.

    This is the cross-check the charter means by "identifier match beats
    semantic similarity, always": if the PAN on the bidder's PAN card does not
    equal the PAN embedded in their GSTIN, the two documents are not about the
    same entity, and no amount of name similarity changes that.
    """
    return gstin[2:12]


def validate_udyam(value: str) -> Check:
    if not UDYAM_RE.fullmatch(value):
        return Check(False, "does not match the Udyam grammar")
    return Check(True, f"state {value[6:8]}")


VALIDATORS = {
    "pan_number": validate_pan,
    "gstin": validate_gstin,
    "udyam_number": validate_udyam,
}

PATTERNS = {
    "pan_number": PAN_RE,
    "gstin": GSTIN_RE,
    "udyam_number": UDYAM_RE,
}

#: A GSTIN contains a PAN, so scanning for PAN first would match inside every
#: GSTIN. Longest-first ordering avoids reporting the same characters twice.
SCAN_ORDER = ("gstin", "udyam_number", "pan_number")
