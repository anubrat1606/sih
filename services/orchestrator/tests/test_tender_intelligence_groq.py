"""GroqDecomposer: the alternate Tender Intelligence provider (round 11).
Same no-real-network-call principle as test_tender_intelligence.py's own
docstring -- only `httpx.post` is monkeypatched.
"""
from __future__ import annotations

import json
from datetime import datetime

import httpx
import pytest

from satyapramana_store.tender_intelligence import Decomposed, Unavailable
from satyapramana_store.tender_intelligence.groq import (
    GroqDecomposer, UnconfiguredDecomposer, _retry_delay_seconds,
)


class _FakeResponse:
    def __init__(self, status_code, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=request, response=self)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    monkeypatch.setattr("satyapramana_store.tender_intelligence.groq.time.sleep", lambda *_: None)


def _ok_response(content_obj):
    return _FakeResponse(200, payload={"choices": [{"message": {"content": json.dumps(content_obj)}}]})


def test_unconfigured_decomposer_is_honestly_unavailable():
    outcome = UnconfiguredDecomposer().decompose("irrelevant tender text")
    assert isinstance(outcome, Unavailable)
    assert "SATYAPRAMANA_GROQ_API_KEY" in outcome.reason


def test_groq_decomposer_parses_real_structured_output(monkeypatch):
    decomposer = GroqDecomposer(api_key="fake-key-for-test")
    payload = {"requirements": [
        {"text": "Bidder shall hold valid GST registration.", "page": 14,
         "obligation_guess": "mandatory", "suggested_field": "bidder.gst.status",
         "suggested_check": "exists", "note": "clause 4.1"},
        {"text": "ISO 9001 certification is preferred.", "page": 15,
         "obligation_guess": "desirable"},
    ]}
    monkeypatch.setattr("satyapramana_store.tender_intelligence.groq.httpx.post",
                         lambda *a, **kw: _ok_response(payload))

    outcome = decomposer.decompose("some real tender text")
    assert isinstance(outcome, Decomposed)
    assert len(outcome.proposals) == 2
    assert outcome.proposals[0].text == "Bidder shall hold valid GST registration."
    assert outcome.proposals[0].suggested_field == "bidder.gst.status"
    assert outcome.proposals[1].suggested_field is None
    assert isinstance(outcome.generated_at, datetime)


def test_groq_decomposer_accepts_a_bare_array_too(monkeypatch):
    """The system prompt asks for {"requirements": [...]}, but a model that
    ignores that instruction and returns a bare array shouldn't be treated
    as a hard failure when the array itself is perfectly usable."""
    decomposer = GroqDecomposer(api_key="fake-key-for-test")
    payload = [{"text": "A real one.", "page": 1, "obligation_guess": "mandatory"}]
    monkeypatch.setattr("satyapramana_store.tender_intelligence.groq.httpx.post",
                         lambda *a, **kw: _ok_response(payload))

    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Decomposed)
    assert len(outcome.proposals) == 1


def test_groq_decomposer_drops_malformed_candidates_rather_than_guessing(monkeypatch):
    decomposer = GroqDecomposer(api_key="fake-key-for-test")
    payload = {"requirements": [
        {"text": "A real one.", "page": 1, "obligation_guess": "mandatory"},
        {"text": "Missing a page number."},
    ]}
    monkeypatch.setattr("satyapramana_store.tender_intelligence.groq.httpx.post",
                         lambda *a, **kw: _ok_response(payload))

    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Decomposed)
    assert len(outcome.proposals) == 1
    assert outcome.proposals[0].text == "A real one."


def test_groq_decomposer_treats_invalid_json_as_unavailable(monkeypatch):
    decomposer = GroqDecomposer(api_key="fake-key-for-test")
    monkeypatch.setattr(
        "satyapramana_store.tender_intelligence.groq.httpx.post",
        lambda *a, **kw: _FakeResponse(200, payload={"choices": [{"message": {"content": "not json"}}]}))

    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Unavailable)
    assert "not valid JSON" in outcome.reason


def test_groq_decomposer_treats_an_empty_response_as_unavailable(monkeypatch):
    decomposer = GroqDecomposer(api_key="fake-key-for-test")
    monkeypatch.setattr(
        "satyapramana_store.tender_intelligence.groq.httpx.post",
        lambda *a, **kw: _FakeResponse(200, payload={"choices": [{"message": {"content": ""}}]}))

    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Unavailable)
    assert "empty" in outcome.reason


def test_groq_decomposer_degrades_honestly_on_a_persistent_provider_error(monkeypatch):
    decomposer = GroqDecomposer(api_key="fake-key-for-test")
    monkeypatch.setattr("satyapramana_store.tender_intelligence.groq.httpx.post",
                         lambda *a, **kw: _FakeResponse(402, text="prepayment credits depleted"))

    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Unavailable)
    assert "402" in outcome.reason


def test_groq_decomposer_retries_a_transient_503_before_succeeding(monkeypatch):
    decomposer = GroqDecomposer(api_key="fake-key-for-test")
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            return _FakeResponse(503, text="high demand")
        return _ok_response({"requirements": [
            {"text": "Recovered requirement.", "page": 1, "obligation_guess": "mandatory"},
        ]})
    monkeypatch.setattr("satyapramana_store.tender_intelligence.groq.httpx.post", flaky)

    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Decomposed)
    assert calls["n"] == 2


# --- retry delay: the real wait a 429 names, not a fixed guess -----------------
#
# Found live 2026-09-30: Groq's TPM limit is a rolling per-minute budget,
# not per-request -- chunking a large tender across many quick calls
# still hits it, and the real 429 named a ~10-30s wait. A fixed 2s retry
# just failed again immediately. Round 11 follow-up: honoring that real
# wait in full, across enough chunks and retries, wedged the whole shared
# service (a single-worker free-tier deployment) -- not just one request.
# _MAX_RETRY_DELAY_SECONDS caps it: a bounded honest failure beats an
# unbounded one that can take the whole deployment down with it.

def test_retry_delay_reads_the_real_wait_from_the_error_message_but_caps_it():
    resp = _FakeResponse(429, text='{"error":{"message":"Rate limit reached... '
                          'Please try again in 27.285s. Need more tokens?"}}')
    assert _retry_delay_seconds(resp) == 10.0


def test_retry_delay_prefers_the_retry_after_header_but_still_caps_it():
    resp = _FakeResponse(429, text="try again in 5s", headers={"retry-after": "12"})
    assert _retry_delay_seconds(resp) == 10.0


def test_retry_delay_under_the_cap_is_used_as_named():
    resp = _FakeResponse(429, text="...Please try again in 3.5s...")
    assert _retry_delay_seconds(resp) == pytest.approx(4.0, abs=0.01)


def test_retry_delay_falls_back_to_the_fixed_default_with_no_signal():
    resp = _FakeResponse(429, text="rate limited, no timing given")
    assert _retry_delay_seconds(resp) == 2


def test_groq_decomposer_waits_the_real_named_delay_not_a_fixed_guess(monkeypatch):
    """The retry actually uses _retry_delay_seconds()'s result, not the
    fixed fallback -- proven by asserting what time.sleep was called
    with, not just that a retry happened."""
    decomposer = GroqDecomposer(api_key="fake-key-for-test")
    slept = []
    monkeypatch.setattr("satyapramana_store.tender_intelligence.groq.time.sleep", slept.append)

    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResponse(429, text="...Please try again in 3.5s...")
        return _ok_response({"requirements": [
            {"text": "Recovered.", "page": 1, "obligation_guess": "mandatory"},
        ]})
    monkeypatch.setattr("satyapramana_store.tender_intelligence.groq.httpx.post", flaky)

    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Decomposed)
    assert slept == [pytest.approx(4.0, abs=0.01)]
