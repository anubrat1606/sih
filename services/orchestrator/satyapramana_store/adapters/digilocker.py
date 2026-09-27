"""Live DigiLocker integration via Sandbox.co.in -- structurally different
from the other four capabilities on this account: a bidder-consent redirect
flow (adapters/base.py's BIDDER_CONSENT basis exists for exactly this), not
a single server-to-server lookup. It does not implement VerificationAdapter
.verify() and is not registered into the generic Registry/
`/bidders/{id}/verify` loop those four use -- app.py wires these three
functions into their own dedicated endpoints, emitting the same
VERIFICATION_REQUESTED/OBSERVED/FAILED event vocabulary by hand so the
result still flows through the existing evidence/verdict pipeline with no
new machinery in evidence.py or projections.py.

Round 10, PS26100 point 8. Scoped to one document type (aadhaar) this
round -- pan and driving_license use the identical three calls with a
different doc_type string; real future scope, not built here.

Contracts read from Sandbox's own OpenAPI spec (developer.sandbox.co.in),
not guessed:

  Initiate  POST /kyc/digilocker/sessions/init
            body: {"@entity": "in.co.sandbox.kyc.digilocker.session.request",
                    flow, redirect_url, doc_types}
            -> {"data": {"authorization_url", "session_id"}}

  Status    GET /kyc/digilocker/sessions/{session_id}/status
            -> {"data": {"status": created|succeeded|failed|expired,
                          "documents_consented": [...] (present only when
                          status is "succeeded")}}

  Fetch     GET /kyc/digilocker/sessions/{session_id}/documents/{doc_type}
            -> {"data": {"files": [{"url", "size", "metadata": {
                          "ContentType", "issuer_id", "issuer",
                          "LastModified", "description"}}]}}
            -- `url` is a pre-signed S3 link to the raw document (XML/PDF,
            DigiLocker's own format), valid roughly an hour. This module
            archives the metadata response, not the file bytes behind that
            link -- downloading, storing, and OCR'ing the actual document
            is real future scope, not built this round.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from satyapramana.verdicts import Channel, Tier

from .base import (
    Basis, Capability, CapabilityManifest, Failure, FailureCode, LawfulBasis,
    VerificationRequest,
)
from .sandbox_co_in import LIVE_BASE_URL, TEST_BASE_URL, SandboxSession, _http_failure, _record

DOC_TYPES = ("aadhaar", "pan", "driving_license")
_LIVE_STATUSES = ("created", "succeeded", "failed", "expired")

#: One shared Capability object -- the placeholder adapter's manifest below
#: and app.py's dedicated endpoints both reference this exact instance, so
#: the registry/coverage-report view and the real consent-flow endpoints
#: can never silently drift into describing two different capabilities.
DIGILOCKER_CAPABILITY = Capability(
    capability_id="DIGILOCKER_DOCUMENT",
    provides=("bidder.digilocker.aadhaar_verified", "bidder.digilocker.aadhaar_issuer"),
    tier=Tier.A,
    channel=Channel.AGGREGATOR,
    as_of_supported=False,
    freshness_days=90,
    not_found_is_negative=False,
    lawful_bases=(Basis.BIDDER_CONSENT,),
    status="LIVE",
)


class DigilockerPlaceholderAdapter:
    """Registered into the Registry purely so DIGILOCKER_DOCUMENT shows up
    honestly in the coverage report and requirement_types.py's producible-
    paths computation, the same mechanism every other capability uses --
    without pretending the real consent flow fits the generic single-call
    verify() loop it was never built for. If something ever calls verify()
    on this anyway (a stale integration, a test that assumes every
    registered capability is loop-callable), it fails loudly and says
    exactly where the real flow lives, instead of silently doing nothing
    or, worse, guessing at a result.
    """

    def __init__(self):
        self.manifest = CapabilityManifest(
            adapter_id="digilocker", adapter_version="1.0.0",
            authority="DigiLocker (Ministry of Electronics and Information Technology)",
            intermediary="Sandbox.co.in", identifier_queryable=False,
            capabilities=(DIGILOCKER_CAPABILITY,),
        )

    def verify(self, request: VerificationRequest, conn=None) -> Failure:
        return Failure(
            FailureCode.NOT_CAPABLE,
            "DigiLocker requires the dedicated bidder-consent redirect flow "
            "-- POST /bidders/{bidder_id}/digilocker/session, not the "
            "generic verification loop.",
        )


def _digilocker_status_failure(status: int, body_text: str) -> Failure | None:
    """DigiLocker-specific -- distinct from sandbox_co_in.py's own
    _status_failure because this product documents 400/404/523 with real,
    specific meanings none of the other three capabilities use."""
    if status in (401, 403):
        return Failure(FailureCode.UNAUTHORIZED, f"Sandbox.co.in rejected the credentials (HTTP {status})")
    if status == 429:
        return Failure(FailureCode.RATE_LIMITED, "Sandbox.co.in rate-limited this request")
    if status == 400:
        return Failure(FailureCode.MALFORMED, f"Sandbox.co.in rejected the request as malformed: {body_text}")
    if status == 404:
        return Failure(FailureCode.NOT_FOUND, body_text or "DigiLocker has no record of this document")
    if status == 521:
        return Failure(FailureCode.NOT_FOUND, body_text or "no DigiLocker session found for this session_id")
    if status == 523:
        # Documented as two distinct meanings sharing one status code:
        # fetch called before consent completed ("Invalid session status:
        # created"), or the session's DigiLocker access token expired.
        # Both recover the same way -- check status again, or start a new
        # session -- so both map to UNAVAILABLE (retry-shaped) rather than
        # guessing which one happened from the code alone.
        return Failure(FailureCode.UNAVAILABLE, body_text or "DigiLocker session is not currently usable")
    if status >= 500:
        return Failure(FailureCode.UNAVAILABLE, f"Sandbox.co.in returned HTTP {status}: {body_text}")
    if status != 200:
        return Failure(FailureCode.UNAVAILABLE, f"unexpected HTTP {status}: {body_text}")
    return None


@dataclass(frozen=True)
class InitiateResult:
    authorization_url: str
    session_id: str
    raw_response_ref: str


@dataclass(frozen=True)
class SessionStatus:
    status: str  # created | succeeded | failed | expired
    documents_consented: tuple[str, ...]
    raw_response_ref: str


@dataclass(frozen=True)
class FetchedDocument:
    files: tuple[dict[str, Any], ...]
    raw_response_ref: str


def initiate_session(
    session: SandboxSession, *, redirect_url: str, doc_types: tuple[str, ...],
    lawful_basis: LawfulBasis, flow: str = "signin", conn=None,
) -> InitiateResult | Failure:
    if not redirect_url.startswith("https://"):
        return Failure(FailureCode.MALFORMED, "redirect_url must be a real https:// URL, not guessed or omitted")
    bad = [d for d in doc_types if d not in DOC_TYPES]
    if bad:
        return Failure(FailureCode.MALFORMED, f"unsupported doc_types {bad}; DigiLocker only offers {DOC_TYPES}")

    body = {
        "@entity": "in.co.sandbox.kyc.digilocker.session.request",
        "flow": flow, "redirect_url": redirect_url, "doc_types": list(doc_types),
    }
    observed_at = datetime.now(timezone.utc)
    url = f"{session.base_url}/kyc/digilocker/sessions/init"

    try:
        resp = session.post("/kyc/digilocker/sessions/init", body)
    except httpx.HTTPError as exc:
        return _http_failure(exc)

    ref = _record(
        conn, adapter_id="digilocker", adapter_version="1.0.0",
        capability_id="DIGILOCKER_DOCUMENT", observed_at=observed_at, url=url,
        request_headers=dict(resp.request.headers), request_body=json.dumps(body),
        response_status=resp.status_code, response_headers=dict(resp.headers),
        response_body=resp.text, lawful_basis=lawful_basis, method="POST",
    )
    failure = _digilocker_status_failure(resp.status_code, resp.text)
    if failure:
        return Failure(failure.code, failure.detail, raw_response_ref=ref)

    data = resp.json().get("data", {})
    if not data.get("authorization_url") or not data.get("session_id"):
        return Failure(
            FailureCode.AMBIGUOUS,
            "DigiLocker session response carried neither an authorization_url "
            "nor a session_id", raw_response_ref=ref,
        )
    return InitiateResult(data["authorization_url"], data["session_id"], ref)


def check_session_status(
    session: SandboxSession, session_id: str, *, lawful_basis: LawfulBasis, conn=None,
) -> SessionStatus | Failure:
    observed_at = datetime.now(timezone.utc)
    path = f"/kyc/digilocker/sessions/{session_id}/status"
    url = f"{session.base_url}{path}"

    try:
        resp = session.get(path)
    except httpx.HTTPError as exc:
        return _http_failure(exc)

    ref = _record(
        conn, adapter_id="digilocker", adapter_version="1.0.0",
        capability_id="DIGILOCKER_DOCUMENT", observed_at=observed_at, url=url,
        request_headers=dict(resp.request.headers), request_body="",
        response_status=resp.status_code, response_headers=dict(resp.headers),
        response_body=resp.text, lawful_basis=lawful_basis, method="GET",
    )
    failure = _digilocker_status_failure(resp.status_code, resp.text)
    if failure:
        return Failure(failure.code, failure.detail, raw_response_ref=ref)

    data = resp.json().get("data", {})
    status = data.get("status")
    if status not in _LIVE_STATUSES:
        return Failure(FailureCode.AMBIGUOUS, f"unrecognized DigiLocker session status {status!r}", raw_response_ref=ref)
    return SessionStatus(status, tuple(data.get("documents_consented") or ()), ref)


def fetch_document(
    session: SandboxSession, session_id: str, doc_type: str, *,
    lawful_basis: LawfulBasis, conn=None,
) -> FetchedDocument | Failure:
    if doc_type not in DOC_TYPES:
        return Failure(FailureCode.MALFORMED, f"unsupported doc_type {doc_type!r}; DigiLocker only offers {DOC_TYPES}")

    observed_at = datetime.now(timezone.utc)
    path = f"/kyc/digilocker/sessions/{session_id}/documents/{doc_type}"
    url = f"{session.base_url}{path}"

    try:
        resp = session.get(path)
    except httpx.HTTPError as exc:
        return _http_failure(exc)

    ref = _record(
        conn, adapter_id="digilocker", adapter_version="1.0.0",
        capability_id="DIGILOCKER_DOCUMENT", observed_at=observed_at, url=url,
        request_headers=dict(resp.request.headers), request_body="",
        response_status=resp.status_code, response_headers=dict(resp.headers),
        response_body=resp.text, lawful_basis=lawful_basis, method="GET",
    )
    failure = _digilocker_status_failure(resp.status_code, resp.text)
    if failure:
        return Failure(failure.code, failure.detail, raw_response_ref=ref)

    files = resp.json().get("data", {}).get("files") or []
    if not files:
        return Failure(FailureCode.NOT_FOUND, "DigiLocker returned no files for this document type", raw_response_ref=ref)
    return FetchedDocument(tuple(files), ref)


def build_from_env() -> SandboxSession | None:
    """Same two env vars sandbox_co_in.py's build_from_env reads -- one
    Sandbox.co.in account, DigiLocker is just another product on it. A
    second SandboxSession rather than sharing sandbox_co_in.py's (that
    module's session isn't exposed externally, only the wrapped adapters
    are) -- an extra JWT fetch on first use, functionally identical
    credentials, not worth changing that shipped, tested module's contract
    for."""
    api_key = os.environ.get("SATYAPRAMANA_SANDBOX_API_KEY")
    api_secret = os.environ.get("SATYAPRAMANA_SANDBOX_API_SECRET")
    if not api_key or not api_secret:
        return None
    environment = os.environ.get("SATYAPRAMANA_SANDBOX_ENV", "test").lower()
    base_url = LIVE_BASE_URL if environment == "live" else TEST_BASE_URL
    return SandboxSession(api_key, api_secret, base_url=base_url)
