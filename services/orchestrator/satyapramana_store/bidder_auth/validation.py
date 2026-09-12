"""Input validation for bidder self-service accounts -- deliberately the
same rules the frontend already enforces (frontend/src/bidder/components/
FormControls.jsx), re-applied here because a browser-side check is a UX
convenience, not a security boundary; anyone can POST directly to these
endpoints without ever loading the form.
"""
from __future__ import annotations

import re

#: Pragmatic RFC-5322-ish check, same one the frontend uses -- rejects the
#: obviously malformed (no @, no domain, spaces) without trying to be a full
#: grammar no one needs.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")

#: Indian mobile numbers: 10 digits, first digit 6-9, optionally prefixed
#: with +91 / 91 / 0. Applied after stripping spaces and dashes, so a
#: visitor typing "+91 98765 43210" or "98765-43210" (both completely
#: ordinary ways to type a phone number) normalises the same as
#: "9876543210" -- the space/dash isn't only tolerated right after the "91"
#: prefix.
_MOBILE_RE = re.compile(r"^(?:\+?91|0)?([6-9]\d{9})$")


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value.strip()))


def normalize_indian_mobile(value: str) -> str | None:
    """Returns the bare 10-digit form, or None if `value` isn't a valid
    Indian mobile number in any of the accepted input shapes."""
    cleaned = re.sub(r"[\s-]", "", value.strip())
    m = _MOBILE_RE.match(cleaned)
    return m.group(1) if m else None


def is_valid_indian_mobile(value: str) -> bool:
    return normalize_indian_mobile(value) is not None


def password_issues(password: str) -> list[str]:
    """Every rule the password fails, in plain language -- empty means the
    password is acceptable. A list, not a bool, so the signup endpoint can
    return exactly what's still missing instead of a bare 400."""
    issues = []
    if len(password) < 8:
        issues.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        issues.append("one uppercase letter")
    if not re.search(r"[a-z]", password):
        issues.append("one lowercase letter")
    if not re.search(r"[0-9]", password):
        issues.append("one number")
    if not re.search(r"[^A-Za-z0-9]", password):
        issues.append("one special character")
    return issues
