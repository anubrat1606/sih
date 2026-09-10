"""Rule pack loading and validation.

docs/RULE_PACKS.md section 7. The JSON Schema at /schemas/rule_pack.schema.json
covers structure; this module covers the semantic rules a schema cannot express
-- cycles, unresolvable references, evidence paths nothing can produce, and the
prohibition on reading the system clock.

Validation gates adoption. It is deterministic and it never repairs a pack: a
malformed rule pack is rejected, never coerced into something evaluable.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

CANONICAL = dict(sort_keys=True, separators=(",", ":"), ensure_ascii=False)

#: Operand kinds and operators, mirrored from the schema so a drifted pack is
#: caught here even if schema validation is skipped.
OPERATORS = {
    "eq", "ne", "gt", "gte", "lt", "lte", "one_of", "not_one_of", "matches",
    "exists", "date_before", "date_after", "date_between", "active_on",
    "not", "all", "any",
}
OPERAND_KINDS = {"field", "literal", "context", "aggregate"}


@dataclass(frozen=True)
class Violation:
    rule: int
    requirement_id: str | None
    message: str

    def __str__(self) -> str:
        where = f" [{self.requirement_id}]" if self.requirement_id else ""
        return f"rule {self.rule}{where}: {self.message}"


def canonical_json(pack: Mapping[str, Any]) -> str:
    """The form the content hash is taken over: sorted keys, no insignificant
    whitespace, UTF-8, with content_hash itself excluded."""
    return json.dumps({k: v for k, v in pack.items() if k != "content_hash"},
                      **CANONICAL)


def content_hash(pack: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(pack).encode("utf-8")).hexdigest()


def rule_pack_version(pack: Mapping[str, Any]) -> str:
    """id@semver+hash12 -- semver alone is forgeable by editing in place, and a
    hash alone is unreadable, so a verdict records the full triple."""
    return f"{pack['rule_pack_id']}@{pack['semver']}+{content_hash(pack)[:12]}"


def _walk_operands(node: Any) -> Iterable[Mapping[str, Any]]:
    if not isinstance(node, Mapping):
        return
    op = node.get("op")
    if op in ("all", "any"):
        for child in node.get("of", []):
            yield from _walk_operands(child)
        return
    if op == "not":
        yield from _walk_operands(node.get("of", {}))
        return
    for key in ("left", "right", "subject", "at", "from", "to"):
        if key in node and isinstance(node[key], Mapping):
            yield node[key]


def _walk_predicates(node: Any) -> Iterable[Mapping[str, Any]]:
    if not isinstance(node, Mapping) or "op" not in node:
        return
    yield node
    if node.get("op") in ("all", "any"):
        for child in node.get("of", []):
            yield from _walk_predicates(child)
    elif node.get("op") == "not":
        yield from _walk_predicates(node.get("of", {}))


def derived_bindings(requirement: Mapping[str, Any]) -> set[str]:
    """Evidence paths a requirement consumes, COMPUTED by walking its predicate.

    Never hand-declared: a hand-written binding drifts the moment someone edits
    the predicate and not the binding, and a drifted binding produces a verdict
    whose provenance chain points at the wrong evidence.
    """
    paths: set[str] = set()
    pred = requirement.get("predicate")
    if not pred:
        return paths
    for operand in _walk_operands(pred):
        if "field" in operand:
            paths.add(operand["field"])
        elif "aggregate" in operand:
            paths.add(f"{operand['over']}.{operand['select']}")
    return paths


def capability_paths(registry: Mapping[str, Any]) -> set[str]:
    """The union of every evidence path the registered adapters can produce."""
    return {
        path
        for adapter in registry.get("adapters", [])
        for capability in adapter.get("capabilities", [])
        for path in capability.get("provides", [])
    }


def validate(
    pack: Mapping[str, Any],
    registry: Mapping[str, Any] | None = None,
    schema: Mapping[str, Any] | None = None,
) -> list[Violation]:
    """Return every violation. An empty list means the pack may be adopted."""
    v: list[Violation] = []
    requirements: Sequence[Mapping[str, Any]] = pack.get("requirements", [])

    # 1 -- structural conformance
    if schema is not None:
        try:
            from jsonschema import Draft7Validator
        except ImportError:  # pragma: no cover
            v.append(Violation(1, None, "jsonschema not installed; cannot verify"))
        else:
            for err in sorted(Draft7Validator(schema).iter_errors(pack),
                              key=lambda e: list(e.path)):
                v.append(Violation(1, None, f"{list(err.path)}: {err.message}"))

    by_id: dict[str, Mapping[str, Any]] = {}
    for req in requirements:
        rid = req.get("id")
        # 2 -- duplicate ids
        if rid in by_id:
            v.append(Violation(2, rid, "duplicate requirement id"))
        by_id[rid] = req

    for req in requirements:
        rid = req.get("id")
        operator = req.get("operator")
        children = req.get("children", [])
        pred = req.get("predicate")

        # 2 -- unresolvable child references
        for child in children:
            if child not in by_id:
                v.append(Violation(2, rid, f"child {child!r} does not resolve"))

        # 4 -- k in range
        if operator == "K_OF_N":
            k = req.get("k")
            if k is None or not (1 <= k <= len(children)):
                v.append(Violation(4, rid, f"k={k} out of range for {len(children)} children"))

        # 5 -- leaf/interior shape
        if operator == "LEAF" and not pred:
            v.append(Violation(5, rid, "LEAF without a predicate"))
        if operator and operator != "LEAF" and not children:
            v.append(Violation(5, rid, f"{operator} without children"))

        # 6 -- NOT arity
        if operator == "NOT" and len(children) != 1:
            v.append(Violation(6, rid, f"NOT takes exactly one child, got {len(children)}"))

        # 7 -- closed operator and operand vocabulary
        for p in _walk_predicates(pred or {}):
            if p.get("op") not in OPERATORS:
                v.append(Violation(7, rid, f"unknown operator {p.get('op')!r}"))
        for operand in _walk_operands(pred or {}):
            kinds = OPERAND_KINDS & set(operand)
            if len(kinds) != 1:
                v.append(Violation(7, rid, f"operand must have exactly one kind, got {sorted(operand)}"))

        # 9 -- currency literals are integers
        for operand in _walk_operands(pred or {}):
            lit = operand.get("literal")
            if isinstance(lit, float):
                v.append(Violation(9, rid, "currency literal must be an integer in minor units"))

        # 10 -- no wall clock: temporal values come only from the context
        for operand in _walk_operands(pred or {}):
            if operand.get("field") in ("now", "today", "current_date"):
                v.append(Violation(10, rid, "predicate may not read the system clock"))
            if operand.get("literal") in ("now", "today"):
                v.append(Violation(10, rid, "predicate may not read the system clock"))

        # 11 -- unreviewed uncertainty blocks adoption
        if req.get("review_required"):
            note = req.get("review_note", "no note given")
            v.append(Violation(11, rid, f"awaiting human review: {note}"))

        # 12 -- provenance into the tender document
        if "page" not in (req.get("source") or {}):
            v.append(Violation(12, rid, "source.page is required"))

        # 8 -- every consumed evidence path must be producible
        if registry is not None:
            producible = capability_paths(registry)
            for path in derived_bindings(req):
                if path not in producible:
                    v.append(Violation(
                        8, rid,
                        f"no registered capability provides {path!r}; this "
                        f"requirement could only ever be UNKNOWN"))

    # 3 -- the requirement graph must be a tree
    v.extend(_cycle_violations(by_id))

    # 13 -- declared hash matches the canonical form
    declared = pack.get("content_hash")
    if declared and declared != content_hash(pack):
        v.append(Violation(13, None, "content_hash disagrees with the canonical form"))

    return v


def _cycle_violations(by_id: Mapping[str, Mapping[str, Any]]) -> list[Violation]:
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {rid: WHITE for rid in by_id}
    found: list[Violation] = []

    def visit(rid: str, path: list[str]) -> None:
        if colour.get(rid) == GREY:
            cycle = " -> ".join(path[path.index(rid):] + [rid])
            found.append(Violation(3, rid, f"cycle in the requirement graph: {cycle}"))
            return
        if colour.get(rid) != WHITE:
            return
        colour[rid] = GREY
        for child in by_id[rid].get("children", []):
            if child in by_id:
                visit(child, path + [rid])
        colour[rid] = BLACK

    for rid in by_id:
        if colour[rid] == WHITE:
            visit(rid, [])
    return found
