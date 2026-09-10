"""A hash chain under concurrent writers.

Two transactions that both read tip N and both commit would fork the chain --
and a forked chain silently destroys the exact property the chain exists to
provide. Naive implementations get this wrong and never notice, because it only
manifests under load. This test puts it under load.
"""
import os
import threading
import uuid

import pytest

from satyapramana_store import Actor, append, connect, export_jsonl, verify_chain

SYS = Actor("SYSTEM", "worker")
WRITERS, PER_WRITER = 8, 25


def test_concurrent_writers_cannot_fork_the_chain(conn, dsn):
    errors: list[Exception] = []
    written = threading.Semaphore(0)

    def writer(n: int) -> None:
        try:
            c = connect(dsn)
            for i in range(PER_WRITER):
                append(c, event_type="FIELD_EXTRACTED", actor=SYS,
                       correlation_id=str(uuid.uuid4()), tender_id="T1",
                       bidder_id="A", payload={"worker": n, "i": i})
                written.release()
            c.close()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(WRITERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"writers failed: {errors[:3]}"

    with conn.cursor() as cur:
        cur.execute("SELECT count(*), count(DISTINCT prev_hash), count(DISTINCT hash) "
                    "FROM events")
        total, distinct_prev, distinct_hash = cur.fetchone()

    assert total == WRITERS * PER_WRITER
    assert distinct_prev == total, "a repeated prev_hash means a forked chain"
    assert distinct_hash == total

    report = verify_chain(list(export_jsonl(conn)))
    assert report.intact, f"chain broken at {report.breaks[:3]}"
    assert report.events == report.linked == report.rehashed == total


def test_seq_order_and_chain_order_agree(conn, dsn):
    """The export is ordered by seq, so seq order must be chain order. Because
    the sequence value is assigned inside the same lock that reads the tip,
    they cannot diverge."""
    def writer(n: int) -> None:
        c = connect(dsn)
        for i in range(10):
            append(c, event_type="FIELD_EXTRACTED", actor=SYS,
                   correlation_id=str(uuid.uuid4()), payload={"w": n, "i": i})
        c.close()

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with conn.cursor() as cur:
        cur.execute("SELECT seq, prev_hash, hash FROM events ORDER BY seq")
        rows = cur.fetchall()
    for (_, _, earlier_hash), (_, later_prev, _) in zip(rows, rows[1:]):
        assert later_prev == earlier_hash
