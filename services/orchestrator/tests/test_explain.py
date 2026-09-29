"""EXPLAIN (satyapramana.md section 2.2): the LLM narrator, never a judge.

No test here makes a real network call to Gemini -- the same principle the
sandbox adapter tests follow (test_sandbox_adapter.py's own docstring): this
mocks *our own test harness's* dependency on the network, never the
product's behaviour. `genai.Client(api_key=...)` itself does not touch the
network at construction time (confirmed empirically before writing these),
so only the one call each test cares about -- `.models.generate_content` --
is monkeypatched.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from google.genai import errors

from satyapramana_store.explain import Narrated, Unavailable, build_from_env
from satyapramana_store.explain.gemini import DEFAULT_MODEL, GeminiExplainer, UnconfiguredExplainer
from satyapramana_store.explain.groq import DEFAULT_MODEL as GROQ_DEFAULT_MODEL
from satyapramana_store.explain.groq import GroqExplainer


class _FakeResponse:
    def __init__(self, text):
        self.text = text


def test_unconfigured_explainer_is_honestly_unavailable_not_a_blank_narrative():
    outcome = UnconfiguredExplainer().narrate("irrelevant dossier text")
    assert isinstance(outcome, Unavailable)
    assert "not configured" in outcome.reason


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    """Every dispatcher test starts from neither provider configured --
    explicit, not whatever happened to be in the environment when the
    suite ran (round-11: a second provider, Groq, means a test that only
    clears the Gemini var can silently pass for the wrong reason if a
    Groq var leaks in from elsewhere)."""
    monkeypatch.delenv("SATYAPRAMANA_GROQ_API_KEY", raising=False)
    monkeypatch.delenv("SATYAPRAMANA_GROQ_MODEL", raising=False)
    monkeypatch.delenv("SATYAPRAMANA_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("SATYAPRAMANA_GEMINI_MODEL", raising=False)


def test_build_from_env_without_any_key_is_unconfigured():
    outcome = build_from_env().narrate("irrelevant dossier text")
    assert isinstance(outcome, Unavailable)
    assert "is not configured" in outcome.reason
    assert "GROQ" in outcome.reason and "GEMINI" in outcome.reason


def test_build_from_env_with_a_gemini_key_returns_a_configured_gemini_explainer(monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_GEMINI_API_KEY", "fake-key-for-test")
    explainer = build_from_env()
    assert isinstance(explainer, GeminiExplainer)
    assert explainer._model == DEFAULT_MODEL


def test_build_from_env_honours_a_gemini_model_override(monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setenv("SATYAPRAMANA_GEMINI_MODEL", "gemini-test-model")
    explainer = build_from_env()
    assert explainer._model == "gemini-test-model"


def test_build_from_env_prefers_groq_when_both_keys_are_set(monkeypatch):
    """Added round 11: Groq first, since that's the provider that actually
    works when Gemini's billing is the thing that's broken -- never a
    silent blend of both."""
    monkeypatch.setenv("SATYAPRAMANA_GROQ_API_KEY", "fake-groq-key")
    monkeypatch.setenv("SATYAPRAMANA_GEMINI_API_KEY", "fake-gemini-key")
    assert isinstance(build_from_env(), GroqExplainer)


def test_build_from_env_with_only_a_groq_key_returns_a_configured_groq_explainer(monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_GROQ_API_KEY", "fake-groq-key")
    explainer = build_from_env()
    assert isinstance(explainer, GroqExplainer)
    assert explainer._model == GROQ_DEFAULT_MODEL


def test_gemini_explainer_returns_the_providers_text_as_narrated():
    explainer = GeminiExplainer(api_key="fake-key-for-test", model="gemini-test-model")
    explainer._client.models.generate_content = lambda **kw: _FakeResponse("  A plain prose narrative.  ")
    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Narrated)
    assert outcome.narrative == "A plain prose narrative."
    assert outcome.model == "gemini-test-model"
    assert isinstance(outcome.generated_at, datetime)


def test_gemini_explainer_degrades_honestly_on_a_provider_error_never_a_crash():
    explainer = GeminiExplainer(api_key="fake-key-for-test")

    def raise_it(**kw):
        raise errors.APIError(401, {"error": {"message": "invalid API key", "status": "UNAUTHENTICATED"}})
    explainer._client.models.generate_content = raise_it

    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Unavailable)
    assert "401" in outcome.reason and "invalid API key" in outcome.reason


def test_gemini_explainer_treats_an_empty_response_as_unavailable_not_a_blank_narrative():
    explainer = GeminiExplainer(api_key="fake-key-for-test")
    explainer._client.models.generate_content = lambda **kw: _FakeResponse(None)
    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Unavailable)
    assert "empty" in outcome.reason
