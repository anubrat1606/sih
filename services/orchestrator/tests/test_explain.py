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


class _FakeResponse:
    def __init__(self, text):
        self.text = text


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """The retry loop's short pause between attempts is real product
    behaviour worth having live; sitting through it for real in every test
    that exercises a retryable error would just slow the suite for no
    benefit -- only the wall-clock wait is faked here, not the retry count
    or the outcome."""
    monkeypatch.setattr("satyapramana_store.explain.gemini.time.sleep", lambda *_: None)


def test_unconfigured_explainer_is_honestly_unavailable_not_a_blank_narrative():
    outcome = UnconfiguredExplainer().narrate("irrelevant dossier text")
    assert isinstance(outcome, Unavailable)
    assert "not configured" in outcome.reason


def test_build_from_env_without_a_key_is_unconfigured(monkeypatch):
    monkeypatch.delenv("SATYAPRAMANA_GEMINI_API_KEY", raising=False)
    assert isinstance(build_from_env(), UnconfiguredExplainer)


def test_build_from_env_with_a_key_returns_a_configured_gemini_explainer(monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.delenv("SATYAPRAMANA_GEMINI_MODEL", raising=False)
    explainer = build_from_env()
    assert isinstance(explainer, GeminiExplainer)
    assert explainer._model == DEFAULT_MODEL


def test_build_from_env_honours_a_model_override(monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setenv("SATYAPRAMANA_GEMINI_MODEL", "gemini-test-model")
    explainer = build_from_env()
    assert explainer._model == "gemini-test-model"


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


def test_gemini_explainer_retries_a_transient_503_before_succeeding():
    """Found live 2026-09-29: the real Gemini key's first calls came back
    503 'high demand' -- the provider's own word that this is transient,
    not a real, permanent unavailability. A request that recovers on a
    later attempt should succeed, not fail on the first hiccup."""
    explainer = GeminiExplainer(api_key="fake-key-for-test")
    calls = {"n": 0}

    def flaky(**kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise errors.APIError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}})
        return _FakeResponse("Recovered narrative.")
    explainer._client.models.generate_content = flaky

    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Narrated)
    assert outcome.narrative == "Recovered narrative."
    assert calls["n"] == 3


def test_gemini_explainer_gives_up_after_max_retries_on_a_persistent_503():
    explainer = GeminiExplainer(api_key="fake-key-for-test")
    calls = {"n": 0}

    def always_503(**kw):
        calls["n"] += 1
        raise errors.APIError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}})
    explainer._client.models.generate_content = always_503

    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Unavailable)
    assert calls["n"] == 3
    assert "503" in outcome.reason


def test_gemini_explainer_does_not_retry_a_non_transient_error():
    """401/bad key, 404/retired model -- retrying changes nothing about a
    permanent failure, just delays the honest Unavailable an officer sees."""
    explainer = GeminiExplainer(api_key="fake-key-for-test")
    calls = {"n": 0}

    def raise_401(**kw):
        calls["n"] += 1
        raise errors.APIError(401, {"error": {"message": "invalid API key", "status": "UNAUTHENTICATED"}})
    explainer._client.models.generate_content = raise_401

    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Unavailable)
    assert calls["n"] == 1
