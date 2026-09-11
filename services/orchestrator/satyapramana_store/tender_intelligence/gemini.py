"""The only file in this package that imports a provider SDK -- same rule
as explain/gemini.py, same reason (satyapramana.md section 8: "provider-
agnostic LLM/VLM abstraction; no provider SDK imported outside the
adapter").
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from google import genai
from google.genai import errors, types

from .base import Decomposed, DecompositionOutcome, ProposedRequirement, Unavailable

DEFAULT_MODEL = "gemini-2.5-flash"

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
            response = self._client.models.generate_content(
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
