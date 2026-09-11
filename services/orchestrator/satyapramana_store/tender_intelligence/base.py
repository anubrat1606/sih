"""Tender Intelligence: satyapramana.md's AI/deterministic boundary table,
row "Decompose tender prose into atomic requirements" -- explicitly an
LLM-may capability. The boundary is drawn sharply on purpose: this module
produces *candidate* requirement text, an officer's own read of what the
model proposed, and nothing else. Nothing here ever becomes a rule pack
requirement, an evidence path, or a verdict without a human manually
building it in RulePackBuilder -- there is no code path from a
DecompositionResult to POST /tenders/{id}/rule-pack that skips a person.

Same shape as explain/base.py for the same reason: a provider-agnostic
Protocol, an honest Unavailable outcome, no evidentiary weight, nothing
written to the event log by this stage (a decomposition is regenerable at
will from the same source document and commits nothing).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ProposedRequirement:
    """A candidate, not a requirement. Every field here is the model's
    best guess, re-derived from the officer's own read of the source
    document before it becomes anything real."""
    text: str
    page: int
    obligation_guess: str  # "mandatory" | "desirable" -- a guess, never trusted as-is
    suggested_field: str | None = None
    suggested_check: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class Decomposed:
    proposals: tuple[ProposedRequirement, ...]
    model: str
    generated_at: datetime


@dataclass(frozen=True)
class Unavailable:
    reason: str


DecompositionOutcome = Decomposed | Unavailable


class Decomposer(Protocol):
    def decompose(self, document_text: str) -> DecompositionOutcome:
        """document_text is the tender PDF's own extracted text (real text,
        from the same deterministic text layer extraction already used
        elsewhere in this system -- never OCR'd or paraphrased before
        reaching the model)."""
        ...
