"""The only file in this package that imports a provider SDK -- same rule
as explain/gemini.py, same reason (satyapramana.md section 8: "provider-
agnostic LLM/VLM abstraction; no provider SDK imported outside the
adapter").
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from google import genai
from google.genai import errors, types

from .base import Decomposed, DecompositionOutcome, ProposedRequirement, Unavailable

#: See explain/gemini.py's own comment on this same helper -- identical
#: reasoning, kept as a second small copy rather than a shared import,
#: matching how the rest of this file already mirrors that one (same
#: DEFAULT_MODEL, same try/except-to-Unavailable shape).
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

#: See explain/gemini.py's own DEFAULT_MODEL comment -- same constant,
#: same real 404 that surfaced it, same fix.
DEFAULT_MODEL = "gemini-3.8-flash"

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
    "your job here."
)

_RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "text": {"type": "STRING"},
            "page": {"type": "INTEGER"},
            "obligation_guess": {"type": "STRING", "enum": ["mandatory", "desirable"]},
            "suggested_field": {"type": "STRING"},
            "suggested_check": {"type": "STRING",
                                "enum": ["exists", "eq", "date_after", "date_before"]},
            "note": {"type": "STRING"},
        },
        "required": ["text", "page", "obligation_guess"],
    },
}


class GeminiDecomposer:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def decompose(self, document_text: str) -> DecompositionOutcome:
        try:
            response = _generate_with_retry(
                self._client,
                model=self._model,
                contents=document_text,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTION,
                    temperature=0.1,
                    response_mime_type="application/json",
                    response_schema=_RESPONSE_SCHEMA,
                ),
            )
        except errors.APIError as exc:
            return Unavailable(reason=f"{type(exc).__name__} ({getattr(exc, 'code', '?')}): {exc}")

        text = (response.text or "").strip()
        if not text:
            return Unavailable(reason="the provider returned an empty response")

        import json
        try:
            items = json.loads(text)
        except (ValueError, TypeError):
            return Unavailable(reason="the provider's response was not valid JSON -- refusing to guess at candidates from it")

        proposals = tuple(
            ProposedRequirement(
                text=item["text"], page=int(item["page"]),
                obligation_guess=item["obligation_guess"],
                suggested_field=item.get("suggested_field"),
                suggested_check=item.get("suggested_check"),
                note=item.get("note"),
            )
            for item in items if "text" in item and "page" in item and "obligation_guess" in item
        )
        return Decomposed(proposals=proposals, model=self._model,
                          generated_at=datetime.now(timezone.utc))


class UnconfiguredDecomposer:
    def decompose(self, document_text: str) -> DecompositionOutcome:
        return Unavailable(
            reason="SATYAPRAMANA_GEMINI_API_KEY is not configured -- Tender "
                   "Intelligence is unavailable; requirements can still be "
                   "entered by hand in the rule pack builder")


def build_from_env():
    key = os.environ.get("SATYAPRAMANA_GEMINI_API_KEY")
    if not key:
        return UnconfiguredDecomposer()
    model = os.environ.get("SATYAPRAMANA_GEMINI_MODEL") or DEFAULT_MODEL
    return GeminiDecomposer(api_key=key, model=model)
