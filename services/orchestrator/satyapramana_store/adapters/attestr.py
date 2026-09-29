"""UDYAM_STATUS, backed by Attestr's MSME/Udyam verification API.

Separate vendor from Sandbox.co.in (adapters/sandbox_co_in.py), so a
separate file with its own session/auth/error-mapping, same reasoning
digilocker.py's own separate consent flow already follows for a
differently-shaped integration on the same account.

Round 10 confirmed UDYAM_STATUS unavailable *from Sandbox.co.in* -- checked
against their own KYC/KYB catalog, which does not offer it. That was never
a claim that no vendor anywhere offers it; a follow-up check (this file)
found Attestr's documented MSME Udyam Verification API
(docs.attestr.com/attestr-docs/msme-udyam-verification-api): POST
/api/{version}/public/corpx/udyam, Basic-auth, real request/response shape
below. Built against Attestr's own published documentation; not yet
exercised against a real account, since none exists on this deployment
yet -- SATYAPRAMANA_ATTESTR_AUTH_TOKEN unset means this capability stays
on the honest NullAdapter, exactly as before this file existed.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from satyapramana.verdicts import Channel, Tier

from .archive import archive
from .base import (
    Basis, Capability, CapabilityManifest, Failure, FailureCode,
    Observation, Success, VerificationRequest,
)

#: Attestr issues separate test/live hosts, same shape as Sandbox.co.in's
#: own test/live split -- see build_from_env() below for which one is used.
TEST_BASE_URL = "https://api.attestr.com"
LIVE_BASE_URL = "https://api.attestr.com"
_API_VERSION = "v2"


def _record(
    conn, *, adapter_id: str, adapter_version: str, capability_id: str,
    observed_at: datetime, url: str, request_headers: dict[str, str],
    request_body: str, response_status: int | None,
    response_headers: dict[str, str], response_body: str | None, lawful_basis,
) -> str:
    """See sandbox_co_in.py's identical helper -- same archive-or-hash
    shape, kept as a local copy rather than a cross-vendor import so this
    file's only dependency on the rest of adapters/ is the generic
    archive() function and the base.py contract, nothing Sandbox-specific."""
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
        return Failure(FailureCode.UNAVAILABLE, f"Attestr unreachable: {exc}")
    return Failure(FailureCode.UNAVAILABLE, f"Attestr request failed: {exc}")


def _status_failure(status: int, body_text: str) -> Failure | None:
    """Only the generic HTTP-layer failures are documented for Attestr;
    the specific "not found" case is a 200 with valid: false in the body
    (handled in verify() below, not here) -- not an HTTP status at all."""
    if status in (401, 403):
        return Failure(FailureCode.UNAUTHORIZED, f"Attestr rejected the credentials (HTTP {status})")
    if status == 429:
        return Failure(FailureCode.RATE_LIMITED, "Attestr rate-limited this request")
    if status == 422:
        return Failure(FailureCode.MALFORMED, f"Attestr rejected the request as malformed: {body_text}")
    if status >= 500:
        return Failure(FailureCode.UNAVAILABLE, f"Attestr returned HTTP {status}: {body_text}")
    if status != 200:
        return Failure(FailureCode.UNAVAILABLE, f"unexpected HTTP {status}: {body_text}")
    return None


class UdyamStatusAdapter:
    """docs/ADAPTERS.md capability UDYAM_STATUS, backed by Attestr's
    documented MSME/Udyam verification endpoint. `adapter_id` matches the
    placeholder already declared in schemas/capability_registry.json
    ("udyam_status") so registering this real adapter replaces that
    NullAdapter -- the whole plug-in point, no other file needs to change.
    """

    def __init__(self, auth_token: str, base_url: str = LIVE_BASE_URL):
        self._auth_token = auth_token
        self._base_url = base_url
        self.manifest = CapabilityManifest(
            adapter_id="udyam_status",
            adapter_version="1.0.0",
            authority="Ministry of Micro, Small and Medium Enterprises",
            intermediary="Attestr",
            identifier_queryable=True,
            capabilities=(
                Capability(
                    capability_id="UDYAM_STATUS",
                    provides=(
                        "bidder.udyam.status", "bidder.udyam.entity_name",
                        "bidder.udyam.enterprise_type", "bidder.udyam.registered_date",
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

    def verify(self, request: VerificationRequest, conn: Any = None) -> Success | Failure:
        udyam_number = request.subject.get("udyam_number")
        if not udyam_number:
            return Failure(FailureCode.MALFORMED, "no Udyam number extracted for this bidder; nothing to submit")

        body = {"reg": udyam_number}
        observed_at = datetime.now(timezone.utc)
        url = f"{self._base_url}/api/{_API_VERSION}/public/corpx/udyam"
        headers = {"Authorization": f"Basic {self._auth_token}", "Content-Type": "application/json"}

        try:
            resp = httpx.post(url, json=body, headers=headers, timeout=30.0)
        except httpx.HTTPError as exc:
            return _http_failure(exc)

        ref = _record(
            conn, adapter_id="udyam_status", adapter_version="1.0.0",
            capability_id="UDYAM_STATUS", observed_at=observed_at, url=url,
            request_headers=dict(resp.request.headers), request_body=json.dumps(body),
            response_status=resp.status_code, response_headers=dict(resp.headers),
            response_body=resp.text, lawful_basis=request.lawful_basis,
        )

        failure = _status_failure(resp.status_code, resp.text)
        if failure:
            return Failure(failure.code, failure.detail, raw_response_ref=ref)

        data = resp.json()
        if not data.get("valid"):
            return Failure(FailureCode.NOT_FOUND, data.get("message") or "no Udyam registration found for this number", raw_response_ref=ref)

        # Attestr's documented response has no separate textual status field
        # (unlike CIN's company_status) -- `valid: true` on a queried number
        # IS the authority's own signal that a current, matching Udyam
        # registration exists, so "ACTIVE" here is a derived label for a
        # real fact, not an invented one. Revisit against a real response
        # once a real account exists, in case Attestr's actual payload
        # carries a field this documentation excerpt didn't show.
        observations = [Observation("bidder.udyam.status", "ACTIVE", Tier.A, Channel.AGGREGATOR)]
        if data.get("entity"):
            observations.append(Observation("bidder.udyam.entity_name", data["entity"], Tier.A, Channel.AGGREGATOR))
        if data.get("type"):
            observations.append(Observation("bidder.udyam.enterprise_type", data["type"], Tier.A, Channel.AGGREGATOR))
        if data.get("registered"):
            observations.append(Observation("bidder.udyam.registered_date", data["registered"], Tier.A, Channel.AGGREGATOR))

        return Success(
            observations=tuple(observations), raw_response_ref=ref,
            observed_at=observed_at, source_asserted_at=None,
        )


def build_from_env() -> list[Any]:
    """The whole plug-in point, same shape as sandbox_co_in.py's own
    build_from_env(). SATYAPRAMANA_ATTESTR_AUTH_TOKEN unset -> [] -> the
    JSON-declared NullAdapter placeholder for UDYAM_STATUS is untouched."""
    token = os.environ.get("SATYAPRAMANA_ATTESTR_AUTH_TOKEN")
    if not token:
        return []
    env = os.environ.get("SATYAPRAMANA_ATTESTR_ENV", "live")
    base_url = LIVE_BASE_URL if env == "live" else TEST_BASE_URL
    return [UdyamStatusAdapter(auth_token=token, base_url=base_url)]
