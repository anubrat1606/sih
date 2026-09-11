"""Session tokens -- a signed JWT, HS256, carrying only what a request needs
to identify who's asking and at what role: `sub` (username), `role`,
`iat`/`exp`. Nothing evidentiary lives in a token; the users table (and, for
the actions that matter, the event log's own `actor` field) is the source
of truth, the token is only a signed claim about who's currently logged in.
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


def issue_token(user: User, secret: str, *, ttl: timedelta = DEFAULT_TTL) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": user.username, "role": user.role.value, "iat": now, "exp": now + ttl}
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decode_token(token: str, secret: str) -> dict:
    """Raises jwt.PyJWTError (or a subclass -- ExpiredSignatureError,
    InvalidSignatureError, etc.) on any failure. The caller (app.py's
    current_user dependency) translates that into a 401, never a fabricated
    "logged in as nobody" fallback."""
    return jwt.decode(token, secret, algorithms=[ALGORITHM])
