"""Session tokens -- a signed JWT, HS256, carrying only what a request needs
to identify who's asking and at what role: `sub` (username), `role`,
`iat`/`exp`. Nothing evidentiary lives in a token; the users table (and, for
the actions that matter, the event log's own `actor` field) is the source
of truth, the token is only a signed claim about who's currently logged in.

`encode_claims`/`decode_claims` are the shared low-level primitive:
bidder_auth/tokens.py issues its own, differently-shaped JWTs (a bidder
account id, not an officer username; no `role`) through the same two
functions, rather than a second hand-rolled `jwt.encode` call elsewhere.
Every bidder claim set also carries `"typ": "bidder"`, which is what lets
current_user() below refuse a bidder's token outright instead of relying on
a bidder id merely failing to match any row in the officer `users` table.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from .models import User

ALGORITHM = "HS256"
#: A working shift, roughly -- long enough an officer isn't re-logging-in
#: every few minutes, short enough a leaked token doesn't stay valid for
#: days.
DEFAULT_TTL = timedelta(hours=12)


def encode_claims(claims: dict, secret: str, *, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({**claims, "iat": now, "exp": now + ttl}, secret, algorithm=ALGORITHM)


def decode_claims(token: str, secret: str) -> dict:
    """Raises jwt.PyJWTError (or a subclass -- ExpiredSignatureError,
    InvalidSignatureError, etc.) on any failure. Every caller (app.py's
    current_user and current_bidder dependencies) translates that into a
    401, never a fabricated "logged in as nobody" fallback."""
    return jwt.decode(token, secret, algorithms=[ALGORITHM])


def issue_token(user: User, secret: str, *, ttl: timedelta = DEFAULT_TTL) -> str:
    return encode_claims({"sub": user.username, "role": user.role.value}, secret, ttl=ttl)


def decode_token(token: str, secret: str) -> dict:
    return decode_claims(token, secret)
