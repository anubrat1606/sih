"""Projections: rebuildable caches folded from the event log.

They are never patched. `rebuild_projections` drops and refolds from genesis,
and a test asserts the result is identical to the incrementally-maintained
tables -- which is what makes determinism enforced rather than aspirational.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Cluster:
    bidder_id: str
    flagged: bool
    cluster_id: str
    members: tuple[str, ...]


def collusion_clusters(conn, tender_id: str) -> list[Cluster]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT bidder_id, flagged, cluster_id, members "
            "FROM collusion_clusters(%s) ORDER BY bidder_id",
            (tender_id,),
        )
        return [Cluster(b, f, c, tuple(m)) for b, f, c, m in cur.fetchall()]


def collusion_clusters_as_of(conn, tender_id: str, up_to_seq: int) -> list[Cluster]:
    """The Temporal Scrubber's counterpart to `collusion_clusters` -- the
    same connected-components clustering, folded only from
    SHARED_ATTRIBUTE_OBSERVED and BIDDER_REGISTERED events up to a past
    seq, via sql/009_collusion_as_of.sql's `collusion_clusters_as_of`
    (read-only, no table touched -- same safety property every other
    as-of fold in this module has). Round 8's `bidder_as_of` endpoint
    shipped with a stated gap here (collusion was always current, never
    historical); this closes it."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT bidder_id, flagged, cluster_id, members "
            "FROM collusion_clusters_as_of(%s, %s) ORDER BY bidder_id",
            (tender_id, up_to_seq),
        )
        return [Cluster(b, f, c, tuple(m)) for b, f, c, m in cur.fetchall()]


def provenance_trail(conn, bidder_id: str, requirement_id: str) -> list[dict[str, Any]]:
    """The causation chain behind one verdict: verdict -> fused evidence ->
    verification -> extraction (with page and region) -> source document."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT depth, event_type, seq, occurred_at, payload "
            "FROM provenance_trail(%s, %s)",
            (bidder_id, requirement_id),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


#: Advisory lock key for the rebuild below. Any stable bigint works; it only
#: has to be the same number in every process that talks to this database.
REBUILD_LOCK_KEY = 7_411_001


def rebuild_projections(conn, up_to_seq: int | None = None) -> dict[str, int]:
    """Truncate and fold from genesis.

    `up_to_seq` gives time travel: fold to sequence N and the projection is the
    state as of that moment. The TemporalScrubber UI is deferred, but the
    capability underneath it costs nothing extra, so the query stays supported.

    Seen live (Render, 2026-09-12): the officer dashboard fires several
    requests at once and more than one of them rebuilds. Pool connections are
    autocommit, so DELETE-then-INSERT from two requests interleaved -- both
    deleted, both inserted the same tender -- and one died with
    UniqueViolation on proj_tenders_pkey (and, a minute earlier, on
    proj_collusion_pkey). A 500 from there escapes the CORS middleware, which
    is why the browser reported it as a CORS/ERR_FAILED failure rather than
    an error the page could show. One transaction plus a transaction-scoped
    advisory lock makes concurrent rebuilds queue instead of interleave, and
    means a reader never sees the cache empty between the DELETE and the
    INSERTs either.
    """
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (REBUILD_LOCK_KEY,))
        return _rebuild_locked(conn, up_to_seq)


def fold_verdicts_as_of(conn, up_to_seq: int, bidder_id: str | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """The pure computation half of the verdicts fold: reads events up to a
    ceiling and returns the folded `(bidder_id, requirement_id) -> row` dict
    -- no cursor writes, no table touched. `_rebuild_locked` below is the
    only caller that persists this (to `proj_verdicts`, for every bidder,
    always at the live tip); the Temporal Scrubber's `as-of` endpoint
    (app.py) is the other caller, scoped to one bidder and a past `up_to_seq`,
    and never writes anything -- reading history must never risk the state
    every other concurrent request's `GET /bidders/{id}` reads, which is
    exactly the class of bug fixed here for the live path (see
    `rebuild_projections`'s own docstring).
    """
    with conn.cursor() as cur:
        if bidder_id is None:
            cur.execute(
                """SELECT event_id, event_type, tender_id, bidder_id, payload, seq
                   FROM events
                   WHERE event_type IN ('REQUIREMENT_EVALUATED','VERDICT_OVERRIDDEN')
                     AND seq <= %s
                   ORDER BY seq""",
                (up_to_seq,),
            )
        else:
            cur.execute(
                """SELECT event_id, event_type, tender_id, bidder_id, payload, seq
                   FROM events
                   WHERE event_type IN ('REQUIREMENT_EVALUATED','VERDICT_OVERRIDDEN')
                     AND bidder_id = %s AND seq <= %s
                   ORDER BY seq""",
                (bidder_id, up_to_seq),
            )
        rows = cur.fetchall()

    verdicts: dict[tuple[str, str], dict[str, Any]] = {}
    for event_id, etype, tender, bidder, payload, seq in rows:
        key = (bidder, payload["requirement_id"])
        if etype == "REQUIREMENT_EVALUATED":
            verdicts[key] = {
                "bidder_id": bidder, "tender_id": tender,
                "requirement_id": payload["requirement_id"],
                "verdict_system": payload["verdict"],
                "reason_system": payload["reason_code"],
                "verdict_effective": payload["verdict"],
                "reason_effective": payload["reason_code"],
                "overridden_by": None, "override_justification": None,
                "rule_pack_version": payload["rule_pack_version"],
                "causation_event": event_id, "built_from_seq": seq,
            }
        else:
            row = verdicts.get(key)
            if row is None:
                # An override with no prior evaluation is a real anomaly.
                # Recording it beats silently dropping it.
                continue
            # The system's own conclusion is preserved, never overwritten.
            row["verdict_effective"] = payload["verdict_after"]
            row["reason_effective"] = payload.get("reason_after", row["reason_system"])
            row["overridden_by"] = payload["officer_id"]
            row["override_justification"] = payload["justification"]
            row["built_from_seq"] = seq
    return verdicts


def _rebuild_locked(conn, up_to_seq: int | None) -> dict[str, int]:
    ceiling = up_to_seq if up_to_seq is not None else _tip(conn)
    counts = {"proj_verdicts": 0, "proj_collusion": 0, "proj_tenders": 0}

    with conn.cursor() as cur:
        # proj_verdicts, proj_collusion and proj_tenders are caches, not the
        # log: DELETE here is correct and is exactly why they are separate
        # tables from `events`.
        cur.execute("DELETE FROM proj_verdicts")
        cur.execute("DELETE FROM proj_collusion")
        cur.execute("DELETE FROM proj_tenders")

        verdicts = fold_verdicts_as_of(conn, ceiling)

        for row in verdicts.values():
            cur.execute(
                """INSERT INTO proj_verdicts (bidder_id,tender_id,requirement_id,
                       verdict_system,reason_system,verdict_effective,reason_effective,
                       overridden_by,override_justification,rule_pack_version,
                       causation_event,built_from_seq)
                   VALUES (%(bidder_id)s,%(tender_id)s,%(requirement_id)s,
                       %(verdict_system)s,%(reason_system)s,%(verdict_effective)s,
                       %(reason_effective)s,%(overridden_by)s,%(override_justification)s,
                       %(rule_pack_version)s,%(causation_event)s,%(built_from_seq)s)""",
                row,
            )
        counts["proj_verdicts"] = len(verdicts)

        cur.execute("SELECT DISTINCT tender_id FROM bidder_in_tender")
        for (tender,) in cur.fetchall():
            cur.execute(
                """INSERT INTO proj_collusion
                       (tender_id,bidder_id,flagged,cluster_id,members,built_from_seq)
                   SELECT %s, bidder_id, flagged, cluster_id, members, %s
                   FROM collusion_clusters(%s)""",
                (tender, ceiling, tender),
            )
            counts["proj_collusion"] += cur.rowcount

        cur.execute(
            """SELECT tender_id, payload, seq FROM events
               WHERE event_type='TENDER_CREATED' AND seq <= %s ORDER BY seq""",
            (ceiling,))
        tenders: dict[str, dict[str, Any]] = {}
        for tender, payload, seq in cur.fetchall():
            tenders[tender] = {
                "tender_id": tender, "title": payload["title"],
                "issuing_authority": payload["issuing_authority"],
                "bid_submission_deadline": payload.get("bid_submission_deadline"),
                "description": payload.get("description"),
                "created_by": payload["created_by"], "built_from_seq": seq,
                "department": payload.get("department"),
                "category": payload.get("category"),
                "issue_date": payload.get("issue_date"),
            }
        for row in tenders.values():
            cur.execute(
                """INSERT INTO proj_tenders (tender_id,title,issuing_authority,
                       bid_submission_deadline,description,created_by,built_from_seq,
                       department,category,issue_date)
                   VALUES (%(tender_id)s,%(title)s,%(issuing_authority)s,
                       %(bid_submission_deadline)s,%(description)s,%(created_by)s,
                       %(built_from_seq)s,%(department)s,%(category)s,%(issue_date)s)""",
                row)
        counts["proj_tenders"] = len(tenders)
    return counts


def _tip(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(seq), 0) FROM events")
        return cur.fetchone()[0]
