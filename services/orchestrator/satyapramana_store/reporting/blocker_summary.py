"""Tender-wide blocker summary: across every bidder, which requirement is
blocking the most of them -- useful for an officer deciding whether a
requirement needs relaxing, or which document type to chase bidders for.

Each bidder's own Bid Autopsy (`bid_autopsy.py`) already says which
requirements block *them*. Nothing aggregates that across a tender; this
does, and nothing else -- no database, no I/O, no recomputation of a verdict
or classification, only counting and grouping what each autopsy already
says.
"""
from __future__ import annotations

from typing import Any, Mapping


def blocker_summary(autopsies: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """`autopsies` is a list of GET /bidders/{id}/autopsy's real response
    shape (see bid_autopsy.py's `autopsy()` return, or round 1's brief).

    An autopsy whose `would_qualify` is `None` (never evaluated) or `True`
    (nothing blocking) contributes nothing -- counting a not-yet-evaluated
    bidder as "blocked by nothing" would understate real blockers, so only
    a determinate blocked bidder (`would_qualify is False`) is counted.

    Returns one row per requirement_id that blocks at least one bidder,
    sorted by how many bidders it blocks (most first, requirement_id breaks
    a tie so the order is stable). Each row lists every classification
    (FATAL/CURABLE) actually seen for that requirement -- the same
    requirement can be FATAL for one bidder and CURABLE for another, since
    different bidders can hit it via different reason codes.
    """
    counts: dict[str, dict[str, Any]] = {}
    for a in autopsies:
        if a.get("would_qualify") is not False:
            continue
        for b in a.get("blocking_requirements", []):
            rid = b["requirement_id"]
            entry = counts.setdefault(
                rid, {"requirement_id": rid, "blocked_bidder_count": 0, "classifications": set()})
            entry["blocked_bidder_count"] += 1
            entry["classifications"].add(b["classification"])

    rows = [
        {**entry, "classifications": sorted(entry["classifications"])}
        for entry in counts.values()
    ]
    rows.sort(key=lambda r: (-r["blocked_bidder_count"], r["requirement_id"]))
    return rows
