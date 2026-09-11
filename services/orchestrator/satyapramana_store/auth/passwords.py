"""Password hashing -- stdlib only, no new dependency. `hashlib.scrypt`
(RFC 7914) is a real, production-grade KDF, not a placeholder; using it
instead of pulling in bcrypt/argon2 keeps this module dependency-free the
same way the rest of this project avoids adding a library where a few dozen
correct lines already do the job.

The stored format is self-describing (`scrypt$n$r$p$salt$hash`) so the cost
parameters can be tuned later for a faster or slower deployment target
without invalidating passwords hashed under the old parameters.
"""
from __future__ import annotations

import hashlib
import hmac
import os

#: Cost parameters tuned for an interactive login (roughly 100-200ms on
#: ordinary hardware) -- expensive enough to resist offline brute force,
#: cheap enough that a real officer logging in doesn't notice the wait.
_N, _R, _P = 2**14, 8, 1
_DKLEN = 64
_ALGO = "scrypt"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"{_ALGO}${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Never raises -- a malformed or foreign-format stored hash is simply a
    failed login, not a crash. Constant-time comparison against timing
    attacks via hmac.compare_digest."""
    try:
        algo, n, r, p, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        n, r, p = int(n), int(r), int(p)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected))
    return hmac.compare_digest(dk, expected)
