"""Live adapters for Sandbox.co.in -- one aggregator account, two capabilities.

Contracts below were read from Sandbox's own developer docs
(developer.sandbox.co.in), not guessed:

  Auth       POST https://test-api.sandbox.co.in/authenticate
             headers: x-api-key, x-api-secret, x-api-version
             -> {"data": {"access_token": "<jwt>"}}, valid 24h.
             Subsequent calls send the token RAW in `authorization` --
             confirmed against the docs: no "Bearer " prefix.

  PAN verify POST /kyc/pan/verify
             body: {pan, name_as_per_pan, date_of_birth (DD/MM/YYYY), consent, reason}
             -> {"data": {"status", "category", "name_as_per_pan_match",
                           "date_of_birth_match", "aadhaar_seeding_status"}}

  GST search POST /gst/compliance/public/gstin/search
             body: {gstin}
             -> {"data": {"data": {"sts", "lgnm", "rgdt", ...},
                           "status_cd": "1"}}   -- "status_cd": "0" means
             not found (error_cd FO8000), still HTTP 200.

This module only turns those two calls into Observations or Failures. It never
canonicalises a date or decides a verdict -- that is NORMALIZE's and DECIDE's
job respectively, not an adapter's (docs/satyapramana.md section 2.2).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from satyapramana.verdicts import Channel, Tier

from .archive import archive
from .base import (
    Basis, Capability, CapabilityManifest, Failure, FailureCode, Observation,
    Success, VerificationRequest,
)

TEST_BASE_URL = "https://test-api.sandbox.co.in"
LIVE_BASE_URL = "https://api.sandbox.co.in"
API_VERSION = "1.0.0"
TIMEOUT_SECONDS = 10.0


class SandboxSession:
    """Owns the JWT lifecycle for one api_key/api_secret pair.

    One session is shared by both capability adapters -- they're one account,
    not two -- so a token fetched for a PAN check is reused for a GST check
    without re-authenticating.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        base_url: str = TEST_BASE_URL,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
        self._token: str | None = None
        self._expires_at: datetime | None = None

    def _authenticate(self) -> None:
        resp = self._client.post(
            f"{self.base_url}/authenticate",
            headers={
                "x-api-key": self.api_key,
                "x-api-secret": self.api_secret,
                "x-api-version": API_VERSION,
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        self._token = resp.json()["data"]["access_token"]
        # Documented as valid 24h; refresh an hour early rather than race the
        # expiry mid-request.
        self._expires_at = datetime.now(timezone.utc) + timedelta(hours=23)

    def token(self) -> str:
        if self._token is None or datetime.now(timezone.utc) >= self._expires_at:
            self._authenticate()
        return self._token

    def headers(self) -> dict[str, str]:
        return {
            "authorization": self.token(),
            "x-api-key": self.api_key,
            "x-api-version": API_VERSION,
            "Content-Type": "application/json",
        }

    def post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        return self._client.post(
            f"{self.base_url}{path}", headers=self.headers(), json=body
        )


def _record(
    conn,
    *,
    adapter_id: str,
    adapter_version: str,
    capability_id: str,
    observed_at: datetime,
    url: str,
    request_headers: dict[str, str],
    request_body: str,
    response_status: int | None,
    response_headers: dict[str, str],
    response_body: str | None,
    lawful_basis,
) -> str:
    """Archive the exchange if a DB connection was given; otherwise return a
    content hash without persisting anything. Production (app.py) always
    passes a real conn -- the no-conn path exists only for adapter-level unit
    tests that exercise the HTTP mapping without a database."""
    if conn is not None:
        return archive(
            conn, adapter_id=adapter_id, adapter_version=adapter_version,
            capability_id=capability_id, observed_at=observed_at, method="POST",
            url=url, request_headers=request_headers, request_body=request_body,
            response_status=response_status, response_headers=response_headers,
            response_body=response_body, lawful_basis=lawful_basis,
        )
    return "unarchived:" + hashlib.sha256(
        json.dumps({"url": url, "response_body": response_body}, sort_keys=True)
        .encode("utf-8")
    ).hexdigest()


def _http_failure(exc: httpx.HTTPError) -> Failure:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ConnectTimeout)):
        return Failure(FailureCode.UNAVAILABLE, f"Sandbox.co.in unreachable: {exc}")
    return Failure(FailureCode.UNAVAILABLE, f"Sandbox.co.in request failed: {exc}")


def _status_failure(status: int, body_text: str) -> Failure | None:
    """Maps an HTTP status to a FailureCode, or None if the caller should
    proceed to parse the body as a normal response (200 covers both success
    and GST's documented "not found" shape)."""
    if status in (401, 403):
        return Failure(FailureCode.UNAUTHORIZED, f"Sandbox.co.in rejected the credentials (HTTP {status})")
    if status == 429:
        return Failure(FailureCode.RATE_LIMITED, "Sandbox.co.in rate-limited this request")
    if status == 422:
        return Failure(FailureCode.MALFORMED, f"Sandbox.co.in rejected the request as malformed: {body_text}")
    if status == 521:
        # Documented, non-standard: MCA's own "not found" signal, not the
        # authority being down. Must be checked before the >=500 branch below.
        return Failure(FailureCode.NOT_FOUND, body_text or "company master data not found")
    if status >= 500:
        return Failure(FailureCode.UNAVAILABLE, f"Sandbox.co.in returned HTTP {status}: {body_text}")
    if status != 200:
        return Failure(FailureCode.UNAVAILABLE, f"unexpected HTTP {status}: {body_text}")
    return None


_ISO_DATE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")


def _iso_to_ddmmyyyy(value: str) -> str | None:
    """NORMALIZE (evidence.py) stores every date this system reads as
    canonical ISO-8601 -- that is what a resolved subject field always is by
    the time it reaches an adapter's verify(). Sandbox.co.in's own PAN
    verification contract is documented as DD/MM/YYYY, a wire-format detail
    that belongs entirely to this adapter (the same way a different
    authority's own date format would), never upstream in app.py or
    evidence.py. Returns None, never a guess, if the value isn't the
    ISO-8601 shape NORMALIZE guarantees -- that would mean something changed
    upstream in a way this adapter needs to know about, not silently paper
    over."""
    m = _ISO_DATE.fullmatch(value)
    if not m:
        return None
    year, month, day = m.groups()
    return f"{day}/{month}/{year}"


class PanStatusAdapter:
    """docs/ADAPTERS.md capability PAN_STATUS, backed by Sandbox.co.in's
    Verify PAN Details endpoint.

    Sandbox's PAN check is not identifier-only: it requires the holder's name
    and date of birth as printed on the card, and returns only a match
    boolean against what was submitted -- not a canonical name. Both
    `provides` and the failure path below reflect that honestly rather than
    promising fields this endpoint never returns.
    """

    def __init__(self, session: SandboxSession):
        self._session = session
        self.manifest = CapabilityManifest(
            adapter_id="pan_status",
            adapter_version="1.0.0",
            authority="Income Tax Department, Government of India",
            intermediary="Sandbox.co.in",
            identifier_queryable=True,
            capabilities=(
                Capability(
                    capability_id="PAN_STATUS",
                    provides=("bidder.pan.status", "bidder.pan.holder_category"),
                    tier=Tier.A,
                    channel=Channel.AGGREGATOR,
                    as_of_supported=False,
                    freshness_days=90,
                    not_found_is_negative=True,
                    not_found_justification=(
                        "The PAN allotment register is complete and authoritative "
                        "for the PAN identifier space; a PAN absent from it has "
                        "not been allotted and is therefore not valid."
                    ),
                    lawful_bases=(Basis.TENDER_EVALUATION, Basis.PUBLIC_REGISTER),
                    status="LIVE",
                ),
            ),
        )

    def verify(self, request: VerificationRequest, conn=None) -> Success | Failure:
        pan = request.subject.get("pan_number")
        if not pan:
            return Failure(FailureCode.MALFORMED, "no PAN number extracted for this bidder; nothing to submit")

        name = request.subject.get("pan_holder_name")
        dob_iso = request.subject.get("pan_date_of_birth")
        if not name or not dob_iso:
            return Failure(
                FailureCode.MALFORMED,
                "Sandbox.co.in's PAN verification requires the holder's name and "
                "date of birth as printed on the card; extraction does not "
                "currently capture either field, so this check cannot be "
                "attempted -- not skipped silently, refused honestly",
            )

        dob = _iso_to_ddmmyyyy(dob_iso)
        if dob is None:
            return Failure(
                FailureCode.MALFORMED,
                f"pan_date_of_birth resolved to {dob_iso!r}, not the ISO-8601 "
                "form NORMALIZE is supposed to guarantee -- refusing to guess "
                "a wire format rather than sending Sandbox.co.in something "
                "that was never actually validated",
            )

        reason = request.lawful_basis.purpose
        if len(reason) < 20:
            # Sandbox requires >=20 chars; padding would mean sending text we
            # didn't mean, so this fails honestly instead.
            return Failure(
                FailureCode.MALFORMED,
                f"lawful_basis.purpose is {len(reason)} chars; Sandbox.co.in "
                "requires a reason of at least 20 characters",
            )

        body = {
            "@entity": "in.co.sandbox.kyc.pan_verification.request",
            "pan": pan,
            "name_as_per_pan": name,
            "date_of_birth": dob,
            "consent": "Y",
            "reason": reason,
        }
        observed_at = datetime.now(timezone.utc)
        url = f"{self._session.base_url}/kyc/pan/verify"

        try:
            resp = self._session.post("/kyc/pan/verify", body)
        except httpx.HTTPError as exc:
            return _http_failure(exc)

        ref = _record(
            conn, adapter_id="pan_status", adapter_version="1.0.0",
            capability_id="PAN_STATUS", observed_at=observed_at, url=url,
            request_headers=dict(resp.request.headers), request_body=json.dumps(body),
            response_status=resp.status_code, response_headers=dict(resp.headers),
            response_body=resp.text, lawful_basis=request.lawful_basis,
        )

        failure = _status_failure(resp.status_code, resp.text)
        if failure:
            failure = Failure(failure.code, failure.detail, raw_response_ref=ref)
            return failure

        data = resp.json().get("data", {})
        status = data.get("status")
        if not status:
            return Failure(FailureCode.NOT_FOUND, "no PAN record returned", raw_response_ref=ref)

        observations = [Observation("bidder.pan.status", status, Tier.A, Channel.AGGREGATOR)]
        if data.get("category"):
            observations.append(
                Observation("bidder.pan.holder_category", data["category"], Tier.A, Channel.AGGREGATOR)
            )
        return Success(
            observations=tuple(observations), raw_response_ref=ref,
            observed_at=observed_at, source_asserted_at=None,
        )


class GstStatusAdapter:
    """docs/ADAPTERS.md capability GST_STATUS, backed by Sandbox.co.in's
    Search GSTIN endpoint."""

    def __init__(self, session: SandboxSession):
        self._session = session
        self.manifest = CapabilityManifest(
            adapter_id="gst_status",
            adapter_version="1.0.0",
            authority="Goods and Services Tax Network",
            intermediary="Sandbox.co.in",
            identifier_queryable=True,
            capabilities=(
                Capability(
                    capability_id="GST_STATUS",
                    provides=(
                        "bidder.gst.status", "bidder.gst.legal_name",
                        "bidder.gst.registration_date",
                    ),
                    tier=Tier.A,
                    channel=Channel.AGGREGATOR,
                    as_of_supported=False,
                    freshness_days=30,
                    not_found_is_negative=False,
                    lawful_bases=(Basis.TENDER_EVALUATION, Basis.PUBLIC_REGISTER),
                    status="LIVE",
                ),
            ),
        )

    def verify(self, request: VerificationRequest, conn=None) -> Success | Failure:
        gstin = request.subject.get("gstin")
        if not gstin:
            return Failure(FailureCode.MALFORMED, "no GSTIN extracted for this bidder; nothing to submit")

        body = {"gstin": gstin}
        observed_at = datetime.now(timezone.utc)
        url = f"{self._session.base_url}/gst/compliance/public/gstin/search"

        try:
            resp = self._session.post("/gst/compliance/public/gstin/search", body)
        except httpx.HTTPError as exc:
            return _http_failure(exc)

        ref = _record(
            conn, adapter_id="gst_status", adapter_version="1.0.0",
            capability_id="GST_STATUS", observed_at=observed_at, url=url,
            request_headers=dict(resp.request.headers), request_body=json.dumps(body),
            response_status=resp.status_code, response_headers=dict(resp.headers),
            response_body=resp.text, lawful_basis=request.lawful_basis,
        )

        failure = _status_failure(resp.status_code, resp.text)
        if failure:
            failure = Failure(failure.code, failure.detail, raw_response_ref=ref)
            return failure

        payload = resp.json().get("data", {})
        if payload.get("status_cd") != "1":
            err = payload.get("error", {}).get("message", "no records found")
            return Failure(FailureCode.NOT_FOUND, err, raw_response_ref=ref)

        record = payload.get("data", {})
        observations = []
        if record.get("sts"):
            observations.append(Observation("bidder.gst.status", record["sts"], Tier.A, Channel.AGGREGATOR))
        if record.get("lgnm"):
            observations.append(Observation("bidder.gst.legal_name", record["lgnm"], Tier.A, Channel.AGGREGATOR))
        if record.get("rgdt"):
            # Raw string as the authority returned it -- NORMALIZE canonicalises
            # to ISO-8601, an adapter never does.
            observations.append(Observation("bidder.gst.registration_date", record["rgdt"], Tier.A, Channel.AGGREGATOR))
        if not observations:
            return Failure(FailureCode.AMBIGUOUS, "GSTIN found but the response carried none of the fields this capability provides", raw_response_ref=ref)

        return Success(
            observations=tuple(observations), raw_response_ref=ref,
            observed_at=observed_at,
            # lstupdt's format isn't confirmed against a real response yet --
            # left unset rather than guessed, same stance as the EPFO regex.
            source_asserted_at=None,
        )


class CinStatusAdapter:
    """docs/ADAPTERS.md capability CIN_STATUS, backed by Sandbox.co.in's
    Company Master Data endpoint.

    The registry's placeholder manifest lists `bidder.entity.directors` among
    this capability's provided paths, inherited from when the design assumed
    a director lookup would exist. Sandbox's Director Master Data API is
    documented as discontinued, so this adapter's `provides` omits that path
    rather than promise a field it can never return -- narrower than the
    placeholder, on purpose.

    Nothing in this codebase extracts a CIN from a document yet (`extract/`
    is Suhani's, per CONTRIBUTING.md) -- so today this always returns the
    honest MALFORMED refusal below, exactly like PAN_STATUS does for the
    missing name/DOB. It goes live for real the moment that extraction
    lands, no adapter change required.
    """

    def __init__(self, session: SandboxSession):
        self._session = session
        self.manifest = CapabilityManifest(
            adapter_id="mca_cin",
            adapter_version="1.0.0",
            authority="Ministry of Corporate Affairs",
            intermediary="Sandbox.co.in",
            identifier_queryable=True,
            capabilities=(
                Capability(
                    capability_id="CIN_STATUS",
                    provides=(
                        "bidder.entity.cin", "bidder.entity.legal_name_canonical",
                        "bidder.entity.incorporation_date", "bidder.entity.status",
                    ),
                    tier=Tier.A,
                    channel=Channel.AGGREGATOR,
                    as_of_supported=False,
                    freshness_days=90,
                    not_found_is_negative=False,
                    lawful_bases=(Basis.TENDER_EVALUATION, Basis.PUBLIC_REGISTER),
                    status="LIVE",
                ),
            ),
        )

    def verify(self, request: VerificationRequest, conn=None) -> Success | Failure:
        cin = request.subject.get("cin")
        if not cin:
            return Failure(FailureCode.MALFORMED, "no CIN extracted for this bidder; nothing to submit")

        body = {"cin": cin}
        observed_at = datetime.now(timezone.utc)
        url = f"{self._session.base_url}/kyc/mca/company/master-data"

        try:
            resp = self._session.post("/kyc/mca/company/master-data", body)
        except httpx.HTTPError as exc:
            return _http_failure(exc)

        ref = _record(
            conn, adapter_id="mca_cin", adapter_version="1.0.0",
            capability_id="CIN_STATUS", observed_at=observed_at, url=url,
            request_headers=dict(resp.request.headers), request_body=json.dumps(body),
            response_status=resp.status_code, response_headers=dict(resp.headers),
            response_body=resp.text, lawful_basis=request.lawful_basis,
        )

        failure = _status_failure(resp.status_code, resp.text)
        if failure:
            failure = Failure(failure.code, failure.detail, raw_response_ref=ref)
            return failure

        rows = resp.json().get("data") or []
        if not rows:
            return Failure(FailureCode.NOT_FOUND, "no company master data returned", raw_response_ref=ref)
        record = rows[0]

        observations = [Observation("bidder.entity.cin", record.get("cin", cin), Tier.A, Channel.AGGREGATOR)]
        if record.get("company_name"):
            observations.append(Observation("bidder.entity.legal_name_canonical", record["company_name"], Tier.A, Channel.AGGREGATOR))
        if record.get("company_registration_date"):
            observations.append(Observation("bidder.entity.incorporation_date", record["company_registration_date"], Tier.A, Channel.AGGREGATOR))
        if record.get("company_status"):
            observations.append(Observation("bidder.entity.status", record["company_status"], Tier.A, Channel.AGGREGATOR))

        return Success(
            observations=tuple(observations), raw_response_ref=ref,
            observed_at=observed_at, source_asserted_at=None,
        )


def build_from_env() -> list[Any]:
    """The whole plug-in point. Set both env vars and these three capabilities
    flip from AWAITING_CREDENTIALS to LIVE on next process start; unset either
    and verification falls straight back to the honest UnconfiguredAdapter.

    Sandbox.co.in issues separate credential pools for their test and
    production hosts -- a `key_live_...` pair is production and belongs
    against LIVE_BASE_URL, not the test host. Defaulting to the test host
    would just 401 for a live key pair, so the environment says which one:
    unset or "test" -> TEST_BASE_URL (default, safest); "live" -> LIVE_BASE_URL.
    Every call against the live host is a real, billed query against a real
    government-adjacent record -- this flag exists so that only happens when
    someone deliberately set it, never by a default guess.
    """
    api_key = os.environ.get("SATYAPRAMANA_SANDBOX_API_KEY")
    api_secret = os.environ.get("SATYAPRAMANA_SANDBOX_API_SECRET")
    if not api_key or not api_secret:
        return []
    environment = os.environ.get("SATYAPRAMANA_SANDBOX_ENV", "test").lower()
    base_url = LIVE_BASE_URL if environment == "live" else TEST_BASE_URL
    session = SandboxSession(api_key, api_secret, base_url=base_url)
    return [PanStatusAdapter(session), GstStatusAdapter(session), CinStatusAdapter(session)]
