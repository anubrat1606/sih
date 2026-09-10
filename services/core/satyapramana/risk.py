"""Risk classification -- a deterministic function of the three metrics plus
conflict signals. Never a model's opinion. docs/VERDICT_ALGEBRA.md section 6.

Versioned exactly like a rule pack: every RISK_FUNCTION_VERSION bump is recorded
on the RISK_CLASSIFIED event, so a classification can always be reproduced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from .metrics import Constants, Metrics, RequirementResult
from .verdicts import Obligation, Tier, Verdict

RISK_FUNCTION_VERSION = "1.0.0"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class ConflictSignals:
    identifier_conflict: bool = False
    collusion_edge: bool = False
    mandatory_document_expired: bool = False
    stale_verification: bool = False
    #: Requirement ids whose only support is Tier C evidence.
    self_declared_mandatory: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskAssessment:
    level: RiskLevel
    triggers: tuple[str, ...]
    function_version: str = RISK_FUNCTION_VERSION


def classify(
    results: Sequence[RequirementResult],
    metrics: Metrics,
    signals: ConflictSignals,
    c: Constants,
) -> RiskAssessment:
    """Evaluated in order; first matching band wins. All triggers are reported,
    not just the first, because an officer needs the whole picture."""
    mandatory = [r for r in results if r.obligation is Obligation.MANDATORY]

    high: list[str] = []
    if any(r.verdict is Verdict.FAIL for r in mandatory):
        high.append("mandatory requirement failed")
    # A mandatory UNKNOWN is HIGH risk deliberately. "We could not verify a
    # mandatory requirement" is a serious procurement risk even though it is not
    # a compliance failure -- this is where UNKNOWN != FAIL while still being
    # taken seriously.
    if any(r.verdict is Verdict.UNKNOWN for r in mandatory):
        high.append("mandatory requirement unverified")
    if signals.identifier_conflict:
        high.append("identifier conflict")
    if signals.collusion_edge:
        high.append("collusion link to another bidder on this tender")
    if signals.mandatory_document_expired:
        high.append("mandatory document expired at the bid submission date")
    cm = metrics.verification_coverage_mandatory
    if cm is not None and cm < c.coverage_floor_high:
        high.append(f"mandatory coverage {cm:.0f}% below {c.coverage_floor_high:.0f}%")
    if high:
        return RiskAssessment(RiskLevel.HIGH, tuple(high))

    medium: list[str] = []
    if any(r.verdict is Verdict.PARTIAL for r in mandatory):
        medium.append("mandatory requirement partially satisfied")
    if signals.self_declared_mandatory:
        medium.append(
            "mandatory requirement resting solely on self-declaration: "
            + ", ".join(signals.self_declared_mandatory)
        )
    if cm is not None and cm < c.coverage_floor_medium:
        medium.append(f"mandatory coverage {cm:.0f}% below {c.coverage_floor_medium:.0f}%")
    ec = metrics.evidence_confidence
    if ec is not None and ec < c.confidence_floor:
        medium.append(f"evidence confidence {ec:.0f}% below {c.confidence_floor:.0f}%")
    if any(
        r.verdict is Verdict.FAIL
        for r in results
        if r.obligation is Obligation.DESIRABLE
    ):
        medium.append("desirable requirement failed")
    if signals.stale_verification:
        medium.append("verification outside its freshness window")
    if medium:
        return RiskAssessment(RiskLevel.MEDIUM, tuple(medium))

    return RiskAssessment(RiskLevel.LOW, ())
