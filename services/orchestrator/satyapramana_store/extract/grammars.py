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

#: A PAN card prints the date of birth as DD/MM/YYYY. Sandbox.co.in's PAN
#: verification endpoint requires exactly this format (adapters/sandbox_co_in.py),
#: so this is the target grammar, not a generic date parser.
PAN_DOB_RE = re.compile(r"[0-9]{2}/[0-9]{2}/[0-9]{4}")

#: The printed holder name on a PAN card: letters, spaces, and the
#: punctuation an Indian legal name actually uses (periods for initials,
#: apostrophes, hyphens). Deliberately does not accept digits -- a "next
#: line" containing a digit is not a name, it is something else read from the
#: wrong line.
PAN_HOLDER_NAME_RE = re.compile(r"[A-Z][A-Z .'\-]{1,98}[A-Z.]")

#: A CIN is 21 characters: listing status (L or U), a 5-digit industry code, a
#: 2-letter Registrar-of-Companies state code, the 4-digit year of
#: incorporation, a 3-letter ownership class, and a 6-digit registration number.
#: There is no check digit -- validation is structural, on the four segments
#: that have a closed set of legal values.
CIN_RE = re.compile(r"[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}")

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

#: The 2-letter Registrar-of-Companies state code embedded in a CIN (characters
#: 7-8). Transcribed from the MCA's published scheme; like GST_STATE_CODES this
#: must be checked against the current MCA notification before the demo, since
#: codes shift as states are reorganised. An unrecognised code is treated as a
#: reason to look, not as proof the number is fabricated.
CIN_ROC_STATE_CODES = {
    "AP", "AR", "AS", "BR", "CH", "CG", "CT", "DL", "GA", "GJ", "HP", "HR",
    "JH", "JK", "KA", "KL", "MH", "ML", "MN", "MP", "MZ", "NL", "OR", "PB",
    "PY", "RJ", "SK", "TG", "TN", "TR", "UK", "UP", "UT", "WB",
    "AN", "DN", "DD", "LD",
}

#: The 3-letter ownership class embedded in a CIN (characters 13-15). This set
#: is closed and published by the MCA.
CIN_OWNERSHIP_CLASSES = {
    "PLC": "Public Limited Company",
    "PTC": "Private Limited Company",
    "OPC": "One Person Company",
    "SGC": "State Government Company",
    "GOI": "Union Government Company",
    "NPL": "Not-for-Profit (Section 8) Company",
    "GAP": "General Association Public",
    "GAT": "General Association Private",
    "FLC": "Financial Lease Company (Public)",
    "FTC": "Subsidiary of a Foreign Company, incorporated as Private",
    "ULL": "Public Company with Unlimited Liability",
    "ULT": "Private Company with Unlimited Liability",
}

#: The plausible span for a CIN's incorporation year. The lower bound predates
#: the Companies Act (1857 is roughly the first Indian joint-stock companies);
#: the upper bound is a fixed sentinel, deliberately not date.today() -- a
#: structural validator must return the same answer on replay.
CIN_YEAR_MIN, CIN_YEAR_MAX = 1857, 2100

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


def validate_pan_date_of_birth(value: str) -> Check:
    if not PAN_DOB_RE.fullmatch(value):
        return Check(False, "does not match DD/MM/YYYY")
    from datetime import date
    day, month, year = (int(part) for part in value.split("/"))
    try:
        date(year, month, day)
    except ValueError:
        return Check(False, f"{value} is not a real calendar date")
    return Check(True, f"parses as {value} (DD/MM/YYYY)")


def validate_pan_holder_name(value: str) -> Check:
    if not PAN_HOLDER_NAME_RE.fullmatch(value):
        return Check(
            False,
            "does not look like a printed name (letters, spaces, '.', \"'\", "
            "'-' only, no digits)")
    return Check(True, "structurally plausible printed name")


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


def validate_cin(value: str) -> Check:
    if not CIN_RE.fullmatch(value):
        return Check(False, "does not match the CIN grammar")
    roc = value[6:8]
    if roc not in CIN_ROC_STATE_CODES:
        return Check(False, f"'{roc}' is not a Registrar-of-Companies state code in use")
    year = int(value[8:12])
    if not CIN_YEAR_MIN <= year <= CIN_YEAR_MAX:
        return Check(
            False,
            f"incorporation year {year} is outside {CIN_YEAR_MIN}-{CIN_YEAR_MAX}")
    ownership = value[12:15]
    if ownership not in CIN_OWNERSHIP_CLASSES:
        return Check(False, f"'{ownership}' is not a known CIN ownership class")
    return Check(
        True,
        f"state {roc}, incorporated {year}, "
        f"{ownership} ({CIN_OWNERSHIP_CLASSES[ownership]})")


VALIDATORS = {
    "pan_number": validate_pan,
    "gstin": validate_gstin,
    "udyam_number": validate_udyam,
    "cin": validate_cin,
}

PATTERNS = {
    "pan_number": PAN_RE,
    "gstin": GSTIN_RE,
    "udyam_number": UDYAM_RE,
    "cin": CIN_RE,
}

#: A GSTIN contains a PAN, so scanning for PAN first would match inside every
#: GSTIN. Longest-first ordering avoids reporting the same characters twice; a
#: CIN is longer still (21 characters) and so leads.
SCAN_ORDER = ("cin", "gstin", "udyam_number", "pan_number")
