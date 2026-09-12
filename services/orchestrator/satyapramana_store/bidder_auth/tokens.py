"""Bidder session tokens, plus the one-time secrets used by the email
verification, mobile OTP and password reset flows.

Session tokens reuse auth.tokens' encode_claims/decode_claims (the same
signing primitive the officer side uses) rather than a second hand-rolled
jwt.encode call -- see that module's docstring. Every bidder claim set
carries "typ": "bidder", which is what lets app.py's officer-side
current_user() refuse a bidder's token outright and current_bidder() refuse
an officer's.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from ..auth.tokens import decode_claims, encode_claims

#: A week, not a shift -- a bidder isn't re-logging-in on a shared
#: workstation every day the way an officer might be; friction here just
#: means an abandoned signup, which this project has no reason to invite.
DEFAULT_TTL = timedelta(days=7)

EMAIL_VERIFICATION_TTL = timedelta(hours=24)
MOBILE_OTP_TTL = timedelta(minutes=10)
MOBILE_OTP_MAX_ATTEMPTS = 5
PASSWORD_RESET_TTL = timedelta(hours=1)


def issue_bidder_token(bidder_id: int, secret: str, *, ttl: timedelta = DEFAULT_TTL) -> str:
    return encode_claims({"sub": str(bidder_id), "typ": "bidder"}, secret, ttl=ttl)


def decode_bidder_token(token: str, secret: str) -> dict:
    """Raises jwt.PyJWTError on any failure, same as decode_claims -- the
    caller (app.py's current_bidder dependency) turns that into a 401."""
    return decode_claims(token, secret)


# --- one-time secrets (email verification links, password reset links) -----
#
# High-entropy, generated with `secrets` (never `random`), stored as a
# SHA-256 hash so a leaked database backup can't be replayed as a valid
# link -- the same reasoning as never storing a password in plain text, but
# a fast hash is the right tool here: these tokens are ~192 bits of real
# entropy, not a low-entropy secret that needs a slow KDF to resist offline
# brute force the way a password does.

def generate_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_opaque_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# --- mobile OTPs -------------------------------------------------------------
#
# A 6-digit code, generated with `secrets.randbelow` (never `random` or a
# hardcoded/test value), stored hashed the same way. Its real protection
# against brute force is bidder_auth/store.py's attempt counter and short
# expiry, not the hash -- a 6-digit space is small enough that hashing
# algorithm choice doesn't matter once those are in place.

def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()
