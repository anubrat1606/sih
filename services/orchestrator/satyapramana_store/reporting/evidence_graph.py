"""The Evidence Graph: satyapramana.md section 2.3's signature screen, as
data. "One tender, one bidder, rendered as a navigable graph: requirements
on one axis, evidence nodes beneath, authority verifications beside, edges
weighted by verdict and confidence."

Three node kinds, three columns:
  requirement -> evidence -> authority

A **requirement** node exists only for a LEAF requirement -- one with its own
predicate, per `derived_bindings`. A composite (ALL_OF/ANY_OF) requirement
consumes no evidence directly; it aggregates its children's verdicts, which
already have their own nodes. Showing a composite here would draw an edge to
nothing real.

An **evidence** node exists for every path at least one requirement binds to,
whatever its resolution state -- an unresolved path is exactly as real a node
as a resolved one; hiding it would make a gap invisible instead of visible.

An **authority** node exists only for a path that was actually the subject of
a verification attempt (its evidence record carries a `capability_id`) --
never for a path that only rests on extraction (self-declared, Tier C).
Drawing an authority node for a fact nobody asked an authority about would be
exactly the fabrication this system refuses everywhere else.

Every edge carries the `requirement_id` it belongs to (a shared evidence path
can serve more than one requirement) and the requirement's own verdict --
that is the "weighted by verdict" the charter asks for. `resolved`/`tier`
carry evidence-side confidence for the evidence->authority edge, since a
verdict is only computed per-requirement, not per-evidence-hop.
"""
from __future__ import annotations

from typing import Any, Mapping

from satyapramana.rulepack import derived_bindings

from ..adapters import Registry


def build_evidence_graph(
    pack: Mapping[str, Any],
    verdict_rows: list[Mapping[str, Any]],
    evidence_by_path: Mapping[str, Mapping[str, Any]],
    registry: Registry,
) -> dict[str, Any]:
    verdict_by_id = {v["requirement_id"]: v for v in verdict_rows}

    requirements: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    path_requirements: dict[str, set[str]] = {}

    for req in pack.get("requirements", []):
        paths = derived_bindings(req)
        if not paths:
            continue  # composite -- aggregates children, binds no evidence itself
        v = verdict_by_id.get(req["id"])
        requirements.append({
            "requirement_id": req["id"],
            "text": req["text"],
            "obligation": req["obligation"],
            "verdict": v["verdict_effective"] if v else None,
            "reason_code": v["reason_effective"] if v else None,
        })
        for path in sorted(paths):
            path_requirements.setdefault(path, set()).add(req["id"])
            edges.append({
                "from_kind": "requirement", "from_id": req["id"],
                "to_kind": "evidence", "to_id": path,
                "requirement_id": req["id"],
                "verdict": v["verdict_effective"] if v else None,
            })

    evidence: list[dict[str, Any]] = []
    authorities: dict[str, dict[str, Any]] = {}

    for path in sorted(path_requirements):
        rec = evidence_by_path.get(path)
        resolved = bool(rec and rec.get("resolved"))
        capability_id = rec.get("capability_id") if rec else None
        evidence.append({
            "path": path,
            "resolved": resolved,
            "value": rec.get("value") if rec else None,
            "unresolved_reason": rec.get("unresolved_reason") if rec else None,
            "tier": rec.get("tier") if rec else None,
            "channel": rec.get("channel") if rec else None,
            "capability_id": capability_id,
        })
        if not capability_id:
            continue  # extraction-only (Tier C, self-declared) -- no authority was ever asked
        found = registry.for_capability(capability_id)
        authority_name = (found[0].manifest.authority if found else None) or capability_id
        authorities.setdefault(capability_id, {
            "capability_id": capability_id, "authority": authority_name})
        for requirement_id in sorted(path_requirements[path]):
            edges.append({
                "from_kind": "evidence", "from_id": path,
                "to_kind": "authority", "to_id": capability_id,
                "requirement_id": requirement_id,
                "verdict": verdict_by_id.get(requirement_id, {}).get("verdict_effective"),
                "resolved": resolved,
            })

    return {
        "requirements": requirements,
        "evidence": evidence,
        "authorities": sorted(authorities.values(), key=lambda a: a["capability_id"]),
        "edges": edges,
    }
