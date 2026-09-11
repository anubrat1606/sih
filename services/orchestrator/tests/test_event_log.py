"""The append-only hash-chained log, against a real PostgreSQL."""
import json
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from satyapramana_store import (
    GENESIS, Actor, ChainFork, append, event_hash, export_jsonl, verify_chain,
)

SYS = Actor("SYSTEM", "test")
CORR = str(uuid.uuid4())


def emit(conn, n=1, **kw):
    return [append(conn, event_type="FIELD_EXTRACTED", actor=SYS,
                   correlation_id=CORR, payload={"i": i}, **kw)
            for i in range(n)]


# --- append-only enforcement --------------------------------------------------

def test_update_delete_truncate_are_all_refused(conn):
    """Row-level triggers do not fire on TRUNCATE, so it needs its own
    statement-level trigger. An earlier draft without it left the log wipeable."""
    emit(conn, 3)
    for stmt in ("UPDATE events SET actor_id='forged'",
                 "DELETE FROM events",
                 "TRUNCATE events"):
        # TRUNCATE is refused twice over: PostgreSQL rejects it outright while
        # rule_packs holds a foreign key into events, and the statement-level
        # trigger catches it otherwise. Either refusal is correct.
        with pytest.raises((psycopg.errors.RaiseException,
                            psycopg.errors.FeatureNotSupported)):
            with conn.cursor() as cur:
                cur.execute(stmt)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM events")
        assert cur.fetchone()[0] == 3


def test_a_non_hex_hash_is_refused(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO events (event_id,event_type,occurred_at,actor_kind,
                       actor_id,correlation_id,payload,prev_hash,hash)
                   VALUES (gen_random_uuid(),'X',now(),'SYSTEM','s',
                       gen_random_uuid(),'{}',%s,'genesis')""",
                (GENESIS,))


# --- the chain ----------------------------------------------------------------

def test_the_first_event_links_to_genesis(conn):
    assert emit(conn, 1)[0]["prev_hash"] == GENESIS


def test_each_event_links_to_its_predecessor(conn):
    events = emit(conn, 20)
    for earlier, later in zip(events, events[1:]):
        assert later["prev_hash"] == earlier["hash"]


def test_a_stale_tip_cannot_be_reused(conn):
    """UNIQUE(prev_hash) makes a fork a constraint violation rather than
    something only a lock prevents."""
    first, second = emit(conn, 2)
    with pytest.raises((ChainFork, psycopg.errors.RaiseException,
                        psycopg.errors.UniqueViolation)):
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO events (event_id,event_type,occurred_at,actor_kind,
                       actor_id,correlation_id,payload,prev_hash,hash)
                   VALUES (gen_random_uuid(),'X',now(),'SYSTEM','s',
                       gen_random_uuid(),'{}',%s,%s)""",
                (first["hash"], "a" * 64))


def test_prev_hash_is_unique(conn):
    emit(conn, 30)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), count(DISTINCT prev_hash) FROM events")
        total, distinct = cur.fetchone()
    assert total == distinct == 30, "a repeated prev_hash is a forked chain"


# --- independent verification -------------------------------------------------

def test_the_export_verifies_without_the_database(conn):
    emit(conn, 25)
    report = verify_chain(list(export_jsonl(conn)))
    assert report.intact
    assert report.events == report.linked == report.rehashed == 25


def test_naive_tampering_is_caught_at_the_altered_event(conn):
    """Altering a payload without recomputing the hash breaks that event's own
    hash. The successor still links fine, because its prev_hash refers to the
    stored hash, which was left alone."""
    emit(conn, 20)
    lines = list(export_jsonl(conn))
    forged = json.loads(lines[10])
    forged["payload"] = {"i": "forged"}
    lines[10] = json.dumps(forged, sort_keys=True, separators=(",", ":"))

    report = verify_chain(lines)
    assert not report.intact
    seqs = [s for s, _ in report.breaks]
    assert forged["seq"] in seqs, "the altered event fails its own hash"
    assert report.linked == report.events, "linkage is untouched by this attack"


def test_recomputing_the_hash_moves_the_break_to_the_successor(conn):
    """The competent attack: rewrite the payload AND its hash. Now the event is
    internally consistent, and the break surfaces one event later, where
    prev_hash no longer matches. The attacker must therefore rewrite every
    event from the tampering point to the tip -- which anyone holding an
    earlier copy of the export can see."""
    emit(conn, 10)
    lines = list(export_jsonl(conn))
    forged = json.loads(lines[5])
    forged["payload"] = {"i": "forged"}
    forged["hash"] = event_hash(forged["prev_hash"], forged)
    lines[5] = json.dumps(forged, sort_keys=True, separators=(",", ":"))

    report = verify_chain(lines)
    assert not report.intact
    assert forged["seq"] + 1 in [s for s, _ in report.breaks]


def test_an_unknown_chain_format_is_reported(conn):
    emit(conn, 2)
    lines = list(export_jsonl(conn))
    lines[0] = json.dumps({"chain_format": "someone-elses/2", "genesis": GENESIS})
    assert not verify_chain(lines).intact


# --- who may emit what --------------------------------------------------------

def test_only_the_named_event_types_may_have_a_human_actor(conn):
    with pytest.raises(ValueError, match="may not be emitted by a HUMAN"):
        append(conn, event_type="FIELD_EXTRACTED", actor=Actor("HUMAN", "officer_1"),
               correlation_id=CORR, payload={})


def test_an_override_requires_a_justification(conn):
    with pytest.raises(ValueError, match="justification"):
        append(conn, event_type="VERDICT_OVERRIDDEN", actor=Actor("HUMAN", "officer_1"),
               correlation_id=CORR,
               payload={"requirement_id": "R4.1", "verdict_after": "PASS",
                        "officer_id": "officer_1"})


def test_a_justified_override_is_accepted(conn):
    rec = append(conn, event_type="VERDICT_OVERRIDDEN", actor=Actor("HUMAN", "officer_1"),
                 correlation_id=CORR,
                 payload={"requirement_id": "R4.1", "verdict_after": "PASS",
                          "officer_id": "officer_1",
                          "justification": "Original certificate produced in person."})
    assert rec["actor_kind"] == "HUMAN"


def test_an_unknown_actor_kind_is_refused(conn):
    with pytest.raises(ValueError):
        Actor("ROBOT", "x")
