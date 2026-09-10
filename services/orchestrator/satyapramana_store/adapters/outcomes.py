"""Mapping adapter outcomes to leaf judgements.

This is the only place a Failure becomes a verdict, and it is deliberately
small enough to read in one sitting -- it is the boundary a judge or an auditor
will interrogate hardest.
"""
from __future__ import annotations

from datetime import date

from satyapramana.verdicts import Judgement, Reason, Verdict

from .base import Capability, Failure, FailureCode, Success


def failure_to_judgement(failure: Failure, capability: Capability) -> Judgement:
    """Every adapter failure becomes UNKNOWN at the leaf -- never FAIL, and
    never PASS. A source being down is not evidence against a bidder.

    The single exception: a capability whose register is complete and
    authoritative for its identifier space may declare not_found_is_negative,
    because absence there genuinely disproves existence. A PAN absent from the
    allotment register was never allotted. The declaration requires a written
    justification, which is rendered beside the resulting FAIL, because a
    finding derived from an absence is exactly what a bidder will contest.
    """
    if failure.code is FailureCode.NOT_FOUND and capability.not_found_is_negative:
        return Judgement(Verdict.FAIL, Reason.AUTHORITY_CONTRADICTED)
    return Judgement(Verdict.UNKNOWN, failure.code.reason)


class Freshness:
    FRESH = "FRESH"
    STALE = "STALE"
    EXPIRED = "EXPIRED"


def freshness(
    success: Success, capability: Capability, as_of: date, window_days: int | None = None
) -> str:
    """docs/ADAPTERS.md section 8.

    Age is measured from source_asserted_at where the authority gave one --
    what it says its answer is as of -- and only falls back to observed_at,
    when we asked. A status the authority last refreshed a fortnight ago is not
    made fresh by our having queried it this morning.
    """
    window = window_days or capability.freshness_days
    asserted = success.source_asserted_at or success.observed_at.date()
    age = (as_of - asserted).days
    if age <= window:
        return Freshness.FRESH
    if age <= 2 * window:
        return Freshness.STALE
    return Freshness.EXPIRED


def recency_factor(state: str, recency_floor: float, window_days: int, age_days: int) -> float:
    if state == Freshness.FRESH:
        return 1.0
    if state == Freshness.EXPIRED:
        return recency_floor
    # Linear decay to the floor across a second window of equal length.
    over = max(0, age_days - window_days)
    return 1.0 - (1.0 - recency_floor) * min(1.0, over / window_days)


def counts_as_covered(success: Success, capability: Capability, as_of: date) -> bool:
    """Verification Coverage counts only fresh, Tier A evidence. A stale
    verification is still shown and still real -- it simply stops counting as
    coverage, which is why the freshness clause lives inside the predicate."""
    from satyapramana.verdicts import Tier

    return (
        capability.tier is Tier.A
        and freshness(success, capability, as_of) == Freshness.FRESH
    )
