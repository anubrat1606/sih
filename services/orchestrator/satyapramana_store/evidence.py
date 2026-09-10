"""The evidence projection and the resolver the rule engine reads through.

Folded from FIELD_EXTRACTED, VERIFICATION_OBSERVED and VERIFICATION_FAILED. The
important property: when a path cannot be resolved, the projection carries *why*
-- taken from the evidence record itself, never guessed by the evaluator. That
is what makes a leaf say "the authority was unavailable" rather than a generic
placeholder, all the way to the officer's screen.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from satyapramana.predicates import Resolved
from satyapramana.verdicts import Channel, Reason, Tier

from .adapters import Registry


@dataclass(frozen=True)
class EvidenceRecord:
    path: str
    resolved: bool
    value: Any = None
    unresolved_reason: Reason | None = None
    tier: Tier | None = None
    channel: Channel | None = None
    capability_id: str | None = None
    source_event: str | None = None


def rebuild_evidence(conn, bidder_id: str, registry: Registry,
                     up_to_seq: int | None = None) -> int:
    """Fold this bidder's evidence. Later events win, so a re-verification
    supersedes an earlier failure without either being erased from the log."""
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(seq),0) FROM events")
        ceiling = up_to_seq if up_to_seq is not None else cur.fetchone()[0]

        cur.execute("DELETE FROM proj_evidence WHERE bidder_id=%s", (bidder_id,))
        cur.execute(
            """SELECT event_id, event_type, payload, occurred_at, seq
               FROM events
               WHERE bidder_id=%s AND seq<=%s
                 AND event_type IN ('FIELD_EXTRACTED','VERIFICATION_OBSERVED',
                                    'VERIFICATION_FAILED','EXTRACTION_FAILED')
               ORDER BY seq""",
            (bidder_id, ceiling))
        rows = cur.fetchall()

        records: dict[str, dict[str, Any]] = {}
        for event_id, etype, payload, occurred_at, seq in rows:
            if etype == "FIELD_EXTRACTED":
                records[payload["path"]] = {
                    "path": payload["path"], "resolved": True,
                    "value": payload.get("value"), "unresolved_reason": None,
                    "tier": Tier.C.value, "channel": None, "capability_id": None,
                    "observed_at": occurred_at, "source_asserted_at": None,
                    "source_event": event_id, "built_from_seq": seq,
                }
            elif etype == "EXTRACTION_FAILED":
                records[payload["path"]] = {
                    "path": payload["path"], "resolved": False, "value": None,
                    "unresolved_reason": payload.get(
                        "reason_code", Reason.EXTRACTION_FAILED.value),
                    "tier": None, "channel": None, "capability_id": None,
                    "observed_at": occurred_at, "source_asserted_at": None,
                    "source_event": event_id, "built_from_seq": seq,
                }
            elif etype == "VERIFICATION_OBSERVED":
                for obs in payload.get("observations", []):
                    records[obs["path"]] = {
                        "path": obs["path"], "resolved": True,
                        "value": obs.get("value"), "unresolved_reason": None,
                        "tier": obs.get("tier"), "channel": obs.get("channel"),
                        "capability_id": payload.get("capability_id"),
                        "observed_at": occurred_at,
                        "source_asserted_at": payload.get("source_asserted_at"),
                        "source_event": event_id, "built_from_seq": seq,
                    }
            else:  # VERIFICATION_FAILED
                # Every path the capability WOULD have produced becomes an
                # unresolved record carrying the real reason. Without this the
                # rule engine could not distinguish "never attempted" from
                # "attempted and the authority was down".
                found = registry.for_capability(payload["capability_id"])
                paths = found[1].provides if found else ()
                for path in paths:
                    records[path] = {
                        "path": path, "resolved": False, "value": None,
                        "unresolved_reason": payload.get("reason_code"),
                        "tier": None, "channel": None,
                        "capability_id": payload["capability_id"],
                        "observed_at": occurred_at, "source_asserted_at": None,
                        "source_event": event_id, "built_from_seq": seq,
                    }

        import json as _json
        for rec in records.values():
            cur.execute(
                """INSERT INTO proj_evidence (bidder_id,path,resolved,value,
                       unresolved_reason,tier,channel,capability_id,observed_at,
                       source_asserted_at,source_event,built_from_seq)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (bidder_id, rec["path"], rec["resolved"],
                 _json.dumps(rec["value"]) if rec["resolved"] else None,
                 rec["unresolved_reason"], rec["tier"], rec["channel"],
                 rec["capability_id"], rec["observed_at"],
                 rec["source_asserted_at"], rec["source_event"],
                 rec["built_from_seq"]))
    return len(records)


class ProjectionResolver:
    """Implements the Resolver protocol in satyapramana.predicates, backed by
    proj_evidence. The rule engine never touches the event log directly."""

    def __init__(self, conn, bidder_id: str):
        self._records: dict[str, EvidenceRecord] = {}
        with conn.cursor() as cur:
            cur.execute(
                """SELECT path,resolved,value,unresolved_reason,tier,channel,
                          capability_id,source_event
                   FROM proj_evidence WHERE bidder_id=%s""", (bidder_id,))
            for (path, resolved, value, reason, tier, channel,
                 capability_id, source_event) in cur.fetchall():
                self._records[path] = EvidenceRecord(
                    path=path, resolved=resolved, value=value,
                    unresolved_reason=Reason(reason) if reason else None,
                    tier=Tier(tier) if tier else None,
                    channel=Channel(channel) if channel else None,
                    capability_id=capability_id,
                    source_event=str(source_event) if source_event else None)

    def record(self, path: str) -> EvidenceRecord | None:
        return self._records.get(path)

    def field(self, path: str) -> Resolved:
        rec = self._records.get(path)
        if rec is None:
            # Nothing ever produced this path -- distinct from an attempt that
            # failed, and the reason says so.
            return Resolved.missing(Reason.NO_ADAPTER_FOR_FIELD)
        if not rec.resolved:
            return Resolved.missing(rec.unresolved_reason or Reason.EXTRACTION_FAILED)
        return Resolved(rec.value)

    def collection(self, path: str) -> Resolved:
        return self.field(path)

    def tiers_for(self, paths) -> list[Tier]:
        """Supporting tiers, for the Tier C ceiling. Only resolved evidence
        counts -- an unresolved path supports nothing."""
        return [r.tier for p in paths
                if (r := self._records.get(p)) and r.resolved and r.tier]

    def source_events(self, paths) -> list[str]:
        return [r.source_event for p in sorted(paths)
                if (r := self._records.get(p)) and r.source_event]
