"""Alternate Tender Intelligence provider -- see explain/groq.py's own
docstring for why this exists and why it's a second small file rather than
a rewrite. Same Groq REST API, same retry shape, same honest-degrade
contract as tender_intelligence/gemini.py; only the request/response shape
differs (Groq's OpenAI-compatible json_object mode returns a single JSON
object, not a bare array, so the model is asked for one and the array is
read back out of it).
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone

import httpx

from .base import Decomposed, DecompositionOutcome, ProposedRequirement, Unavailable

#: See explain/groq.py's own DEFAULT_MODEL comment -- same reasoning.
DEFAULT_MODEL = "openai/gpt-oss-120b"

_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_RETRYABLE_STATUS = {429, 503}
#: Confirmed live 2026-09-30: this endpoint runs synchronously on a
#: shared, single-worker free-tier deployment (satyapramana_store/app.py's
#: decompose_tender). Honoring a real 429's full named wait (seen up to
#: ~27-30s) across enough attempts and chunks genuinely wedged the whole
#: service, not just one request -- /health itself started 503ing for
#: every user until a manual restart. _MAX_ATTEMPTS and
#: _MAX_RETRY_DELAY_SECONDS are deliberately tight: bounding this
#: process's worst case protects shared infrastructure, which matters
#: more here than maximizing any single request's odds of full success --
#: a bounded honest failure beats an unbounded one that can take the
#: whole deployment down with it.
_MAX_ATTEMPTS = 2
_RETRY_DELAY_SECONDS = 2
_MAX_RETRY_DELAY_SECONDS = 10.0
_RETRY_AFTER_RE = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)
#: Real successful calls take a few seconds (confirmed live); 60s let one
#: hung call eat most of the whole request's safety budget by itself.
_REQUEST_TIMEOUT_SECONDS = 20.0


def _retry_delay_seconds(response: httpx.Response) -> float:
    """Groq's own Retry-After header, if present; otherwise the real wait
    named in the 429 body text ("...try again in 27.285s..."), confirmed
    live; otherwise the fixed fallback. A small buffer is added since the
    provider's own clock and ours are never perfectly in sync. Capped --
    see _MAX_ATTEMPTS's own comment on why this stays bounded rather than
    honoring an arbitrarily long real wait."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return min(float(header) + 0.5, _MAX_RETRY_DELAY_SECONDS)
        except ValueError:
            pass
    match = _RETRY_AFTER_RE.search(response.text or "")
    if match:
        return min(float(match.group(1)) + 0.5, _MAX_RETRY_DELAY_SECONDS)
    return _RETRY_DELAY_SECONDS

_SYSTEM_INSTRUCTION = (
    "You read a government tender document and propose candidate compliance "
    "requirements for a procurement officer to review. You are a proposer, "
    "never a decision-maker: every requirement you list is a candidate the "
    "officer will verify against the source text themselves before it "
    "becomes real. Quote or closely paraphrase the tender's own language for "
    "each requirement's text -- do not invent requirements the document does "
    "not state. For each one, name the page it appears on, guess whether it "
    "reads as mandatory or desirable, and if it plausibly maps to one of "
    "these evidence paths, suggest it: bidder.gst.status, "
    "bidder.gst.date_of_expiry, bidder.pan.status, bidder.entity.cin, "
    "bidder.entity.status, bidder.udyam.status. If none fits, leave the "
    "suggestion out rather than guessing. Do not compute, determine, or "
    "assert whether any bidder satisfies any requirement -- that is not "
    "your job here. Respond with a single JSON object of the exact shape "
    '{"requirements": [{"text": str, "page": int, '
    '"obligation_guess": "mandatory"|"desirable", "suggested_field": str '
    '(optional), "suggested_check": "exists"|"eq"|"date_after"|"date_before" '
    '(optional), "note": str (optional)}]} -- nothing else, no prose '
    "before or after the JSON."
)


def _post_with_retry(api_key: str, payload: dict) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = httpx.post(
                _API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=_REQUEST_TIMEOUT_SECONDS,
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
        time.sleep(_retry_delay_seconds(response))
    raise last_exc  # pragma: no cover -- loop always returns or raises above


class GroqDecomposer:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self._api_key = api_key
        self._model = model

    def decompose(self, document_text: str) -> DecompositionOutcome:
        try:
            response = _post_with_retry(self._api_key, {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_INSTRUCTION},
                    {"role": "user", "content": document_text},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
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

        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return Unavailable(reason="the provider's response was not valid JSON -- refusing to guess at candidates from it")

        items = parsed.get("requirements") if isinstance(parsed, dict) else parsed
        if not isinstance(items, list):
            return Unavailable(reason="the provider's JSON did not contain a requirements array -- refusing to guess at candidates from it")

        proposals = tuple(
            ProposedRequirement(
                text=item["text"], page=int(item["page"]),
                obligation_guess=item["obligation_guess"],
                suggested_field=item.get("suggested_field"),
                suggested_check=item.get("suggested_check"),
                note=item.get("note"),
            )
            for item in items
            if isinstance(item, dict) and "text" in item and "page" in item and "obligation_guess" in item
        )
        return Decomposed(proposals=proposals, model=self._model,
                          generated_at=datetime.now(timezone.utc))


class UnconfiguredDecomposer:
    def decompose(self, document_text: str) -> DecompositionOutcome:
        return Unavailable(
            reason="SATYAPRAMANA_GROQ_API_KEY is not configured -- Tender "
                   "Intelligence is unavailable; requirements can still be "
                   "entered by hand in the rule pack builder")


def build_from_env():
    key = os.environ.get("SATYAPRAMANA_GROQ_API_KEY")
    if not key:
        return UnconfiguredDecomposer()
    model = os.environ.get("SATYAPRAMANA_GROQ_MODEL") or DEFAULT_MODEL
    return GroqDecomposer(api_key=key, model=model)
