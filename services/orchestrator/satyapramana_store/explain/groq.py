"""Alternate EXPLAIN provider, added 2026-09-29 after the team's Gemini key
hit a real, unresolved GCP billing block (402 "prepayment credits
depleted") the same day it first went live. The locked stack's own
"provider-agnostic LLM/VLM abstraction; no provider SDK imported outside
the adapter" (satyapramana.md section 8) is exactly what makes this a
second small file rather than a rewrite -- app.py never changes, and
build_from_env() at the package root (__init__.py) decides which provider
to use.

Talks to Groq's OpenAI-compatible REST API directly via httpx (already a
dependency, used elsewhere in this codebase for DigiLocker) rather than
adding a whole second provider SDK for one endpoint.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import httpx

from .base import ExplainOutcome, Narrated, Unavailable

#: Free tier, no credit card required, confirmed 2026-09-29 -- an
#: OpenAI-compatible chat model served at real inference speed. Overridable
#: without a code change via SATYAPRAMANA_GROQ_MODEL, same reasoning as
#: explain/gemini.py's DEFAULT_MODEL comment.
DEFAULT_MODEL = "openai/gpt-oss-120b"

_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_RETRYABLE_STATUS = {429, 503}
_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 2

_SYSTEM_INSTRUCTION = (
    "You narrate an already-final bid-compliance decision for a procurement "
    "officer. You are a presentation layer, never a judge: every verdict, "
    "score, date, requirement id and reason code you are given is already "
    "final and correct. Restate them faithfully in clear, plain officer "
    "prose. Do not invent, infer, guess, or alter any fact, number, date, "
    "verdict or status that is not explicitly present in the input. Do not "
    "recommend a decision or express an opinion on whether the bidder "
    "should qualify -- that decision is not yours to make or imply."
)


class _RetryableHTTPError(Exception):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body}")


def _post_with_retry(api_key: str, payload: dict) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = httpx.post(
                _API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt == _MAX_ATTEMPTS - 1:
                raise
            time.sleep(_RETRY_DELAY_SECONDS)
            continue
        if response.status_code == 200:
            return response
        if response.status_code not in _RETRYABLE_STATUS or attempt == _MAX_ATTEMPTS - 1:
            response.raise_for_status()
        time.sleep(_RETRY_DELAY_SECONDS)
    raise last_exc  # pragma: no cover -- loop always returns or raises above


class GroqExplainer:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self._api_key = api_key
        self._model = model

    def narrate(self, dossier_text: str) -> ExplainOutcome:
        try:
            response = _post_with_retry(self._api_key, {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_INSTRUCTION},
                    {"role": "user", "content": dossier_text},
                ],
                "temperature": 0.1,
            })
        except httpx.HTTPStatusError as exc:
            return Unavailable(reason=f"HTTPStatusError ({exc.response.status_code}): {exc.response.text}")
        except httpx.HTTPError as exc:
            return Unavailable(reason=f"{type(exc).__name__}: {exc}")

        try:
            text = (response.json()["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, ValueError):
            return Unavailable(reason="the provider's response did not have the expected shape")
        if not text:
            return Unavailable(reason="the provider returned an empty response")
        return Narrated(narrative=text, model=self._model, generated_at=datetime.now(timezone.utc))


class UnconfiguredExplainer:
    """No credentials -- an honest, visible absence, not a mock narrative.
    Same reasoning as explain/gemini.py's own UnconfiguredExplainer."""

    def narrate(self, dossier_text: str) -> ExplainOutcome:
        return Unavailable(
            reason="SATYAPRAMANA_GROQ_API_KEY is not configured -- EXPLAIN "
                   "is unavailable; structured verdicts remain complete and "
                   "correct without it")


def build_from_env():
    key = os.environ.get("SATYAPRAMANA_GROQ_API_KEY")
    if not key:
        return UnconfiguredExplainer()
    model = os.environ.get("SATYAPRAMANA_GROQ_MODEL") or DEFAULT_MODEL
    return GroqExplainer(api_key=key, model=model)
