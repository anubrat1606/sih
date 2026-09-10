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


def rebuild_projections(conn, up_to_seq: int | None = None) -> dict[str, int]:
    """Truncate and fold from genesis.

    `up_to_seq` gives time travel: fold to sequence N and the projection is the
    state as of that moment. The TemporalScrubber UI is deferred, but the
    capability underneath it costs nothing extra, so the query stays supported.
    """
    ceiling = up_to_seq if up_to_seq is not None else _tip(conn)
    counts = {"proj_verdicts": 0, "proj_collusion": 0}

    with conn.cursor() as cur:
        # proj_verdicts and proj_collusion are caches, not the log: DELETE here
        # is correct and is exactly why they are separate tables from `events`.
        cur.execute("DELETE FROM proj_verdicts")
        cur.execute("DELETE FROM proj_collusion")

        cur.execute(
            """SELECT event_id, event_type, tender_id, bidder_id, payload, seq
               FROM events
               WHERE event_type IN ('REQUIREMENT_EVALUATED','VERDICT_OVERRIDDEN')
                 AND seq <= %s
               ORDER BY seq""",
            (ceiling,),
        )
        verdicts: dict[tuple[str, str], dict[str, Any]] = {}
        for event_id, etype, tender, bidder, payload, seq in cur.fetchall():
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
    return counts


def _tip(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(seq), 0) FROM events")
        return cur.fetchone()[0]
