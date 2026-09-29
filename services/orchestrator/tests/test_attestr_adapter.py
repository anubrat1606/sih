"""UdyamStatusAdapter (round 11): backed by Attestr's MSME/Udyam
verification API, a second, separate vendor from Sandbox.co.in. No test
here makes a real network call -- same principle as test_sandbox_adapter.py
and test_explain_groq.py -- only httpx.post is monkeypatched.

Every verify() call makes two real HTTP calls -- a consent registration,
then the verification itself -- confirmed live 2026-09-30 against a real
Attestr account: a call with no registered consent returns a real 400
"insufficient consent" error. The GOENKA_ENTERPRISE payload below is a
real, genuine sample response Attestr's own API returned for a real
(anonymised-by-Attestr) Udyam number during that live verification, not a
fabricated fixture.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from satyapramana_store.adapters.attestr import UdyamStatusAdapter, build_from_env
from satyapramana_store.adapters.base import (
    Basis, Failure, FailureCode, LawfulBasis, Success, VerificationRequest,
)

BASIS = LawfulBasis(Basis.TENDER_EVALUATION, "officer_1", "Tender GEM-X evaluation")

_CONSENT_URL = "https://api.attestr.com/api/v3/public/consent/register"
_UDYAM_URL = "https://api.attestr.com/api/v3/public/corpx/udyam"

#: Real response, captured live 2026-09-30 -- confirms the top-level
#: "type" is business structure ("Proprietary"), not MSME size, which
#: lives in "classifications" instead (see attestr.py's own comment).
GOENKA_ENTERPRISE = {
    "valid": True, "reg": "UDYAM-XX-01-0000001", "entity": "GOENKA AGENCY",
    "type": "Proprietary", "majorActivity": ["Manufacturing"],
    "registered": "02/07/2021",
    "classifications": [
        {"date": "09/05/2023", "year": "2023-24", "type": "Micro"},
        {"date": "26/06/2022", "year": "2022-23", "type": "Micro"},
        {"date": "06/07/2021", "year": "2021-22", "type": "Micro"},
    ],
}


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.request = httpx.Request("POST", _UDYAM_URL)
        self.headers = {}

    def json(self):
        return self._payload


def _consent_ok(consent_id="CX_test_consent_id"):
    return _FakeResponse(200, {"_id": consent_id, "number": "0000-000000-0000"})


def _router(consent_response, verify_response):
    """Real verify() calls consent/register then corpx/udyam, in that
    order -- dispatch each fake httpx.post by URL so a test only has to
    say what each of the two real calls returns."""
    def post(url, *a, **kw):
        if url == _CONSENT_URL:
            return consent_response
        assert url == _UDYAM_URL, f"unexpected URL: {url}"
        return verify_response
    return post


def test_udyam_status_missing_number_is_refused_not_guessed(monkeypatch):
    adapter = UdyamStatusAdapter(auth_token="fake-token")

    def no_call(*a, **kw):
        raise AssertionError("no HTTP call should happen without a Udyam number")
    monkeypatch.setattr("satyapramana_store.adapters.attestr.httpx.post", no_call)

    outcome = adapter.verify(VerificationRequest("UDYAM_STATUS", {}, BASIS))
    assert isinstance(outcome, Failure)
    assert outcome.code is FailureCode.MALFORMED


def test_udyam_status_success(monkeypatch):
    adapter = UdyamStatusAdapter(auth_token="fake-token")
    monkeypatch.setattr(
        "satyapramana_store.adapters.attestr.httpx.post",
        _router(_consent_ok(), _FakeResponse(200, GOENKA_ENTERPRISE)))

    outcome = adapter.verify(
        VerificationRequest("UDYAM_STATUS", {"udyam_number": "UDYAM-XX-01-0000001"}, BASIS))
    assert isinstance(outcome, Success)
    values = {o.path: o.value for o in outcome.observations}
    assert values["bidder.udyam.status"] == "ACTIVE"
    assert values["bidder.udyam.entity_name"] == "GOENKA AGENCY"
    # The most recent classification (2023-24), not the top-level "type"
    # (which is "Proprietary" -- business structure, a different fact).
    assert values["bidder.udyam.enterprise_type"] == "Micro"
    assert values["bidder.udyam.registered_date"] == "02/07/2021"


def test_udyam_status_uses_the_most_recent_classification_not_an_older_one(monkeypatch):
    adapter = UdyamStatusAdapter(auth_token="fake-token")
    payload = {
        "valid": True, "entity": "Growing Co", "type": "Partnership", "registered": "01/01/2020",
        "classifications": [
            {"date": "01/01/2020", "year": "2020-21", "type": "Micro"},
            {"date": "01/01/2024", "year": "2024-25", "type": "Small"},  # grew, most recent
            {"date": "01/01/2022", "year": "2022-23", "type": "Micro"},
        ],
    }
    monkeypatch.setattr(
        "satyapramana_store.adapters.attestr.httpx.post",
        _router(_consent_ok(), _FakeResponse(200, payload)))

    outcome = adapter.verify(
        VerificationRequest("UDYAM_STATUS", {"udyam_number": "UDYAM-XX-01-0000002"}, BASIS))
    assert isinstance(outcome, Success)
    values = {o.path: o.value for o in outcome.observations}
    assert values["bidder.udyam.enterprise_type"] == "Small"


def test_udyam_status_not_found_is_honest_not_negative(monkeypatch):
    """valid: false means Attestr found no matching registration -- a real
    NOT_FOUND, not silently treated as a FAIL (not_found_is_negative is
    False on this capability, same reasoning as every other identifier
    lookup in this system)."""
    adapter = UdyamStatusAdapter(auth_token="fake-token")
    monkeypatch.setattr(
        "satyapramana_store.adapters.attestr.httpx.post",
        _router(_consent_ok(), _FakeResponse(200, {"valid": False, "message": "no such registration"})))

    outcome = adapter.verify(
        VerificationRequest("UDYAM_STATUS", {"udyam_number": "UDYAM-XX-99-9999999"}, BASIS))
    assert isinstance(outcome, Failure)
    assert outcome.code is FailureCode.NOT_FOUND
    assert not adapter.manifest.capabilities[0].not_found_is_negative


def test_udyam_status_bad_credentials(monkeypatch):
    """A 401 on the *consent* call (the first real call verify() makes)
    must surface as UNAUTHORIZED without ever reaching the verification
    call -- confirmed by the router asserting no other URL is hit."""
    adapter = UdyamStatusAdapter(auth_token="wrong-token")
    monkeypatch.setattr(
        "satyapramana_store.adapters.attestr.httpx.post",
        _router(_FakeResponse(401, text="unauthorized"), None))

    outcome = adapter.verify(
        VerificationRequest("UDYAM_STATUS", {"udyam_number": "UDYAM-XX-01-0000001"}, BASIS))
    assert isinstance(outcome, Failure)
    assert outcome.code is FailureCode.UNAUTHORIZED


def test_udyam_status_insufficient_consent_is_reported_honestly(monkeypatch):
    """The real error this system hit live before the consent scoping was
    fixed -- confirms it surfaces as a real, readable Failure rather than
    being swallowed or misreported as something else."""
    adapter = UdyamStatusAdapter(auth_token="fake-token")
    monkeypatch.setattr(
        "satyapramana_store.adapters.attestr.httpx.post",
        _router(_consent_ok(), _FakeResponse(
            400, text='{"details": "Missing or insufficient consent to process the request"}')))

    outcome = adapter.verify(
        VerificationRequest("UDYAM_STATUS", {"udyam_number": "UDYAM-XX-01-0000001"}, BASIS))
    assert isinstance(outcome, Failure)
    assert outcome.code is FailureCode.MALFORMED
    assert "consent" in outcome.detail


def test_udyam_status_network_failure_is_unavailable_not_a_crash(monkeypatch):
    adapter = UdyamStatusAdapter(auth_token="fake-token")

    def raise_it(*a, **kw):
        raise httpx.ConnectError("connection refused")
    monkeypatch.setattr("satyapramana_store.adapters.attestr.httpx.post", raise_it)

    outcome = adapter.verify(
        VerificationRequest("UDYAM_STATUS", {"udyam_number": "UDYAM-TN-01-0001234"}, BASIS))
    assert isinstance(outcome, Failure)
    assert outcome.code is FailureCode.UNAVAILABLE


def test_build_from_env_without_a_token_is_a_noop(monkeypatch):
    monkeypatch.delenv("SATYAPRAMANA_ATTESTR_AUTH_TOKEN", raising=False)
    assert build_from_env() == []


def test_build_from_env_with_a_token_returns_the_adapter(monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_ATTESTR_AUTH_TOKEN", "fake-token")
    adapters = build_from_env()
    assert len(adapters) == 1
    assert isinstance(adapters[0], UdyamStatusAdapter)
    assert adapters[0].manifest.adapter_id == "udyam_status"
