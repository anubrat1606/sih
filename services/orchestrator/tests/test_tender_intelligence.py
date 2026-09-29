"""Tender Intelligence (satyapramana.md section 5's AI/deterministic
boundary table, "decompose tender prose into atomic requirements" -- an
LLM-may capability). No test here makes a real network call to Gemini --
same principle as test_explain.py and test_sandbox_adapter.py: only
`.models.generate_content` is monkeypatched.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest
from google.genai import errors

from satyapramana_store.tender_intelligence import Decomposed, Unavailable, build_from_env
from satyapramana_store.tender_intelligence.gemini import (
    DEFAULT_MODEL, GeminiDecomposer, UnconfiguredDecomposer,
)
from satyapramana_store.tender_intelligence.groq import DEFAULT_MODEL as GROQ_DEFAULT_MODEL
from satyapramana_store.tender_intelligence.groq import GroqDecomposer


class _FakeResponse:
    def __init__(self, text):
        self.text = text


def test_unconfigured_decomposer_is_honestly_unavailable():
    outcome = UnconfiguredDecomposer().decompose("irrelevant tender text")
    assert isinstance(outcome, Unavailable)
    assert "not configured" in outcome.reason


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    """See test_explain.py's identical fixture -- every dispatcher test
    starts from neither provider configured, explicit rather than
    whatever leaked in from the environment the suite ran in."""
    monkeypatch.delenv("SATYAPRAMANA_GROQ_API_KEY", raising=False)
    monkeypatch.delenv("SATYAPRAMANA_GROQ_MODEL", raising=False)
    monkeypatch.delenv("SATYAPRAMANA_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("SATYAPRAMANA_GEMINI_MODEL", raising=False)


def test_build_from_env_without_any_key_is_unconfigured():
    outcome = build_from_env().decompose("irrelevant tender text")
    assert isinstance(outcome, Unavailable)
    assert "is not configured" in outcome.reason
    assert "GROQ" in outcome.reason and "GEMINI" in outcome.reason


def test_build_from_env_with_a_gemini_key_returns_a_configured_decomposer(monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_GEMINI_API_KEY", "fake-key-for-test")
    decomposer = build_from_env()
    assert isinstance(decomposer, GeminiDecomposer)
    assert decomposer._model == DEFAULT_MODEL


def test_build_from_env_prefers_groq_when_both_keys_are_set(monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("SATYAPRAMANA_GEMINI_API_KEY", "fake-gemini-key")
    assert isinstance(build_from_env(), GroqDecomposer)


def test_build_from_env_with_only_a_groq_key_returns_a_configured_groq_decomposer(monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_GROQ_API_KEY", "fake-groq-key")
    decomposer = build_from_env()
    assert isinstance(decomposer, GroqDecomposer)
    assert decomposer._model == GROQ_DEFAULT_MODEL


def test_gemini_decomposer_parses_real_structured_output():
    decomposer = GeminiDecomposer(api_key="fake-key-for-test")
    payload = [
        {"text": "Bidder shall hold valid GST registration.", "page": 14,
         "obligation_guess": "mandatory", "suggested_field": "bidder.gst.status",
         "suggested_check": "exists", "note": "clause 4.1"},
        {"text": "ISO 9001 certification is preferred.", "page": 15,
         "obligation_guess": "desirable"},
    ]
    decomposer._client.models.generate_content = lambda **kw: _FakeResponse(json.dumps(payload))
    outcome = decomposer.decompose("some real tender text")
    assert isinstance(outcome, Decomposed)
    assert len(outcome.proposals) == 2
    assert outcome.proposals[0].text == "Bidder shall hold valid GST registration."
    assert outcome.proposals[0].page == 14
    assert outcome.proposals[0].suggested_field == "bidder.gst.status"
    assert outcome.proposals[1].suggested_field is None  # never fabricated when the model didn't suggest one
    assert isinstance(outcome.generated_at, datetime)


def test_gemini_decomposer_drops_malformed_candidates_rather_than_guessing():
    decomposer = GeminiDecomposer(api_key="fake-key-for-test")
    payload = [
        {"text": "A real one.", "page": 1, "obligation_guess": "mandatory"},
        {"text": "Missing a page number."},  # dropped, not defaulted to page 1
    ]
    decomposer._client.models.generate_content = lambda **kw: _FakeResponse(json.dumps(payload))
    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Decomposed)
    assert len(outcome.proposals) == 1
    assert outcome.proposals[0].text == "A real one."


def test_gemini_decomposer_treats_invalid_json_as_unavailable_not_a_crash():
    decomposer = GeminiDecomposer(api_key="fake-key-for-test")
    decomposer._client.models.generate_content = lambda **kw: _FakeResponse("not json at all")
    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Unavailable)
    assert "JSON" in outcome.reason


def test_gemini_decomposer_treats_an_empty_response_as_unavailable():
    decomposer = GeminiDecomposer(api_key="fake-key-for-test")
    decomposer._client.models.generate_content = lambda **kw: _FakeResponse(None)
    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Unavailable)
    assert "empty" in outcome.reason


def test_gemini_decomposer_degrades_honestly_on_a_provider_error():
    decomposer = GeminiDecomposer(api_key="fake-key-for-test")

    def raise_it(**kw):
        raise errors.APIError(429, {"error": {"message": "rate limited", "status": "RESOURCE_EXHAUSTED"}})
    decomposer._client.models.generate_content = raise_it

    outcome = decomposer.decompose("text")
    assert isinstance(outcome, Unavailable)
    assert "429" in outcome.reason
