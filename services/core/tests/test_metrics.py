"""The three metrics stay three."""
import pytest

from satyapramana.metrics import (
    Constants, Metrics, RequirementResult, compliance_score, compute,
    evidence_confidence, requirement_confidence, verification_coverage,
    verification_coverage_mandatory,
)
from satyapramana.verdicts import Channel, Obligation, Tier, Verdict

C = Constants()
M, D = Obligation.MANDATORY, Obligation.DESIRABLE


def r(verdict, obligation=M, **kw):
    return RequirementResult("R", verdict, obligation, **kw)


# --- the null-not-zero rule ---------------------------------------------------

def test_compliance_score_is_none_when_nothing_is_determinate():
    """A zero reads as 'totally non-compliant' when the truth is 'nothing could
    be checked'. That confusion is what this design exists to prevent."""
    results = [r(Verdict.UNKNOWN), r(Verdict.UNKNOWN)]
    assert compliance_score(results, C) is None
    assert compliance_score(results, C) != 0.0


def test_compliance_score_is_zero_only_when_things_genuinely_failed():
    assert compliance_score([r(Verdict.FAIL)], C) == 0.0


def test_none_and_zero_are_distinguishable_downstream():
    nothing = compute([r(Verdict.UNKNOWN)], C)
    failed = compute([r(Verdict.FAIL)], C)
    assert nothing.compliance_score is None
    assert failed.compliance_score == 0.0


# --- domain separation --------------------------------------------------------

def test_unknown_requirements_leave_compliance_score_untouched():
    """UNKNOWN is the subject of Coverage, not of Compliance Score."""
    determinate_only = [r(Verdict.PASS), r(Verdict.FAIL)]
    with_unknowns = determinate_only + [r(Verdict.UNKNOWN)] * 5
    assert compliance_score(determinate_only, C) == compliance_score(with_unknowns, C)


def test_unknown_requirements_do_lower_coverage():
    """...which is exactly where they must show up."""
    covered = [r(Verdict.PASS, covered=True)]
    plus_unknown = covered + [r(Verdict.UNKNOWN, covered=False)]
    assert verification_coverage(covered) == 100.0
    assert verification_coverage(plus_unknown) == 50.0


def test_mandatory_and_desirable_are_weighted_differently():
    mandatory_failed = [r(Verdict.FAIL, M), r(Verdict.PASS, D)]
    desirable_failed = [r(Verdict.PASS, M), r(Verdict.FAIL, D)]
    assert compliance_score(mandatory_failed, C) < compliance_score(desirable_failed, C)


def test_partial_earns_declared_credit_not_a_hard_coded_half():
    strict = Constants(partial_credit=0.0)
    assert compliance_score([r(Verdict.PARTIAL)], C) == 50.0
    assert compliance_score([r(Verdict.PARTIAL)], strict) == 0.0


def test_coverage_mandatory_is_none_when_nothing_is_mandatory():
    assert verification_coverage_mandatory([r(Verdict.PASS, D)]) is None


# --- confidence ---------------------------------------------------------------

def test_aggregator_channel_is_discounted_against_direct():
    """An aggregator's answer is not the authority's own answer."""
    direct = r(Verdict.PASS, tier=Tier.A, channel=Channel.DIRECT)
    via = r(Verdict.PASS, tier=Tier.A, channel=Channel.AGGREGATOR)
    assert requirement_confidence(direct, C) == pytest.approx(1.00)
    assert requirement_confidence(via, C) == pytest.approx(0.85)


def test_extraction_confidence_is_weakest_link_not_mean():
    """A doubtful field can still be the wrong one."""
    weak = r(Verdict.PASS, tier=Tier.A, channel=Channel.DIRECT,
             extraction_confidence=0.4)
    assert requirement_confidence(weak, C) == pytest.approx(0.4)


def test_tier_c_confidence_is_lowest():
    a = r(Verdict.PASS, tier=Tier.A, channel=Channel.DIRECT)
    b = r(Verdict.PASS, tier=Tier.B, channel=Channel.DIRECT)
    c = r(Verdict.PASS, tier=Tier.C, channel=Channel.DIRECT)
    conf = [requirement_confidence(x, C) for x in (a, b, c)]
    assert conf == sorted(conf, reverse=True)


def test_confidence_is_capped_at_one():
    many = r(Verdict.PASS, tier=Tier.A, channel=Channel.DIRECT,
             independent_sources=20)
    assert requirement_confidence(many, C) <= 1.0


def test_stale_verification_lowers_confidence():
    fresh = r(Verdict.PASS, tier=Tier.A, channel=Channel.DIRECT, recency_factor=1.0)
    stale = r(Verdict.PASS, tier=Tier.A, channel=Channel.DIRECT, recency_factor=0.5)
    assert requirement_confidence(stale, C) < requirement_confidence(fresh, C)


# --- the metrics stay orthogonal ---------------------------------------------

def test_the_three_metrics_are_independent():
    """100 compliant / 40 coverage / 60 confidence is a materially different
    procurement risk from 100/95/95. Neither is derivable from the others."""
    results = [
        r(Verdict.PASS, covered=True, tier=Tier.A, channel=Channel.DIRECT),
        r(Verdict.PASS, covered=False, tier=Tier.C, channel=None),
    ]
    m = compute(results, C)
    assert m.compliance_score == 100.0
    assert m.verification_coverage == 50.0
    assert m.evidence_confidence is not None and m.evidence_confidence < 100.0


def test_metrics_exposes_no_blended_figure():
    """docs/VERDICT_ALGEBRA.md section 5.4 forbids it in prose; this makes it a
    build failure."""
    forbidden = {
        "overall", "overall_score", "trust_score", "total", "blended",
        "combined", "aggregate_score", "final_score", "score",
    }
    present = {f for f in Metrics.__dataclass_fields__} | {
        a for a in dir(Metrics) if not a.startswith("_")
    }
    assert not (forbidden & present), f"blended figure exposed: {forbidden & present}"
    assert len(Metrics.__dataclass_fields__) == 4  # three metrics + mandatory split
