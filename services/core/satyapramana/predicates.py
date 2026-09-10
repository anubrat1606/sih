"""The closed predicate language.

docs/RULE_PACKS.md section 4. Small, total, deterministic, with no escape hatch:
no expression strings, no embedded code. If a tender clause cannot be expressed
here, that is a finding to surface for human review, not a licence to add an
operator ad hoc.

Predicates return PASS, FAIL or UNKNOWN -- never a boolean, and never PARTIAL.
PARTIAL enters the system in exactly two places: the Tier C clamp and
composition.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Mapping, Protocol, Sequence

from .verdicts import Judgement, Reason, Verdict

#: Sentinel for an operand that could not be resolved. Distinct from None, which
#: is a legitimately observed null.
UNRESOLVED = object()


class RulePackError(ValueError):
    """The rule pack is malformed. Distinct from evidence being unavailable."""


@dataclass(frozen=True)
class Resolved:
    value: Any
    reason: Reason | None = None  # set only when value is UNRESOLVED

    @property
    def ok(self) -> bool:
        return self.value is not UNRESOLVED

    @staticmethod
    def missing(reason: Reason) -> "Resolved":
        return Resolved(UNRESOLVED, reason)


class Resolver(Protocol):
    """Supplies evidence values. The reason a path is unresolvable comes from
    the evidence record itself -- never guessed by the evaluator."""

    def field(self, path: str) -> Resolved: ...
    def collection(self, path: str) -> Resolved: ...


@dataclass(frozen=True)
class EvaluationContext:
    """The ONLY source of temporal values. No predicate may read the system
    clock -- that is the precondition for replay determinism."""
    as_of: date
    bid_submission_date: date
    tender_id: str
    bidder_id: str
    rule_pack_version: str

    def lookup(self, key: str) -> Resolved:
        if key == "as_of":
            return Resolved(self.as_of)
        if key == "bid_submission_date":
            return Resolved(self.bid_submission_date)
        # Derived offsets, computed deterministically from the context.
        if key.startswith("bid_submission_date_minus_") and key.endswith("y"):
            years = key[len("bid_submission_date_minus_"):-1]
            if years.isdigit():
                d = self.bid_submission_date
                try:
                    return Resolved(d.replace(year=d.year - int(years)))
                except ValueError:  # 29 February
                    return Resolved(d.replace(year=d.year - int(years), day=28))
        raise RulePackError(f"unknown context key: {key!r}")


def _as_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _as_number(v: Any) -> Decimal | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        # Monetary paths are integer minor units. A float here means the rule
        # pack or the normaliser is wrong; refuse rather than round.
        raise RulePackError("float operand: currency must be integer minor units")
    return None


AGGREGATES: dict[str, Callable[[Sequence[Decimal]], Decimal]] = {
    "sum": lambda xs: sum(xs, Decimal(0)),
    "mean": lambda xs: sum(xs, Decimal(0)) / Decimal(len(xs)),
    "min": min,
    "max": max,
    "count": lambda xs: Decimal(len(xs)),
}


def resolve_operand(
    operand: Mapping[str, Any], resolver: Resolver, ctx: EvaluationContext
) -> Resolved:
    if "field" in operand:
        return resolver.field(operand["field"])
    if "literal" in operand:
        return Resolved(operand["literal"])
    if "context" in operand:
        return ctx.lookup(operand["context"])
    if "aggregate" in operand:
        return _resolve_aggregate(operand, resolver, ctx)
    raise RulePackError(f"operand has no recognised kind: {sorted(operand)}")


def _resolve_aggregate(
    operand: Mapping[str, Any], resolver: Resolver, ctx: EvaluationContext
) -> Resolved:
    got = resolver.collection(operand["over"])
    if not got.ok:
        return got
    rows = list(got.value or [])
    select = operand["select"]
    window = operand.get("window")

    if window:
        key = window["order_by"]
        reverse = window["direction"] == "desc"
        try:
            rows = sorted(rows, key=lambda r: r[key], reverse=reverse)
        except KeyError:
            return Resolved.missing(Reason.EXTRACTION_FAILED)
        # A short window makes the aggregate undefined -- it is NOT computed
        # over what happens to be available. Averaging two financial years
        # against a three-year threshold is exactly the quiet substitution the
        # no-fabricated-data stance forbids.
        if len(rows) < window["last_n"]:
            return Resolved.missing(Reason.EXTRACTION_FAILED)
        rows = rows[: window["last_n"]]

    if not rows:
        return Resolved.missing(Reason.EXTRACTION_FAILED)

    values: list[Decimal] = []
    for row in rows:
        n = _as_number(row.get(select))
        if n is None:
            return Resolved.missing(Reason.EXTRACTION_FAILED)
        values.append(n)
    return Resolved(AGGREGATES[operand["aggregate"]](values))


def _unknown(reason: Reason | None) -> Judgement:
    return Judgement(Verdict.UNKNOWN, reason or Reason.EXTRACTION_FAILED)


def _decide(satisfied: bool, on_fail: Reason) -> Judgement:
    return (
        Judgement(Verdict.PASS, Reason.AUTHORITY_CONFIRMED)
        if satisfied
        else Judgement(Verdict.FAIL, on_fail)
    )


def evaluate(
    predicate: Mapping[str, Any], resolver: Resolver, ctx: EvaluationContext
) -> Judgement:
    """Three-valued evaluation. Any unresolved operand makes the whole predicate
    UNKNOWN, carrying the reason propagated from that operand -- a missing field
    is never false."""
    op = predicate.get("op")
    if op is None:
        raise RulePackError("predicate has no op")

    if op in ("all", "any"):
        children = [evaluate(p, resolver, ctx) for p in predicate["of"]]
        verdicts = [c.verdict for c in children]
        if op == "all":
            if Verdict.FAIL in verdicts:
                return next(c for c in children if c.verdict is Verdict.FAIL)
            if Verdict.UNKNOWN in verdicts:
                return next(c for c in children if c.verdict is Verdict.UNKNOWN)
            return Judgement(Verdict.PASS, Reason.AUTHORITY_CONFIRMED)
        if Verdict.PASS in verdicts:
            return next(c for c in children if c.verdict is Verdict.PASS)
        if Verdict.UNKNOWN in verdicts:
            return next(c for c in children if c.verdict is Verdict.UNKNOWN)
        return Judgement(Verdict.FAIL, Reason.THRESHOLD_NOT_MET)

    if op == "not":
        inner = evaluate(predicate["of"], resolver, ctx)
        if inner.verdict is Verdict.PASS:
            return Judgement(Verdict.FAIL, Reason.AUTHORITY_CONTRADICTED)
        if inner.verdict is Verdict.FAIL:
            return Judgement(Verdict.PASS, Reason.AUTHORITY_CONFIRMED)
        return inner  # UNKNOWN must not negate to PASS

    if op == "exists":
        got = resolve_operand(predicate["subject"], resolver, ctx)
        # `exists` is the one operator that legitimately consumes absence -- but
        # only when the evidence record positively says "not submitted". A path
        # that is merely unresolved stays UNKNOWN.
        if not got.ok:
            if got.reason is Reason.MANDATORY_DOCUMENT_ABSENT:
                return Judgement(Verdict.FAIL, Reason.MANDATORY_DOCUMENT_ABSENT)
            return _unknown(got.reason)
        return _decide(got.value is not None, Reason.MANDATORY_DOCUMENT_ABSENT)

    if op in ("one_of", "not_one_of"):
        got = resolve_operand(predicate["left"], resolver, ctx)
        if not got.ok:
            return _unknown(got.reason)
        member = got.value in predicate["values"]
        return _decide(
            member if op == "one_of" else not member, Reason.THRESHOLD_NOT_MET
        )

    if op == "matches":
        import re

        got = resolve_operand(predicate["left"], resolver, ctx)
        if not got.ok:
            return _unknown(got.reason)
        return _decide(
            bool(re.fullmatch(predicate["pattern"], str(got.value))),
            Reason.IDENTIFIER_MISMATCH,
        )

    if op == "active_on":
        got = resolve_operand(predicate["subject"], resolver, ctx)
        at = resolve_operand(predicate["at"], resolver, ctx)
        if not got.ok:
            return _unknown(got.reason)
        if not at.ok:
            return _unknown(at.reason)
        moment = _as_date(at.value)
        if moment is None:
            raise RulePackError("active_on: `at` is not a date")
        for span in got.value or []:
            start = _as_date(span.get("from"))
            end = _as_date(span.get("to")) if span.get("to") else None
            if start and start <= moment and (end is None or moment <= end):
                return _decide(span.get("status") == "ACTIVE",
                               Reason.REGISTRATION_INACTIVE)
        return Judgement(Verdict.UNKNOWN, Reason.AS_OF_UNSUPPORTED)

    if op == "date_between":
        got = resolve_operand(predicate["left"], resolver, ctx)
        lo = resolve_operand(predicate["from"], resolver, ctx)
        hi = resolve_operand(predicate["to"], resolver, ctx)
        for r in (got, lo, hi):
            if not r.ok:
                return _unknown(r.reason)
        d, a, b = (_as_date(x.value) for x in (got, lo, hi))
        if None in (d, a, b):
            return _unknown(Reason.EXTRACTION_FAILED)
        return _decide(a <= d <= b, Reason.DOCUMENT_EXPIRED)

    if op in ("eq", "ne", "gt", "gte", "lt", "lte", "date_before", "date_after"):
        left = resolve_operand(predicate["left"], resolver, ctx)
        right = resolve_operand(predicate["right"], resolver, ctx)
        if not left.ok:
            return _unknown(left.reason)
        if not right.ok:
            return _unknown(right.reason)

        if op in ("eq", "ne"):
            same = left.value == right.value
            return _decide(same if op == "eq" else not same,
                           Reason.IDENTIFIER_MISMATCH)

        if op in ("date_before", "date_after"):
            a, b = _as_date(left.value), _as_date(right.value)
            if a is None or b is None:
                return _unknown(Reason.EXTRACTION_FAILED)
            return _decide(a < b if op == "date_before" else a > b,
                           Reason.DOCUMENT_EXPIRED)

        a, b = _as_number(left.value), _as_number(right.value)
        if a is None or b is None:
            da, db = _as_date(left.value), _as_date(right.value)
            if da is None or db is None:
                return _unknown(Reason.EXTRACTION_FAILED)
            a, b = da, db
        satisfied = {
            "gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b,
        }[op]
        return _decide(satisfied, Reason.THRESHOLD_NOT_MET)

    raise RulePackError(f"unknown operator: {op!r}")
