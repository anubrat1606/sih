"""The DECIDE stage. Fully deterministic; zero model involvement.

Evaluates an adopted rule pack against the evidence projection and emits one
REQUIREMENT_EVALUATED event per requirement, each carrying its verdict, reason
code and the exact rule pack version that produced it -- and each caused by the
evidence that produced it, so the provenance walk has a real chain to follow.
"""
from __future__ import annotations

import uuid
from typing import Any, Mapping

from satyapramana.predicates import EvaluationContext, evaluate
from satyapramana.rulepack import derived_bindings
from satyapramana.verdicts import (
    Judgement, Obligation, Reason, Verdict, apply_tier_ceiling, compose_judgement,
    negate,
)

from .events import Actor, append
from .evidence import ProjectionResolver

SYSTEM = Actor("SYSTEM", "decide@1.0.0")


def _index(pack: Mapping[str, Any]) -> dict[str, dict]:
    return {r["id"]: r for r in pack["requirements"]}


def _roots(pack: Mapping[str, Any]) -> list[str]:
    children = {c for r in pack["requirements"] for c in r.get("children", [])}
    return [r["id"] for r in pack["requirements"] if r["id"] not in children]


def evaluate_bidder(
    conn,
    *,
    pack: Mapping[str, Any],
    rule_pack_version: str,
    tender_id: str,
    bidder_id: str,
    ctx: EvaluationContext,
    correlation_id: str | None = None,
    fusion_events: Mapping[str, str] | None = None,
) -> dict[str, Judgement]:
    """Evaluate every requirement, deepest first, emitting events as it goes."""
    resolver = ProjectionResolver(conn, bidder_id)
    index = _index(pack)
    correlation = correlation_id or str(uuid.uuid4())
    fusion = dict(fusion_events or {})

    judgements: dict[str, Judgement] = {}
    event_ids: dict[str, str] = {}

    def walk(rid: str, seen: frozenset[str] = frozenset()) -> Judgement:
        if rid in judgements:
            return judgements[rid]
        if rid in seen:
            # validate() rejects cycles before adoption; this is belt and braces
            # in case an adopted pack is ever reached by another route.
            raise ValueError(f"cycle in requirement graph at {rid}")

        req = index[rid]
        operator = req["operator"]
        obligation = Obligation(req["obligation"])

        if operator == "LEAF":
            judgement = evaluate(req["predicate"], resolver, ctx)
            bindings = derived_bindings(req)
            # The Tier C ceiling is applied at the leaf so it propagates upward
            # through the fold with no special handling at interior nodes.
            judgement = apply_tier_ceiling(
                judgement, obligation, resolver.tiers_for(bindings))
            payload_extra = {"evidence_paths": sorted(bindings),
                             "evidence_events": resolver.source_events(bindings)}
            # Causation points at the FUSION event for the first binding, not at
            # the raw evidence event. Fusion is where a bidder's claim meets the
            # authority's answer, and skipping it would drop a hop the trail is
            # meant to show: verdict -> fused evidence -> verification ->
            # extraction -> document. Every contributing evidence event is still
            # listed in the payload, so the full set stays recoverable.
            fused = [fusion[p] for p in sorted(bindings) if p in fusion]
            causation = fused[0] if fused else None
        else:
            children = [walk(c, seen | {rid}) for c in req["children"]]
            if operator == "NOT":
                inner = children[0]
                verdict = negate(inner.verdict)
                judgement = Judgement(
                    verdict,
                    {Verdict.PASS: Reason.AUTHORITY_CONFIRMED,
                     Verdict.FAIL: Reason.AUTHORITY_CONTRADICTED,
                     Verdict.PARTIAL: Reason.SUBSET_SATISFIED,
                     Verdict.UNKNOWN: inner.reason}[verdict]
                    if verdict is not Verdict.UNKNOWN else inner.reason)
            else:
                k = len(children) if operator == "ALL_OF" else (
                    1 if operator == "ANY_OF" else req["k"])
                judgement = compose_judgement(children, k)
            payload_extra = {"children": list(req["children"])}
            causation = event_ids.get(req["children"][0])

        judgements[rid] = judgement
        record = append(
            conn, event_type="REQUIREMENT_EVALUATED", actor=SYSTEM,
            correlation_id=correlation, causation_id=causation,
            tender_id=tender_id, bidder_id=bidder_id,
            payload={"requirement_id": rid,
                     "verdict": judgement.verdict.value,
                     "reason_code": judgement.reason.value,
                     "obligation": obligation.value,
                     "operator": operator,
                     "rule_pack_version": rule_pack_version,
                     "source": req.get("source"),
                     "code_version": SYSTEM.id,
                     **payload_extra})
        event_ids[rid] = record["event_id"]
        return judgement

    for root in _roots(pack):
        walk(root)
    return judgements


def _fusion_outcome(rec) -> str:
    if rec is None or not rec.resolved:
        return "GAP"
    return "AUTHORITY_ONLY" if rec.capability_id else "CLAIM_ONLY"


def fuse_and_evaluate(
    conn, *, pack, rule_pack_version, tender_id, bidder_id, ctx,
) -> dict[str, Any]:
    """Emit EVIDENCE_FUSED for each path the pack consumes, then decide.

    Fusion is where a bidder's claim meets the authority's answer. With no
    claims ingested yet the outcome is GAP or the authority's observation
    standing alone -- recorded honestly rather than skipped, because "we have
    an authority answer and no bidder claim to compare it against" is itself a
    fact the officer may need.
    """
    resolver = ProjectionResolver(conn, bidder_id)
    correlation = str(uuid.uuid4())

    paths = sorted({p for r in pack["requirements"] for p in derived_bindings(r)})
    fusion_events: dict[str, str] = {}
    for path in paths:
        rec = resolver.record(path)
        fused = append(conn, event_type="EVIDENCE_FUSED", actor=Actor("SYSTEM", "fuse@1.0.0"),
               correlation_id=correlation,
               causation_id=rec.source_event if rec else None,
               tender_id=tender_id, bidder_id=bidder_id,
               payload={"path": path,
                        # CLAIM_ONLY means the value came off the bidder's own
                        # document with no authority consulted. Labelling that
                        # AUTHORITY_ONLY would overstate the evidence, which is
                        # the whole failure mode this system exists to avoid.
                        "outcome": _fusion_outcome(rec),
                        "observed": rec.value if rec and rec.resolved else None,
                        "unresolved_reason": (
                            rec.unresolved_reason.value
                            if rec and rec.unresolved_reason else None)})
        fusion_events[path] = fused["event_id"]

    judgements = evaluate_bidder(
        conn, pack=pack, rule_pack_version=rule_pack_version, tender_id=tender_id,
        bidder_id=bidder_id, ctx=ctx, correlation_id=correlation,
        fusion_events=fusion_events)
    return {"correlation_id": correlation,
            "verdicts": {rid: {"verdict": j.verdict.value, "reason": j.reason.value}
                         for rid, j in judgements.items()}}
