"""Exhaustive verification of the verdict algebra.

These are property tests over a four-element domain, so "exhaustive" is literal:
every combination up to n=5 children and every threshold k. Note that no
government data appears here -- these fixtures are abstract verdict states, not
simulated authority responses.
"""
from itertools import permutations, product

import pytest

from satyapramana.verdicts import (
    Judgement, Obligation, Reason, ReasonMismatch, Tier, Verdict,
    all_of, any_of, apply_tier_ceiling, compose, compose_judgement, negate,
)

P, F, R, U = Verdict.PASS, Verdict.FAIL, Verdict.PARTIAL, Verdict.UNKNOWN
STATES = (P, F, R, U)

# The tables exactly as written in docs/VERDICT_ALGEBRA.md sections 2.1 and 2.2.
T_AND = {(P, P): P, (P, F): F, (P, R): R, (P, U): R,
         (F, P): F, (F, F): F, (F, R): F, (F, U): F,
         (R, P): R, (R, F): F, (R, R): R, (R, U): R,
         (U, P): R, (U, F): F, (U, R): R, (U, U): U}
T_OR = {(P, P): P, (P, F): P, (P, R): P, (P, U): P,
        (F, P): P, (F, F): F, (F, R): R, (F, U): U,
        (R, P): P, (R, F): R, (R, R): R, (R, U): R,
        (U, P): P, (U, F): U, (U, R): R, (U, U): U}


def fold(table, children):
    acc = children[0]
    for x in children[1:]:
        acc = table[(acc, x)]
    return acc


@pytest.mark.parametrize("a,b", list(product(STATES, STATES)))
def test_documented_tables_match_the_function(a, b):
    """The prose tables and the implementation cannot silently drift apart."""
    assert all_of([a, b]) is T_AND[(a, b)]
    assert any_of([a, b]) is T_OR[(a, b)]


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_compose_is_order_independent(n):
    """Determinism: a verdict cannot depend on document upload order, adapter
    response order, or map iteration order."""
    for children in product(STATES, repeat=n):
        for k in range(1, n + 1):
            expected = compose(list(children), k)
            for perm in permutations(children):
                assert compose(list(perm), k) is expected


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_all_of_and_any_of_are_the_same_function(n):
    """ALL_OF is k=n, ANY_OF is k=1 -- not three operators but one."""
    for children in product(STATES, repeat=n):
        assert compose(list(children), n) is fold(T_AND, children)
        assert compose(list(children), 1) is fold(T_OR, children)


@pytest.mark.parametrize("a,b,c", list(product(STATES, STATES, STATES)))
def test_associativity(a, b, c):
    assert T_AND[(T_AND[(a, b)], c)] is T_AND[(a, T_AND[(b, c)])]
    assert T_OR[(T_OR[(a, b)], c)] is T_OR[(a, T_OR[(b, c)])]


@pytest.mark.parametrize("a", STATES)
def test_idempotence_and_absorption(a):
    assert all_of([a, a]) is a
    assert any_of([a, a]) is a
    assert all_of([a, F]) is F, "FAIL is absorbing under conjunction"
    assert any_of([a, P]) is P, "PASS is absorbing under disjunction"


@pytest.mark.parametrize("a", STATES)
def test_negation_is_an_involution(a):
    assert negate(negate(a)) is a


def test_unknown_does_not_negate_to_pass():
    """Failing to find someone on a debarment list is not evidence of absence."""
    assert negate(U) is U
    assert negate(R) is R


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5])
def test_totality(n):
    for children in product(STATES, repeat=n):
        for k in range(1, n + 1):
            assert compose(list(children), k) in STATES


def test_pass_plus_unknown_is_partial_not_unknown():
    """Real ground was gained on one conjunct; the officer must see that."""
    assert all_of([P, U]) is R


def test_fail_or_unknown_is_unknown_not_fail():
    """The unknown disjunct might still have satisfied the requirement."""
    assert any_of([F, U]) is U


def test_worked_example_from_the_spec():
    """docs/VERDICT_ALGEBRA.md section 7: 2 pass, 1 partial, 1 unknown, 1 fail,
    k=3. Neither settled nor doomed -- a third is still reachable."""
    assert compose([P, P, R, U, F], 3) is R
    assert all_of([P, P, R]) is R


def test_k_of_n_fails_only_when_unreachable():
    assert compose([P, F, F, F, F], 3) is F, "optimum 1 < k=3"
    assert compose([P, U, U, F, F], 3) is R, "optimum 3 >= k=3, ground gained"
    assert compose([U, U, U, F, F], 3) is U, "optimum 3 >= k=3, nothing gained"


def test_compose_rejects_out_of_range_k():
    with pytest.raises(ValueError):
        compose([P, P], 0)
    with pytest.raises(ValueError):
        compose([P, P], 3)
    with pytest.raises(ValueError):
        compose([], 1)


# --- reason codes -------------------------------------------------------------

def test_a_reason_cannot_be_attached_to_the_wrong_verdict():
    Judgement(Verdict.PASS, Reason.AUTHORITY_CONFIRMED)
    with pytest.raises(ReasonMismatch):
        Judgement(Verdict.PASS, Reason.AUTHORITY_UNAVAILABLE)
    with pytest.raises(ReasonMismatch):
        Judgement(Verdict.FAIL, Reason.AUTHORITY_UNAVAILABLE)


def test_no_adapter_failure_reason_can_explain_a_pass():
    """docs/ADAPTERS.md section 5: no row in the failure taxonomy maps to PASS,
    and none maps to FAIL either."""
    from satyapramana.verdicts import ADAPTER_FAILURE_REASON, REASON_VERDICT
    for code, reason in ADAPTER_FAILURE_REASON.items():
        assert REASON_VERDICT[reason] is Verdict.UNKNOWN, code


def test_composed_unknown_propagates_a_unanimous_reason():
    children = [Judgement(U, Reason.AUTHORITY_UNAVAILABLE)] * 3
    assert compose_judgement(children, 3).reason is Reason.AUTHORITY_UNAVAILABLE


def test_composed_unknown_generalises_a_mixed_reason():
    children = [Judgement(U, Reason.AUTHORITY_UNAVAILABLE),
                Judgement(U, Reason.EXTRACTION_FAILED)]
    j = compose_judgement(children, 2)
    assert j.verdict is U and j.reason is Reason.SUBREQUIREMENTS_UNVERIFIED


# --- tier ceiling -------------------------------------------------------------

def _pass():
    return Judgement(Verdict.PASS, Reason.AUTHORITY_CONFIRMED)


def test_mandatory_self_declared_cannot_reach_pass():
    j = apply_tier_ceiling(_pass(), Obligation.MANDATORY, [Tier.C])
    assert j.verdict is R and j.reason is Reason.SELF_DECLARED_CEILING


def test_corroborated_self_declaration_is_not_clamped():
    """'Solely' is load-bearing."""
    assert apply_tier_ceiling(_pass(), Obligation.MANDATORY, [Tier.C, Tier.A]).verdict is P
    assert apply_tier_ceiling(_pass(), Obligation.MANDATORY, [Tier.C, Tier.B]).verdict is P


def test_desirable_self_declaration_is_not_clamped():
    assert apply_tier_ceiling(_pass(), Obligation.DESIRABLE, [Tier.C]).verdict is P


def test_ceiling_only_clamps_pass():
    fail = Judgement(Verdict.FAIL, Reason.THRESHOLD_NOT_MET)
    assert apply_tier_ceiling(fail, Obligation.MANDATORY, [Tier.C]) is fail


def test_ceiling_propagates_through_composition():
    """Clamping at the leaf means interior nodes need no special handling."""
    clamped = apply_tier_ceiling(_pass(), Obligation.MANDATORY, [Tier.C])
    assert all_of([P, P, clamped.verdict]) is R
