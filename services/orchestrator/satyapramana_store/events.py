"""Append-only event log: canonical hashing, appending, export, verification.

docs/EVENTS.md. The canonical form is defined here, in one language, so that the
independent verifier of section 8 reproduces it exactly. Computing it in SQL
would force a third party to replicate PostgreSQL's jsonb key ordering, which
is not a reasonable thing to ask of an auditor.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Mapping

GENESIS = "0" * 64

#: Sorted keys, no insignificant whitespace, UTF-8. Same rule as rule packs.
CANONICAL = dict(sort_keys=True, separators=(",", ":"), ensure_ascii=False)

#: The fields covered by the hash, in a fixed order. Adding a field here is a
#: breaking change to every previously exported chain, so it never happens
#: silently: the export carries a chain_format version.
HASHED_FIELDS = (
    "event_id", "event_type", "occurred_at", "actor_kind", "actor_id",
    "correlation_id", "causation_id", "tender_id", "bidder_id", "payload",
)

CHAIN_FORMAT = "satyapramana/chain/1"


def canonical_ts(dt: datetime) -> str:
    """The one rendering of an instant that enters a hash preimage.

    PostgreSQL returns `timestamptz` in the *client session's* timezone, so the
    same instant reads back as '...T09:20:54.957687+00:00' in UTC and
    '...T14:50:54.957687+05:30' in Asia/Kolkata. Hashing whatever the driver
    happened to render would make chain verification depend on the auditor's
    own timezone -- the identical export would verify for one reader and fail
    for another. Always UTC, always microseconds, always '+00:00'.
    """
    if dt.tzinfo is None:
        raise ValueError("occurred_at must be timezone-aware")
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")


class ChainFork(RuntimeError):
    """Two writers tried to claim the same predecessor."""


def canonical_preimage(prev_hash: str, event: Mapping[str, Any]) -> str:
    body = {k: event.get(k) for k in HASHED_FIELDS}
    return prev_hash + json.dumps(body, **CANONICAL)


def event_hash(prev_hash: str, event: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_preimage(prev_hash, event).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Actor:
    kind: str   # HUMAN | AGENT | ADAPTER | SYSTEM
    id: str

    def __post_init__(self) -> None:
        if self.kind not in ("HUMAN", "AGENT", "ADAPTER", "SYSTEM"):
            raise ValueError(f"unknown actor kind: {self.kind}")


#: The only event types a human may emit -- creating a tender, adopting
#: rules, overriding a verdict, recording a decision. Every other HUMAN
#: event is a bug.
HUMAN_EVENT_TYPES = frozenset({
    "TENDER_CREATED", "RULE_PACK_ADOPTED", "VERDICT_OVERRIDDEN", "DECISION_RECORDED",
    "DECLARATION_RECORDED",
})


def append(
    conn,
    *,
    event_type: str,
    actor: Actor,
    correlation_id: str | uuid.UUID,
    payload: Mapping[str, Any],
    causation_id: str | uuid.UUID | None = None,
    tender_id: str | None = None,
    bidder_id: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Append one event, hashed onto the current tip.

    The tip read and the insert are wrapped in one explicit transaction so the
    advisory lock is actually *held* across both. Under `autocommit=True` each
    statement is its own transaction, which releases the lock immediately and
    leaves every concurrent writer colliding -- an inert lock that looks correct
    in review and only shows up under load.

    Correctness never depended on the lock: UNIQUE(prev_hash) plus the chain
    trigger make a fork impossible at the database level, so a losing writer
    fails loudly rather than silently branching the log. The lock is what turns
    "loud failure" into "no failure" when writers contend.
    """
    if actor.kind == "HUMAN" and event_type not in HUMAN_EVENT_TYPES:
        raise ValueError(
            f"{event_type} may not be emitted by a HUMAN actor; only "
            f"{sorted(HUMAN_EVENT_TYPES)} may be"
        )
    if event_type == "VERDICT_OVERRIDDEN" and not payload.get("justification"):
        raise ValueError("VERDICT_OVERRIDDEN requires a justification")

    at = occurred_at or datetime.now(timezone.utc)
    record = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "occurred_at": canonical_ts(at),
        "actor_kind": actor.kind,
        "actor_id": actor.id,
        "correlation_id": str(correlation_id),
        "causation_id": str(causation_id) if causation_id else None,
        "tender_id": tender_id,
        "bidder_id": bidder_id,
        "payload": dict(payload),
    }

    with conn.transaction(), conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("satyapramana.event_chain",))
        cur.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1")
        row = cur.fetchone()
        prev = row[0] if row else GENESIS
        record["prev_hash"] = prev
        record["hash"] = event_hash(prev, record)
        try:
            cur.execute(
                """INSERT INTO events (event_id,event_type,occurred_at,actor_kind,
                       actor_id,correlation_id,causation_id,tender_id,bidder_id,
                       payload,prev_hash,hash)
                   VALUES (%(event_id)s,%(event_type)s,%(occurred_at)s,%(actor_kind)s,
                       %(actor_id)s,%(correlation_id)s,%(causation_id)s,%(tender_id)s,
                       %(bidder_id)s,%(payload)s,%(prev_hash)s,%(hash)s)
                   RETURNING seq""",
                {**record, "payload": json.dumps(record["payload"], **CANONICAL)},
            )
            record["seq"] = cur.fetchone()[0]
        except Exception as exc:  # noqa: BLE001
            if "prev_hash" in str(exc) or "chain fork" in str(exc):
                raise ChainFork(str(exc)) from exc
            raise
    return record


def export_jsonl(conn) -> Iterator[str]:
    """One event per line in seq order. This is the artefact a third party
    verifies without any access to the database or the application."""
    yield json.dumps({"chain_format": CHAIN_FORMAT, "genesis": GENESIS}, **CANONICAL)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT event_id,event_type,occurred_at,actor_kind,actor_id,
                      correlation_id,causation_id,tender_id,bidder_id,payload,
                      prev_hash,hash,seq
               FROM events ORDER BY seq"""
        )
        cols = [d[0] for d in cur.description]
        for row in cur:
            rec = dict(zip(cols, row))
            rec["event_id"] = str(rec["event_id"])
            rec["correlation_id"] = str(rec["correlation_id"])
            rec["causation_id"] = str(rec["causation_id"]) if rec["causation_id"] else None
            rec["occurred_at"] = canonical_ts(rec["occurred_at"])
            yield json.dumps(rec, **CANONICAL)


@dataclass(frozen=True)
class ChainReport:
    events: int
    linked: int
    rehashed: int
    breaks: tuple[tuple[int, str], ...]

    @property
    def intact(self) -> bool:
        return not self.breaks


def verify_chain(lines: Iterable[str]) -> ChainReport:
    """Independent verification. Needs the export and nothing else -- no
    database, no application code, no cooperation from us.

    Detects tampering at the *successor* of an altered event, because that is
    where prev_hash stops matching. An attacker must therefore rewrite every
    event from the point of tampering to the tip, which anyone holding an
    earlier copy of the export can see.
    """
    prev, n, linked, rehashed = GENESIS, 0, 0, 0
    breaks: list[tuple[int, str]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if "chain_format" in rec:
            if rec["chain_format"] != CHAIN_FORMAT:
                breaks.append((0, f"unknown chain format {rec['chain_format']!r}"))
            continue
        n += 1
        if rec["prev_hash"] != prev:
            breaks.append((rec["seq"], "prev_hash does not match the preceding hash"))
        else:
            linked += 1
        recomputed = event_hash(rec["prev_hash"], rec)
        if recomputed != rec["hash"]:
            breaks.append((rec["seq"], "hash does not match its own contents"))
        else:
            rehashed += 1
        prev = rec["hash"]
    return ChainReport(n, linked, rehashed, tuple(breaks))
