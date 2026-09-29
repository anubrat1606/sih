"""UdyamStatusAdapter (round 11): backed by Attestr's documented MSME/Udyam
verification API, a second, separate vendor from Sandbox.co.in. No test
here makes a real network call -- same principle as test_sandbox_adapter.py
and test_explain_groq.py -- only httpx.post is monkeypatched.
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


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.request = httpx.Request("POST", "https://api.attestr.com/api/v2/public/corpx/udyam")
        self.headers = {}

    def json(self):
        return self._payload


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
    payload = {"valid": True, "reg": "UDYAM-TN-01-0001234", "entity": "Test Enterprises",
               "type": "Micro", "registered": "2021-05-01"}
    monkeypatch.setattr("satyapramana_store.adapters.attestr.httpx.post",
                         lambda *a, **kw: _FakeResponse(200, payload))

    outcome = adapter.verify(
        VerificationRequest("UDYAM_STATUS", {"udyam_number": "UDYAM-TN-01-0001234"}, BASIS))
    assert isinstance(outcome, Success)
    values = {o.path: o.value for o in outcome.observations}
    assert values["bidder.udyam.status"] == "ACTIVE"
    assert values["bidder.udyam.entity_name"] == "Test Enterprises"
    assert values["bidder.udyam.enterprise_type"] == "Micro"
    assert values["bidder.udyam.registered_date"] == "2021-05-01"


def test_udyam_status_not_found_is_honest_not_negative(monkeypatch):
    """valid: false means Attestr found no matching registration -- a real
    NOT_FOUND, not silently treated as a FAIL (not_found_is_negative is
    False on this capability, same reasoning as every other identifier
    lookup in this system)."""
    adapter = UdyamStatusAdapter(auth_token="fake-token")
    monkeypatch.setattr(
        "satyapramana_store.adapters.attestr.httpx.post",
        lambda *a, **kw: _FakeResponse(200, {"valid": False, "message": "no such registration"}))

    outcome = adapter.verify(
        VerificationRequest("UDYAM_STATUS", {"udyam_number": "UDYAM-XX-99-9999999"}, BASIS))
    assert isinstance(outcome, Failure)
    assert outcome.code is FailureCode.NOT_FOUND
    assert not adapter.manifest.capabilities[0].not_found_is_negative


def test_udyam_status_bad_credentials(monkeypatch):
    adapter = UdyamStatusAdapter(auth_token="wrong-token")
    monkeypatch.setattr("satyapramana_store.adapters.attestr.httpx.post",
                         lambda *a, **kw: _FakeResponse(401, text="unauthorized"))

    outcome = adapter.verify(
        VerificationRequest("UDYAM_STATUS", {"udyam_number": "UDYAM-TN-01-0001234"}, BASIS))
    assert isinstance(outcome, Failure)
    assert outcome.code is FailureCode.UNAUTHORIZED


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
