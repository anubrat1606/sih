"""Verifies a Google Sign-In ID token. This is real, working verification,
not a placeholder -- google-auth (the library that does the actual
signature/issuer/audience/expiry checking against Google's own rotating
public keys) is already an installed dependency of google-genai, so nothing
new needs to be added to requirements.txt to make it correct.

The frontend flow this expects: the bidder portal loads Google Identity
Services' JS SDK client-side, the bidder picks an account, and the SDK hands
the frontend a signed ID token -- a JWT Google itself issued, not a
credential this backend has to broker. The frontend POSTs that token here;
this file's only job is proving it's genuinely from Google, genuinely for
this app (the audience check), and not expired, then reading the verified
email/name/sub out of it. There is no server-side OAuth "exchange a code"
flow to implement -- ID-token verification is the correct, simpler shape
for "sign in with Google" (as opposed to "let this app act on my Google
account"), which is all a bidder-identity sign-in needs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str
    email_verified: bool
    name: str


class GoogleSignIn:
    def __init__(self, client_id: str):
        self._client_id = client_id
        # google-auth caches Google's public keys internally and re-fetches
        # them over HTTPS as they rotate -- this is the one network call
        # this module ever makes, and it's to Google, not a credential of
        # ours being sent anywhere.
        self._request = google_requests.Request()

    def verify(self, id_token_str: str) -> GoogleIdentity | None:
        """None for any failure -- forged signature, wrong audience,
        expired token, or an unverified Google-side email. Every one of
        those is "this isn't a trustworthy Google identity", not a
        distinction worth leaking to the caller."""
        try:
            claims = google_id_token.verify_oauth2_token(
                id_token_str, self._request, audience=self._client_id)
        except ValueError:
            return None
        if not claims.get("email_verified"):
            return None
        return GoogleIdentity(
            sub=claims["sub"], email=claims["email"],
            email_verified=True, name=claims.get("name") or claims["email"],
        )


class UnconfiguredGoogleSignIn:
    """No SATYAPRAMANA_GOOGLE_CLIENT_ID -- app.py's /bidders/auth/google
    answers 503, the same honest pattern as /auth/login when
    SATYAPRAMANA_JWT_SECRET is unset, rather than accepting a token this
    deployment has no audience to check it against."""

    def verify(self, id_token_str: str) -> GoogleIdentity | None:
        raise RuntimeError("GoogleSignIn is not configured -- call build_from_env() "
                            "and check for UnconfiguredGoogleSignIn before calling verify()")


def build_from_env():
    client_id = os.environ.get("SATYAPRAMANA_GOOGLE_CLIENT_ID")
    if not client_id:
        return UnconfiguredGoogleSignIn()
    return GoogleSignIn(client_id=client_id)
