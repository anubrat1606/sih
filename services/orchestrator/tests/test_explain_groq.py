"""GroqExplainer: the alternate EXPLAIN provider (round 11, added after the
team's Gemini key hit a real, unresolved GCP billing block). Same
no-real-network-call principle as test_explain.py's own docstring -- only
`httpx.post` is monkeypatched, never a real call to Groq.
"""
from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from satyapramana_store.explain import Narrated, Unavailable
from satyapramana_store.explain.groq import GroqExplainer, UnconfiguredExplainer, _retry_delay_seconds


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
    """See test_explain.py's identical fixture for gemini.py -- only the
    wall-clock wait is faked, not the retry count or the outcome."""
    monkeypatch.setattr("satyapramana_store.explain.groq.time.sleep", lambda *_: None)


def _ok_response(text):
    return _FakeResponse(200, payload={"choices": [{"message": {"content": text}}]})


def test_unconfigured_explainer_is_honestly_unavailable_not_a_blank_narrative():
    outcome = UnconfiguredExplainer().narrate("irrelevant dossier text")
    assert isinstance(outcome, Unavailable)
    assert "SATYAPRAMANA_GROQ_API_KEY" in outcome.reason


def test_groq_explainer_returns_the_providers_text_as_narrated(monkeypatch):
    explainer = GroqExplainer(api_key="fake-key-for-test", model="groq-test-model")
    monkeypatch.setattr("satyapramana_store.explain.groq.httpx.post",
                         lambda *a, **kw: _ok_response("  A plain prose narrative.  "))

    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Narrated)
    assert outcome.narrative == "A plain prose narrative."
    assert outcome.model == "groq-test-model"
    assert isinstance(outcome.generated_at, datetime)


def test_groq_explainer_treats_an_empty_response_as_unavailable(monkeypatch):
    explainer = GroqExplainer(api_key="fake-key-for-test")
    monkeypatch.setattr("satyapramana_store.explain.groq.httpx.post",
                         lambda *a, **kw: _ok_response(""))

    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Unavailable)
    assert "empty" in outcome.reason


def test_groq_explainer_treats_an_unexpected_response_shape_as_unavailable(monkeypatch):
    explainer = GroqExplainer(api_key="fake-key-for-test")
    monkeypatch.setattr("satyapramana_store.explain.groq.httpx.post",
                         lambda *a, **kw: _FakeResponse(200, payload={"unexpected": "shape"}))

    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Unavailable)
    assert "expected shape" in outcome.reason


def test_groq_explainer_retries_a_transient_503_before_succeeding(monkeypatch):
    """Found live 2026-09-29, same real finding as the Gemini key's --
    matching test_explain.py's twin for the Gemini provider."""
    explainer = GroqExplainer(api_key="fake-key-for-test")
    calls = {"n": 0}

    def flaky(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 2:
            return _FakeResponse(503, text="high demand")
        return _ok_response("Recovered narrative.")
    monkeypatch.setattr("satyapramana_store.explain.groq.httpx.post", flaky)

    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Narrated)
    assert outcome.narrative == "Recovered narrative."


# --- retry delay: see tender_intelligence/groq.py's identical tests -----------
#
# Round 11 follow-up: the real named wait is capped, not honored in full --
# see _MAX_RETRY_DELAY_SECONDS's own comment for the real incident
# (honoring an uncapped wait wedged the whole shared service).

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


def test_groq_explainer_gives_up_after_max_retries_on_a_persistent_503(monkeypatch):
    explainer = GroqExplainer(api_key="fake-key-for-test")
    calls = {"n": 0}

    def always_503(*a, **kw):
        calls["n"] += 1
        return _FakeResponse(503, text="high demand")
    monkeypatch.setattr("satyapramana_store.explain.groq.httpx.post", always_503)

    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Unavailable)
    assert calls["n"] == 2
    assert "503" in outcome.reason


def test_groq_explainer_does_not_retry_a_non_transient_error(monkeypatch):
    """401/bad key, 402/billing -- retrying changes nothing about a
    permanent failure, just delays the honest Unavailable an officer sees."""
    explainer = GroqExplainer(api_key="fake-key-for-test")
    calls = {"n": 0}

    def raise_401(*a, **kw):
        calls["n"] += 1
        return _FakeResponse(401, text="invalid API key")
    monkeypatch.setattr("satyapramana_store.explain.groq.httpx.post", raise_401)

    outcome = explainer.narrate("dossier text")
    assert isinstance(outcome, Unavailable)
    assert calls["n"] == 1
    assert "401" in outcome.reason
