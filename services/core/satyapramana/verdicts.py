"""Verdict algebra -- the semantic centre of the product.

Implements docs/VERDICT_ALGEBRA.md exactly. Every property claimed in that
document is asserted exhaustively in tests/test_verdicts.py.

Nothing here touches evidence, documents or authorities. It is pure algebra over
four states, which is what makes it exhaustively testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class Obligation(str, Enum):
    MANDATORY = "mandatory"
    DESIRABLE = "desirable"


class Tier(str, Enum):
    """Evidentiary tier. See docs/VERDICT_ALGEBRA.md section 3."""
    A = "A"  # authority-verifiable
    B = "B"  # issuer-attested
    C = "C"  # self-declared


class Channel(str, Enum):
    DIRECT = "DIRECT"          # the authority's own API
    AGGREGATOR = "AGGREGATOR"  # a licensed intermediary relaying it


class Reason(str, Enum):
    # PASS
    AUTHORITY_CONFIRMED = "AUTHORITY_CONFIRMED"
    CORROBORATED_MULTI_SOURCE = "CORROBORATED_MULTI_SOURCE"
    THRESHOLD_MET = "THRESHOLD_MET"
    # FAIL
    AUTHORITY_CONTRADICTED = "AUTHORITY_CONTRADICTED"
    IDENTIFIER_MISMATCH = "IDENTIFIER_MISMATCH"
    THRESHOLD_NOT_MET = "THRESHOLD_NOT_MET"
    DOCUMENT_EXPIRED = "DOCUMENT_EXPIRED"
    MANDATORY_DOCUMENT_ABSENT = "MANDATORY_DOCUMENT_ABSENT"
    REGISTRATION_INACTIVE = "REGISTRATION_INACTIVE"
    SUBREQUIREMENT_UNREACHABLE = "SUBREQUIREMENT_UNREACHABLE"
    # PARTIAL
    SELF_DECLARED_CEILING = "SELF_DECLARED_CEILING"
    SUBSET_SATISFIED = "SUBSET_SATISFIED"
    CORROBORATION_INCOMPLETE = "CORROBORATION_INCOMPLETE"
    STALE_VERIFICATION = "STALE_VERIFICATION"
    # UNKNOWN
    AUTHORITY_UNAVAILABLE = "AUTHORITY_UNAVAILABLE"
    AUTHORITY_RATE_LIMITED = "AUTHORITY_RATE_LIMITED"
    AUTHORITY_NOT_FOUND = "AUTHORITY_NOT_FOUND"
    AUTHORITY_AMBIGUOUS = "AUTHORITY_AMBIGUOUS"
    AUTHORITY_MALFORMED = "AUTHORITY_MALFORMED"
    AUTHORITY_UNAUTHORIZED = "AUTHORITY_UNAUTHORIZED"
    AS_OF_UNSUPPORTED = "AS_OF_UNSUPPORTED"
    NO_ADAPTER_FOR_FIELD = "NO_ADAPTER_FOR_FIELD"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    ENTITY_UNRESOLVED = "ENTITY_UNRESOLVED"
    SUBREQUIREMENTS_UNVERIFIED = "SUBREQUIREMENTS_UNVERIFIED"


#: Which verdict each reason may accompany. Enforced by Judgement.__post_init__,
#: so a reason can never be attached to a verdict it does not explain.
REASON_VERDICT: dict[Reason, Verdict] = {
    Reason.AUTHORITY_CONFIRMED: Verdict.PASS,
    Reason.CORROBORATED_MULTI_SOURCE: Verdict.PASS,
    Reason.THRESHOLD_MET: Verdict.PASS,
    Reason.AUTHORITY_CONTRADICTED: Verdict.FAIL,
    Reason.IDENTIFIER_MISMATCH: Verdict.FAIL,
    Reason.THRESHOLD_NOT_MET: Verdict.FAIL,
    Reason.DOCUMENT_EXPIRED: Verdict.FAIL,
    Reason.MANDATORY_DOCUMENT_ABSENT: Verdict.FAIL,
    Reason.REGISTRATION_INACTIVE: Verdict.FAIL,
    Reason.SUBREQUIREMENT_UNREACHABLE: Verdict.FAIL,
    Reason.SELF_DECLARED_CEILING: Verdict.PARTIAL,
    Reason.SUBSET_SATISFIED: Verdict.PARTIAL,
    Reason.CORROBORATION_INCOMPLETE: Verdict.PARTIAL,
    Reason.STALE_VERIFICATION: Verdict.PARTIAL,
    Reason.AUTHORITY_UNAVAILABLE: Verdict.UNKNOWN,
    Reason.AUTHORITY_RATE_LIMITED: Verdict.UNKNOWN,
    Reason.AUTHORITY_NOT_FOUND: Verdict.UNKNOWN,
    Reason.AUTHORITY_AMBIGUOUS: Verdict.UNKNOWN,
    Reason.AUTHORITY_MALFORMED: Verdict.UNKNOWN,
    Reason.AUTHORITY_UNAUTHORIZED: Verdict.UNKNOWN,
    Reason.AS_OF_UNSUPPORTED: Verdict.UNKNOWN,
    Reason.NO_ADAPTER_FOR_FIELD: Verdict.UNKNOWN,
    Reason.EXTRACTION_FAILED: Verdict.UNKNOWN,
    Reason.ENTITY_UNRESOLVED: Verdict.UNKNOWN,
    Reason.SUBREQUIREMENTS_UNVERIFIED: Verdict.UNKNOWN,
}

#: The adapter failure taxonomy, mapped one-way. docs/ADAPTERS.md section 5.
#: No entry maps to PASS, and none maps to FAIL -- the sole exception is the
#: explicit, justified not_found_is_negative declaration handled by the adapter
#: layer, never by this table.
ADAPTER_FAILURE_REASON: dict[str, Reason] = {
    "UNAVAILABLE": Reason.AUTHORITY_UNAVAILABLE,
    "RATE_LIMITED": Reason.AUTHORITY_RATE_LIMITED,
    "NOT_FOUND": Reason.AUTHORITY_NOT_FOUND,
    "AMBIGUOUS": Reason.AUTHORITY_AMBIGUOUS,
    "MALFORMED": Reason.AUTHORITY_MALFORMED,
    "UNAUTHORIZED": Reason.AUTHORITY_UNAUTHORIZED,
    "NOT_CAPABLE": Reason.NO_ADAPTER_FOR_FIELD,
    "AS_OF_UNSUPPORTED": Reason.AS_OF_UNSUPPORTED,
}


class ReasonMismatch(ValueError):
    """A reason code was attached to a verdict it cannot explain."""


@dataclass(frozen=True)
class Judgement:
    """A verdict together with the machine-readable reason it was reached."""
    verdict: Verdict
    reason: Reason

    def __post_init__(self) -> None:
        expected = REASON_VERDICT[self.reason]
        if expected is not self.verdict:
            raise ReasonMismatch(
                f"{self.reason.value} explains {expected.value}, "
                f"not {self.verdict.value}"
            )


def compose(children: Sequence[Verdict], k: int) -> Verdict:
    """Compose child verdicts under a k-of-n threshold.

    ALL_OF is k == len(children); ANY_OF is k == 1. See
    docs/VERDICT_ALGEBRA.md section 2 -- these are not three operators but one.

    Commutative, associative and idempotent in `children`, so the result cannot
    depend on document upload order, adapter response order, or map iteration
    order. That is what makes determinism testable rather than aspirational.
    """
    if not children:
        raise ValueError("compose() requires at least one child")
    if not 1 <= k <= len(children):
        raise ValueError(f"k={k} out of range for {len(children)} children")

    p = sum(1 for c in children if c is Verdict.PASS)
    r = sum(1 for c in children if c is Verdict.PARTIAL)
    u = sum(1 for c in children if c is Verdict.UNKNOWN)

    if p >= k:
        return Verdict.PASS
    # Best attainable count if every unresolved child resolved favourably. If
    # even that optimum falls short, the requirement is demonstrably unreachable.
    if p + r + u < k:
        return Verdict.FAIL
    if p > 0 or r > 0:
        return Verdict.PARTIAL
    return Verdict.UNKNOWN


def compose_judgement(children: Sequence[Judgement], k: int) -> Judgement:
    """compose(), carrying a reason code appropriate to an interior node."""
    verdict = compose([c.verdict for c in children], k)
    if verdict is Verdict.PASS:
        return Judgement(verdict, Reason.THRESHOLD_MET)
    if verdict is Verdict.FAIL:
        return Judgement(verdict, Reason.SUBREQUIREMENT_UNREACHABLE)
    if verdict is Verdict.PARTIAL:
        return Judgement(verdict, Reason.SUBSET_SATISFIED)
    # All children are UNKNOWN. Propagate their reason when unanimous, so an
    # officer sees "the authority was down" rather than a generic placeholder.
    reasons = {c.reason for c in children}
    if len(reasons) == 1:
        return Judgement(verdict, reasons.pop())
    return Judgement(verdict, Reason.SUBREQUIREMENTS_UNVERIFIED)


def all_of(children: Sequence[Verdict]) -> Verdict:
    return compose(children, len(children))


def any_of(children: Sequence[Verdict]) -> Verdict:
    return compose(children, 1)


#: NOT is an involution. UNKNOWN must not negate to PASS: failing to find
#: someone on a debarment list is not evidence of their absence from it.
_NEGATION = {
    Verdict.PASS: Verdict.FAIL,
    Verdict.FAIL: Verdict.PASS,
    Verdict.PARTIAL: Verdict.PARTIAL,
    Verdict.UNKNOWN: Verdict.UNKNOWN,
}


def negate(v: Verdict) -> Verdict:
    return _NEGATION[v]


def apply_tier_ceiling(
    judgement: Judgement,
    obligation: Obligation,
    supporting_tiers: Iterable[Tier],
) -> Judgement:
    """Clamp a mandatory requirement resting *solely* on self-declaration.

    docs/VERDICT_ALGEBRA.md section 3. Applied at the leaf, before composition,
    so it propagates upward through the fold with no special handling at
    interior nodes.

    "Solely" is load-bearing: a self-declaration corroborated by any Tier A or B
    item is not clamped. The clamp fires only when the bidder's own word is the
    entire basis for a mandatory requirement.
    """
    tiers = list(supporting_tiers)
    if (
        judgement.verdict is Verdict.PASS
        and obligation is Obligation.MANDATORY
        and tiers
        and all(t is Tier.C for t in tiers)
    ):
        return Judgement(Verdict.PARTIAL, Reason.SELF_DECLARED_CEILING)
    return judgement
