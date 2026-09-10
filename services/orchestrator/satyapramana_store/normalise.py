"""Attribute normalisation for shared-attribute detection.

Two bidders whose phone numbers are written '+91 98765 43210' and '9876543210'
share a phone number. Comparing the strings as typed misses that, and it is
precisely the case worth catching -- people concealing a link rarely format
their fields identically.

The /services/collusion implementation this supersedes compared trimmed,
lowercased strings exactly, so every one of those pairs slipped through.

On the false-positive risk: a shared attribute is a signal for an officer to
review, never a disqualification -- the system does not disqualify anyone. A
false positive costs an officer one look; a false negative costs a missed
cartel. That asymmetry justifies normalising aggressively here, and it is why
the resulting flag is presented as a link to examine rather than a finding of
fact.
"""
from __future__ import annotations

import hashlib
import re

_NON_DIGIT = re.compile(r"\D+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_PUNCT = re.compile(r"[.,/\\#!$%^&*;:{}=\-_`~()'\"]+")


def _collapse(value: str) -> str:
    return " ".join(value.strip().lower().split())


def phone(value: str) -> str:
    """Digits only. Numbers longer than ten digits keep their last ten, which
    strips a +91 or leading-0 prefix without needing to know the country."""
    digits = _NON_DIGIT.sub("", value)
    return digits[-10:] if len(digits) > 10 else digits


def bank_account(value: str) -> str:
    """Alphanumerics only, lowercased -- account numbers are written with
    spaces, hyphens and inconsistent case."""
    return _NON_ALNUM.sub("", value.lower())


def director_name(value: str) -> str:
    """Whitespace collapsed, punctuation dropped, lowercased. Honorifics and
    ordering are deliberately NOT touched: 'Kumar, Ramesh' and 'Ramesh Kumar'
    are left distinct here, because name-based identity belongs to the RESOLVE
    stage with its own evidence, not to a hash comparison."""
    return _collapse(_PUNCT.sub(" ", value.lower()))


def address(value: str) -> str:
    return _collapse(_PUNCT.sub(" ", value.lower()))


NORMALISERS = {
    "phone": phone,
    "bank_account": bank_account,
    "director_name": director_name,
    "address": address,
}


def normalise(attribute: str, value: str) -> str:
    return NORMALISERS[attribute](str(value))


def fingerprint(attribute: str, value: str) -> str:
    """The hash that enters the event log. The value itself never does."""
    return hashlib.sha256(
        f"{attribute}:{normalise(attribute, value)}".encode()
    ).hexdigest()
