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
from satyapramana_store.tender_intelligence.groq import GroqDecomposer, UnconfiguredDecomposer


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

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
        if calls["n"] < 3:
            return _FakeResponse(503, text="high demand")
        return _ok_response({"requirements": [
            {"text": "Recovered requirement.", "page": 1, "obligation_guess": "mandatory"},
        ]})
    monkeypatch.setattr("satyapramana_store.tender_intelligence.groq.httpx.post", flaky)

    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Decomposed)
    assert calls["n"] == 3
