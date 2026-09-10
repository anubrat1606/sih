"""Three-valued predicate evaluation.

No government data appears here. Where a value stands in for an authority
response it is a locally-constructed fixture exercising the evaluator's logic,
never a simulated API payload -- those are forbidden by charter section 3.1 and
none exist in this repository.
"""
from datetime import date

import pytest

from satyapramana.predicates import (
    EvaluationContext, Resolved, RulePackError, evaluate,
)
from satyapramana.verdicts import Reason, Verdict

P, F, U = Verdict.PASS, Verdict.FAIL, Verdict.UNKNOWN

CTX = EvaluationContext(
    as_of=date(2026, 9, 10),
    bid_submission_date=date(2026, 9, 22),
    tender_id="T1",
    bidder_id="A",
    rule_pack_version="rp@1.0.0+abc",
)


class Store:
    """A resolver over an in-memory dict. Unknown paths carry an explicit
    reason, exactly as a real evidence projection would."""

    def __init__(self, fields=None, collections=None, missing=None):
        self._f = fields or {}
        self._c = collections or {}
        self._missing = missing or {}

    def field(self, path):
        if path in self._f:
            return Resolved(self._f[path])
        return Resolved.missing(self._missing.get(path, Reason.EXTRACTION_FAILED))

    def collection(self, path):
        if path in self._c:
            return Resolved(self._c[path])
        return Resolved.missing(self._missing.get(path, Reason.EXTRACTION_FAILED))


def ev(pred, store):
    return evaluate(pred, store, CTX)


# --- the central property -----------------------------------------------------

def test_a_missing_field_is_unknown_never_false():
    pred = {"op": "eq", "left": {"field": "bidder.pan.status"},
            "right": {"literal": "VALID"}}
    j = ev(pred, Store())
    assert j.verdict is U and j.verdict is not F


def test_the_reason_comes_from_the_evidence_record_not_the_evaluator():
    store = Store(missing={"bidder.gst.status": Reason.AUTHORITY_UNAVAILABLE})
    pred = {"op": "eq", "left": {"field": "bidder.gst.status"},
            "right": {"literal": "ACTIVE"}}
    assert ev(pred, store).reason is Reason.AUTHORITY_UNAVAILABLE


def test_predicates_never_return_partial():
    """PARTIAL enters only via the Tier C clamp and composition."""
    cases = [
        ({"op": "eq", "left": {"field": "a.b"}, "right": {"literal": 1}}, Store()),
        ({"op": "eq", "left": {"field": "a.b"}, "right": {"literal": 1}},
         Store(fields={"a.b": 1})),
        ({"op": "exists", "subject": {"field": "a.b"}}, Store()),
    ]
    for pred, store in cases:
        assert ev(pred, store).verdict in (P, F, U)


# --- unknown propagation through logical operators ----------------------------

def test_all_propagates_fail_over_unknown():
    store = Store(fields={"a.b": "X"})
    pred = {"op": "all", "of": [
        {"op": "eq", "left": {"field": "a.b"}, "right": {"literal": "Y"}},
        {"op": "eq", "left": {"field": "missing.path"}, "right": {"literal": 1}},
    ]}
    assert ev(pred, store).verdict is F


def test_all_is_unknown_when_a_conjunct_is_unresolved():
    store = Store(fields={"a.b": "X"})
    pred = {"op": "all", "of": [
        {"op": "eq", "left": {"field": "a.b"}, "right": {"literal": "X"}},
        {"op": "eq", "left": {"field": "missing.path"}, "right": {"literal": 1}},
    ]}
    assert ev(pred, store).verdict is U


def test_any_short_circuits_on_a_real_pass():
    store = Store(fields={"a.b": "X"})
    pred = {"op": "any", "of": [
        {"op": "eq", "left": {"field": "a.b"}, "right": {"literal": "X"}},
        {"op": "eq", "left": {"field": "missing.path"}, "right": {"literal": 1}},
    ]}
    assert ev(pred, store).verdict is P


def test_not_leaves_unknown_alone():
    pred = {"op": "not", "of": {"op": "eq", "left": {"field": "missing"},
                                "right": {"literal": 1}}}
    assert ev(pred, Store()).verdict is U


# --- exists -------------------------------------------------------------------

def test_exists_fails_only_on_a_recorded_absence():
    absent = Store(missing={"doc.iso": Reason.MANDATORY_DOCUMENT_ABSENT})
    unresolved = Store(missing={"doc.iso": Reason.EXTRACTION_FAILED})
    pred = {"op": "exists", "subject": {"field": "doc.iso"}}
    assert ev(pred, absent).verdict is F
    assert ev(pred, unresolved).verdict is U


# --- temporal -----------------------------------------------------------------

def test_no_predicate_reads_the_system_clock():
    """Every temporal value must come from the evaluation context."""
    with pytest.raises(RulePackError):
        CTX.lookup("today")
    with pytest.raises(RulePackError):
        CTX.lookup("now")


def test_derived_context_offsets_are_deterministic():
    assert CTX.lookup("bid_submission_date_minus_5y").value == date(2021, 9, 22)


def test_active_on_uses_the_submission_date_not_today():
    store = Store(fields={"g.hist": [
        {"from": "2020-01-01", "to": "2026-09-15", "status": "ACTIVE"},
        {"from": "2026-09-16", "to": None, "status": "CANCELLED"},
    ]})
    pred = {"op": "active_on", "subject": {"field": "g.hist"},
            "at": {"context": "bid_submission_date"}}
    # Active on as_of (10 Sep) but cancelled by the submission date (22 Sep).
    assert ev(pred, store).verdict is F


def test_active_on_is_unknown_when_no_span_covers_the_moment():
    """A source with no history for that date must not answer the present-tense
    question in its place."""
    store = Store(fields={"g.hist": [
        {"from": "2027-01-01", "to": None, "status": "ACTIVE"}]})
    pred = {"op": "active_on", "subject": {"field": "g.hist"},
            "at": {"context": "bid_submission_date"}}
    j = ev(pred, store)
    assert j.verdict is U and j.reason is Reason.AS_OF_UNSUPPORTED


# --- aggregates ---------------------------------------------------------------

FIN = [
    {"fiscal_year_end": "2026-03-31", "annual_turnover_minor": 40000000000},
    {"fiscal_year_end": "2025-03-31", "annual_turnover_minor": 30000000000},
    {"fiscal_year_end": "2024-03-31", "annual_turnover_minor": 20000000000},
]
TURNOVER = {
    "op": "gte",
    "left": {"aggregate": "mean", "over": "bidder.financials",
             "select": "annual_turnover_minor",
             "window": {"last_n": 3, "order_by": "fiscal_year_end",
                        "direction": "desc"}},
    "right": {"literal": 30000000000},
}


def test_three_year_average_turnover():
    assert ev(TURNOVER, Store(collections={"bidder.financials": FIN})).verdict is P


def test_a_short_window_is_unknown_not_averaged_over_what_is_available():
    """Averaging two years against a three-year threshold is exactly the quiet
    substitution the no-fabricated-data stance forbids."""
    store = Store(collections={"bidder.financials": FIN[:2]})
    j = ev(TURNOVER, store)
    assert j.verdict is U, "must not silently average a short window"
    # The two available years average 35 crore, which WOULD have passed.
    assert j.verdict is not P


def test_currency_must_be_integer_minor_units():
    store = Store(collections={"bidder.financials": [
        {"fiscal_year_end": "2026-03-31", "annual_turnover_minor": 3.0e10}]})
    pred = dict(TURNOVER)
    pred["left"] = dict(TURNOVER["left"])
    pred["left"].pop("window")
    with pytest.raises(RulePackError):
        ev(pred, store)


# --- malformed rule packs are errors, not verdicts ----------------------------

def test_unknown_operator_raises():
    with pytest.raises(RulePackError):
        ev({"op": "vibes", "left": {"field": "a.b"}, "right": {"literal": 1}}, Store())


def test_unknown_operand_kind_raises():
    with pytest.raises(RulePackError):
        ev({"op": "eq", "left": {"mystery": "a.b"}, "right": {"literal": 1}}, Store())
