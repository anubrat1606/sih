"""EXPLAIN: satyapramana.md section 2.2 -- "an LLM renders the already-final
decision into officer-readable prose. It is a narrator, not a judge. It
receives the verdict and the evidence chain as input and may not alter
either. If the explainer is unavailable, the system still returns complete,
correct, structured verdicts -- the prose is a presentation layer, not a
dependency."

This module's whole job is turning an already-computed Compliance Dossier
(reporting/dossier.py) into prose -- never raw evidence, never with access to
a rule pack, never returning anything that could be mistaken for a verdict.
Nothing here writes to the event log: prose is regenerable at will from the
same dossier and carries no evidentiary weight of its own, so there is
nothing here that needs to survive as a permanent fact the way a verdict or
an extraction does.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Narrated:
    narrative: str
    model: str
    generated_at: datetime


@dataclass(frozen=True)
class Unavailable:
    """Never a fallback narrative -- the honest, visible absence of one, with
    why. A blank prose field would look like a bug; this looks like what it
    is."""
    reason: str


ExplainOutcome = Narrated | Unavailable


class Explainer(Protocol):
    def narrate(self, dossier_text: str) -> ExplainOutcome:
        """`dossier_text` is reporting/dossier.py's render_dossier_text() --
        the same plain-text rendering an officer could print. Never the raw
        dossier dict and never anything from the event log directly: the
        narrator sees exactly what a human reviewer would, nothing more."""
        ...
