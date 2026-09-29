import os

from .base import Explainer, ExplainOutcome, Narrated, Unavailable  # noqa: F401
from .gemini import GeminiExplainer, UnconfiguredExplainer  # noqa: F401
from .gemini import build_from_env as _gemini_build_from_env
from .groq import GroqExplainer  # noqa: F401
from .groq import build_from_env as _groq_build_from_env


class _NeitherConfiguredExplainer:
    """Only reached when neither provider's key is set -- names both env
    vars, unlike either provider module's own Unconfigured class, which
    only knows about its own."""

    def narrate(self, dossier_text: str) -> ExplainOutcome:
        return Unavailable(
            reason="SATYAPRAMANA_GROQ_API_KEY is not configured, and "
                   "neither is SATYAPRAMANA_GEMINI_API_KEY -- EXPLAIN is "
                   "unavailable; structured verdicts remain complete and "
                   "correct without it")


def build_from_env():
    """Provider preference: Groq first -- added 2026-09-29 after the team's
    Gemini key hit a real, unresolved GCP billing block (402 "prepayment
    credits depleted") the same day it first went live. Falls back to
    Gemini if a working key exists there instead, then honestly
    Unconfigured. Never both at once: one real narrative source per
    process, chosen once, never silently blended."""
    if os.environ.get("SATYAPRAMANA_GROQ_API_KEY"):
        return _groq_build_from_env()
    if os.environ.get("SATYAPRAMANA_GEMINI_API_KEY"):
        return _gemini_build_from_env()
    return _NeitherConfiguredExplainer()
