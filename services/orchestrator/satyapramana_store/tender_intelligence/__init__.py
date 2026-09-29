import os

from .base import Decomposed, Decomposer, DecompositionOutcome, ProposedRequirement, Unavailable  # noqa: F401
from .gemini import GeminiDecomposer, UnconfiguredDecomposer  # noqa: F401
from .gemini import build_from_env as _gemini_build_from_env
from .groq import GroqDecomposer  # noqa: F401
from .groq import build_from_env as _groq_build_from_env


class _NeitherConfiguredDecomposer:
    """See explain/__init__.py's identical class -- names both env vars,
    unlike either provider module's own Unconfigured class."""

    def decompose(self, document_text: str) -> DecompositionOutcome:
        return Unavailable(
            reason="SATYAPRAMANA_GROQ_API_KEY is not configured, and "
                   "neither is SATYAPRAMANA_GEMINI_API_KEY -- Tender "
                   "Intelligence is unavailable; requirements can still be "
                   "entered by hand in the rule pack builder")


def build_from_env():
    """See explain/__init__.py's identical dispatcher -- same reasoning,
    same provider preference order."""
    if os.environ.get("SATYAPRAMANA_GROQ_API_KEY"):
        return _groq_build_from_env()
    if os.environ.get("SATYAPRAMANA_GEMINI_API_KEY"):
        return _gemini_build_from_env()
    return _NeitherConfiguredDecomposer()
