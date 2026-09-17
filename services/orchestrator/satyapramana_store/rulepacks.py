"""Rule pack adoption.

Adoption is a human act. The decomposer proposes; an officer adopts; the
adoption is an event carrying their identity, the content hash and a timestamp.
Validation gates it, and a pack containing an unreviewed uncertain requirement
cannot be adopted -- that is enforced here, not merely advised.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from satyapramana.rulepack import Violation, content_hash, rule_pack_version, validate

from .adapters import Registry
from .events import Actor, append

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "rule_pack.schema.json"


class NotAdoptable(ValueError):
    def __init__(self, violations: list[Violation]):
        self.violations = violations
        super().__init__("; ".join(str(v) for v in violations))


def _registry_as_dict(registry: Registry) -> dict[str, Any]:
    """Everything that can produce evidence, for rule 8.

    Adapters are only half of it. The deterministic extraction stage produces
    evidence too -- the identifiers it reads off a document -- and a rule pack
    that may not reference them could never express "the bidder stated a GSTIN".
    Rule 8's wording is "no producing stage or adapter"; both belong here.
    """
    from .extract.ingest import FIELD_PATHS

    adapters = [
        {"adapter_id": a.manifest.adapter_id,
         "capabilities": [{"provides": list(c.provides)}
                          for c in a.manifest.capabilities]}
        for a in registry.adapters]
    adapters.append({
        "adapter_id": "extract-deterministic",
        "capabilities": [{"provides": sorted(FIELD_PATHS.values())}]})
    return {"adapters": adapters}


def validate_only(pack: Mapping[str, Any], *, registry: Registry) -> tuple[dict[str, Any], list[Violation]]:
    """The exact same check `adopt()` gates on, without appending an event or
    writing to `rule_packs` -- a dry run for the admin builder's "Validate"
    step, kept separate from "Publish" (adopt) per the brief. Returns the
    content-hashed body (so a valid pack's real hash/version can be shown to
    the officer before they commit to adopting it) and the violation list
    (empty means valid).
    """
    body = {k: v for k, v in pack.items() if k != "content_hash"}
    body["content_hash"] = content_hash(body)
    schema = json.loads(SCHEMA_PATH.read_text())
    violations = validate(body, _registry_as_dict(registry), schema)
    return body, violations


def adopt(
    conn,
    pack: Mapping[str, Any],
    *,
    tender_id: str,
    officer_id: str,
    registry: Registry,
) -> dict[str, Any]:
    """Validate and adopt. Raises NotAdoptable with every violation.

    Rule 8 is checked against the live capability registry, so a pack
    referencing an evidence path nothing can produce is refused at adoption
    rather than becoming a permanent, unexplained UNKNOWN in production.
    """
    body, violations = validate_only(pack, registry=registry)
    if violations:
        raise NotAdoptable(violations)

    version = rule_pack_version(body)
    at = datetime.now(timezone.utc)

    event = append(
        conn, event_type="RULE_PACK_ADOPTED", actor=Actor("HUMAN", officer_id),
        correlation_id=str(__import__("uuid").uuid4()), tender_id=tender_id,
        payload={"rule_pack_version": version,
                 "rule_pack_id": body["rule_pack_id"],
                 "semver": body["semver"],
                 "content_hash": body["content_hash"],
                 "officer_id": officer_id,
                 "requirement_count": len(body["requirements"])})

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO rule_packs (rule_pack_version,rule_pack_id,semver,
                   content_hash,tender_id,body,adopted_at,adopted_by,adoption_event)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (rule_pack_version) DO NOTHING""",
            (version, body["rule_pack_id"], body["semver"], body["content_hash"],
             tender_id, json.dumps(body), at, officer_id, event["event_id"]))

    return {"rule_pack_version": version, "adoption_event": event["event_id"],
            "seq": event["seq"]}


def active_pack(conn, tender_id: str) -> tuple[str, dict[str, Any]] | None:
    """The most recently adopted pack for a tender. Earlier versions remain
    stored and citable -- nothing is superseded out of existence."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT rule_pack_version, body FROM rule_packs "
            "WHERE tender_id=%s ORDER BY adopted_at DESC LIMIT 1", (tender_id,))
        row = cur.fetchone()
    return (row[0], row[1]) if row else None


def active_pack_as_of(conn, tender_id: str, up_to_seq: int) -> tuple[str, dict[str, Any]] | None:
    """`active_pack`'s Temporal Scrubber counterpart: the pack that was
    active as of a past event, not the one active now. A tender can have
    more than one adoption over its life (a correction, a new version) --
    this picks the most recent one whose *adoption event* had already
    happened by `up_to_seq`, via the same `adoption_event` link `adopt()`
    already records, joined against `events` for its real sequence number.
    Read-only, no table touched -- `rule_packs` is itself insert-only
    (nothing here is ever superseded out of existence), so this is safe
    against a concurrent adoption the same way any other read of an
    append-only table is."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT rp.rule_pack_version, rp.body
               FROM rule_packs rp JOIN events e ON e.event_id = rp.adoption_event
               WHERE rp.tender_id=%s AND e.seq <= %s
               ORDER BY e.seq DESC LIMIT 1""",
            (tender_id, up_to_seq))
        row = cur.fetchone()
    return (row[0], row[1]) if row else None


def get_pack(conn, rule_pack_version: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute("SELECT body FROM rule_packs WHERE rule_pack_version=%s",
                    (rule_pack_version,))
        row = cur.fetchone()
    return row[0] if row else None
