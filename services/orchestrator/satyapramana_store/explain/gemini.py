"""The only file in this package that imports a provider SDK -- the locked
stack calls for a "provider-agnostic LLM/VLM abstraction; no provider SDK
imported outside the adapter" (satyapramana.md section 8), and Explainer
(base.py) is that abstraction. Swapping Gemini for another provider later
means writing one more file like this one, never touching app.py or
reporting/dossier.py.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from google import genai
from google.genai import errors, types

from .base import ExplainOutcome, Narrated, Unavailable

#: A 503 ("high demand", confirmed live 2026-09-29 the same day the Gemini
#: key was first configured) or a 429 (rate limit) is the provider's own
#: word that this is transient, not a real, permanent unavailability like a
#: bad key or a retired model -- worth one short retry loop before
#: degrading, since a single hiccup shouldn't permanently fail a request
#: the provider itself says is temporary.
_RETRYABLE_CODES = {429, 503}
_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 2


def _generate_with_retry(client, **kwargs):
    last_exc = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return client.models.generate_content(**kwargs)
        except errors.APIError as exc:
            last_exc = exc
            if getattr(exc, "code", None) not in _RETRYABLE_CODES or attempt == _MAX_ATTEMPTS - 1:
                raise
            time.sleep(_RETRY_DELAY_SECONDS)
    raise last_exc  # pragma: no cover -- loop always returns or raises above

#: Overridable without a code change -- by the time real credentials exist,
#: a newer model id may be current. Never guessed at call time; a stale
#: default just means an officer sees an honest Unavailable from the
#: provider, never a silently wrong model. Confirmed live 2026-09-29:
#: "gemini-2.5-flash" was deprecated (404 NOT_FOUND) after the Gemini key
#: was first configured on the real deployment, caught by the honest
#: Unavailable degrade doing exactly its job, not by a guess.
DEFAULT_MODEL = "gemini-3.8-flash"

_SYSTEM_INSTRUCTION = (
    "You narrate an already-final bid-compliance decision for a procurement "
    "officer. You are a presentation layer, never a judge: every verdict, "
    "score, date, requirement id and reason code you are given is already "
    "final and correct. Restate them faithfully in clear, plain officer "
    "prose. Do not invent, infer, guess, or alter any fact, number, date, "
    "verdict or status that is not explicitly present in the input. Do not "
    "soften a FAIL or a blocking finding, and do not add a recommendation or "
    "caveat beyond what the input itself states. Where the input says a "
    "value was not determined, say it was not determined -- never substitute "
    "a plausible-sounding guess. Write 150-300 words of plain prose, no "
    "markdown, no bullet points."
)


class GeminiExplainer:
    """`conn` never appears here on purpose -- see base.py: narration is
    never archived to the event log, so there is nothing to pass a database
    connection for."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def narrate(self, dossier_text: str) -> ExplainOutcome:
        try:
            response = _generate_with_retry(
                self._client,
                model=self._model,
                contents=dossier_text,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTION,
                    temperature=0.1,
                ),
            )
        except errors.APIError as exc:
            # Every provider failure -- bad key, rate limit, outage, a
            # retired model id -- degrades to Unavailable with the real
            # detail. None of them fabricate a narrative, and none of them
            # touch the structured verdict this is narrating.
            return Unavailable(reason=f"{type(exc).__name__} ({getattr(exc, 'code', '?')}): {exc}")

        text = (response.text or "").strip()
        if not text:
            return Unavailable(reason="the provider returned an empty response")
        return Narrated(narrative=text, model=self._model, generated_at=datetime.now(timezone.utc))


class UnconfiguredExplainer:
    """No credentials -- an honest, visible absence, not a mock narrative.
    Mirrors adapters/registry.py's UnconfiguredAdapter for the same reason:
    "we have not configured this yet" is a different fact from "no source
    exists," and an officer deserves to be told which."""

    def narrate(self, dossier_text: str) -> ExplainOutcome:
        return Unavailable(
            reason="SATYAPRAMANA_GEMINI_API_KEY is not configured -- EXPLAIN "
                   "is unavailable; structured verdicts remain complete and "
                   "correct without it")


def build_from_env():
    key = os.environ.get("SATYAPRAMANA_GEMINI_API_KEY")
    if not key:
        return UnconfiguredExplainer()
    # `or`, not a dict default: a `.env` line left blank (KEY=) still exports
    # an empty string, which a plain .get(..., DEFAULT_MODEL) would not catch.
    model = os.environ.get("SATYAPRAMANA_GEMINI_MODEL") or DEFAULT_MODEL
    return GeminiExplainer(api_key=key, model=model)
