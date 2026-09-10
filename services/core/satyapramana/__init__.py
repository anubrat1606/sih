"""SATYAPRAMĀṆA core domain logic.

Pure, deterministic, framework-free. No I/O, no database, no HTTP, no model
calls. Everything here is exhaustively testable, and is tested that way.
"""
from .verdicts import (  # noqa: F401
    Channel, Judgement, Obligation, Reason, Tier, Verdict,
    all_of, any_of, apply_tier_ceiling, compose, compose_judgement, negate,
)
from .metrics import Constants, Metrics, RequirementResult, compute  # noqa: F401
from .risk import ConflictSignals, RiskAssessment, RiskLevel, classify  # noqa: F401
from .predicates import EvaluationContext, Resolved, evaluate  # noqa: F401

__all__ = [
    "Verdict", "Judgement", "Reason", "Tier", "Channel", "Obligation",
    "compose", "compose_judgement", "all_of", "any_of", "negate",
    "apply_tier_ceiling", "Constants", "Metrics", "RequirementResult", "compute",
    "RiskLevel", "RiskAssessment", "ConflictSignals", "classify",
    "EvaluationContext", "Resolved", "evaluate",
]
