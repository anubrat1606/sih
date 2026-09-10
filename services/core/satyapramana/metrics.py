"""The three orthogonal metrics.

docs/VERDICT_ALGEBRA.md section 5. Computed independently and never averaged,
never blended into a badge. A bid at 100/40/60 is a materially different
procurement risk from one at 100/95/95, and fusing them destroys the exact
information an auditor needs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .verdicts import Channel, Obligation, Tier, Verdict

TIER_FACTOR = {Tier.A: 1.00, Tier.B: 0.70, Tier.C: 0.40}
CHANNEL_FACTOR = {Channel.DIRECT: 1.00, Channel.AGGREGATOR: 0.85}

DETERMINATE = (Verdict.PASS, Verdict.FAIL, Verdict.PARTIAL)


@dataclass(frozen=True)
class Constants:
    """Tunables. Declared in the rule pack, never hard-coded, so that every
    verdict can be attributed to an exact configuration."""
    partial_credit: float = 0.50
    w_mandatory: float = 1.00
    w_desirable: float = 0.30
    recency_floor: float = 0.50
    corroboration_step: float = 0.10
    coverage_floor_high: float = 50.0
    coverage_floor_medium: float = 80.0
    confidence_floor: float = 70.0


@dataclass(frozen=True)
class RequirementResult:
    """One evaluated requirement, as the metrics layer sees it."""
    requirement_id: str
    verdict: Verdict
    obligation: Obligation
    #: True only when at least one supporting item is Tier A AND within its
    #: freshness window. A stale verification does not count as covered.
    covered: bool = False
    tier: Tier | None = None
    channel: Channel | None = None
    #: MIN extraction confidence across every field feeding this requirement --
    #: weakest link, not mean. A doubtful field can still be the wrong one.
    extraction_confidence: float = 1.0
    recency_factor: float = 1.0
    independent_sources: int = 1

    @property
    def determinate(self) -> bool:
        return self.verdict in DETERMINATE


@dataclass(frozen=True)
class Metrics:
    """Three figures. Deliberately no fourth.

    There is no `overall`, no `trust_score`, no `blended`. If you find yourself
    wanting one, docs/VERDICT_ALGEBRA.md section 5 explains why it destroys the
    information the officer needs. tests/test_metrics.py enforces the absence.
    """
    compliance_score: float | None
    verification_coverage: float
    verification_coverage_mandatory: float | None
    evidence_confidence: float | None


def _credit(v: Verdict, c: Constants) -> float:
    return {Verdict.PASS: 1.0, Verdict.PARTIAL: c.partial_credit, Verdict.FAIL: 0.0}[v]


def _weight(o: Obligation, c: Constants) -> float:
    return c.w_mandatory if o is Obligation.MANDATORY else c.w_desirable


def compliance_score(
    results: Sequence[RequirementResult], c: Constants
) -> float | None:
    """Of the requirements we could determine, how many are satisfied?

    Returns None -- never 0.0 -- when nothing is determinate. A zero reads as
    "totally non-compliant" when the truth is "nothing could be checked", and
    that specific confusion is what this whole design exists to prevent. Every
    renderer must show an em dash for None and never a numeral.
    """
    determinate = [r for r in results if r.determinate]
    denominator = sum(_weight(r.obligation, c) for r in determinate)
    if denominator == 0:
        return None
    numerator = sum(
        _weight(r.obligation, c) * _credit(r.verdict, c) for r in determinate
    )
    return 100.0 * numerator / denominator


def verification_coverage(results: Sequence[RequirementResult]) -> float:
    """What fraction was checked against an authority at all?

    The denominator is ALL requirements, including UNKNOWN ones. That is the
    entire point: it is what keeps the unverified remainder visible.
    """
    if not results:
        return 0.0
    return 100.0 * sum(1 for r in results if r.covered) / len(results)


def verification_coverage_mandatory(
    results: Sequence[RequirementResult],
) -> float | None:
    mandatory = [r for r in results if r.obligation is Obligation.MANDATORY]
    if not mandatory:
        return None
    return 100.0 * sum(1 for r in mandatory if r.covered) / len(mandatory)


def requirement_confidence(r: RequirementResult, c: Constants) -> float:
    """Multiplicative, capped at 1.0. docs/VERDICT_ALGEBRA.md section 5.3."""
    tier = TIER_FACTOR[r.tier] if r.tier is not None else TIER_FACTOR[Tier.C]
    channel = CHANNEL_FACTOR[r.channel] if r.channel is not None else 1.0
    corroboration = 1.0 + c.corroboration_step * max(0, r.independent_sources - 1)
    return min(
        tier * channel * r.extraction_confidence * r.recency_factor * corroboration,
        1.0,
    )


def evidence_confidence(
    results: Sequence[RequirementResult], c: Constants
) -> float | None:
    determinate = [r for r in results if r.determinate]
    if not determinate:
        return None
    return 100.0 * sum(requirement_confidence(r, c) for r in determinate) / len(
        determinate
    )


def compute(results: Sequence[RequirementResult], c: Constants) -> Metrics:
    return Metrics(
        compliance_score=compliance_score(results, c),
        verification_coverage=verification_coverage(results),
        verification_coverage_mandatory=verification_coverage_mandatory(results),
        evidence_confidence=evidence_confidence(results, c),
    )
