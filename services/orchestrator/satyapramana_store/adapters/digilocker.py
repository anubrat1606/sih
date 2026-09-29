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

Round 10 follow-up: DigiLocker consent alone proves a real Aadhaar-
verified person completed the flow -- it does not, by itself, prove
that person is the bidder. `parse_aadhaar_xml` closes that gap the same
way the codebase already closes the equivalent PAN-embedded-in-GSTIN
gap (app.py's `identifier_cross_check`): extract the Aadhaar holder's
name and date of birth from the real signed XML DigiLocker returns, and
let app.py compare them against `bidder.pan.holder_name`/
`bidder.pan.date_of_birth`, already on file from the bidder's own PAN
upload. Deliberately minimal about what's extracted and stored: the
Aadhaar XML also carries a full postal address and a base64 photograph
neither this check nor anything else in this system needs -- charter
§9's security artefact calls for "PII handling and minimisation"
explicitly, and this module takes that as a real constraint, not
decoration. Name and DOB only, nothing else read out of the document,
and the document's own bytes are never archived or persisted --
_record already captures a citable reference to the *metadata* response
that pointed at it, which is provenance enough without keeping a copy
of someone's Aadhaar.

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
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree

import httpx

from satyapramana.verdicts import Channel, Tier

from .base import (
    Basis, Capability, CapabilityManifest, Failure, FailureCode, LawfulBasis,
    VerificationRequest,
)
from .sandbox_co_in import (
    LIVE_BASE_URL, TEST_BASE_URL, TIMEOUT_SECONDS, SandboxSession, _http_failure, _record,
)

DOC_TYPES = ("aadhaar", "pan", "driving_license")
_LIVE_STATUSES = ("created", "succeeded", "failed", "expired")

#: One shared Capability object -- the placeholder adapter's manifest below
#: and app.py's dedicated endpoints both reference this exact instance, so
#: the registry/coverage-report view and the real consent-flow endpoints
#: can never silently drift into describing two different capabilities.
DIGILOCKER_CAPABILITY = Capability(
    capability_id="DIGILOCKER_DOCUMENT",
    provides=(
        "bidder.digilocker.aadhaar_verified", "bidder.digilocker.aadhaar_issuer",
        "bidder.digilocker.aadhaar_name", "bidder.digilocker.aadhaar_dob",
        # Only ever emitted once bidder.pan.holder_name is itself resolved --
        # there is nothing to cross-check against before that, and this
        # capability does not manufacture a placeholder result to fill the
        # gap. Still declared here: it is a real, possible output of this
        # capability, the same way an optional field on any other adapter's
        # response is still named in its manifest.
        "bidder.digilocker.pan_identity_match",
    ),
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


@dataclass(frozen=True)
class AadhaarIdentity:
    name: str
    #: ISO-8601 -- NORMALIZE's canonical form, converted from the XML's
    #: own DD-MM-YYYY here, the same wire-format-belongs-to-the-adapter
    #: discipline sandbox_co_in.py's _iso_to_ddmmyyyy already follows for
    #: the opposite direction (ISO out to an authority's own format).
    dob_iso: str | None


_AADHAAR_DOB = re.compile(r"^([0-9]{2})-([0-9]{2})-([0-9]{4})$")


def download_document_file(url: str, *, timeout: float = TIMEOUT_SECONDS) -> bytes:
    """The `url` in a fetch_document response is a pre-signed S3 link, not
    a Sandbox.co.in API path -- no JWT, no x-api-key, just a plain GET the
    same way a browser would fetch it. Separate from SandboxSession on
    purpose: this talks to S3, not to Sandbox."""
    resp = httpx.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def parse_aadhaar_xml(xml_bytes: bytes) -> AadhaarIdentity | None:
    """Reads exactly two facts out of the real, signed XML DigiLocker
    returns for an Aadhaar document (structure and field names confirmed
    against Sandbox's own published sample-responses doc, not guessed):

        <Certificate><CertificateData><KycRes><UidData>
          <Poi name="..." dob="DD-MM-YYYY" gender="..."/>
        </UidData></KycRes></CertificateData></Certificate>

    Deliberately does not read `Poa` (postal address), `LData` (local-
    language name/address), or `Pht` (the photograph) -- none is needed
    for a name/DOB cross-check against the bidder's PAN record, and
    reading them would be exactly the kind of PII over-collection this
    module's own docstring says not to do.

    `ElementTree.fromstring` never resolves external entities or DTDs by
    default (a difference from some other languages' XML parsers) --
    still worth stating explicitly for content originating outside this
    process, even signed content from a trusted source.

    Returns None, never a guess, if the document doesn't have the shape
    this function expects -- a malformed or unexpected document is a
    real, reportable absence of evidence, not something to paper over
    with a partial read.
    """
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return None
    poi = root.find(".//UidData/Poi")
    if poi is None:
        return None
    name = poi.get("name")
    if not name:
        return None
    dob_raw = poi.get("dob")
    dob_iso = None
    if dob_raw:
        m = _AADHAAR_DOB.fullmatch(dob_raw)
        if m:
            day, month, year = m.groups()
            dob_iso = f"{year}-{month}-{day}"
    return AadhaarIdentity(name=name, dob_iso=dob_iso)


def _normalize_name(name: str) -> str:
    """Identifier match beats semantic similarity, always (charter §2.2) --
    applied here to the one place this codebase compares two humans'
    names rather than two statutory identifiers. This does not attempt
    fuzzy/phonetic matching (no middle-name tolerance, no transliteration
    handling) -- a genuine difference (a nickname, a missing middle name)
    is reported honestly as AMBIGUOUS by the caller, never silently
    guessed into a match."""
    return re.sub(r"\s+", " ", name.strip().upper())


def names_match(a: str, b: str) -> bool:
    return _normalize_name(a) == _normalize_name(b)


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
