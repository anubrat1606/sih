"""Tender Compliance Report: the aggregate view across every bidder on one
tender -- "of everyone who bid, where do we stand overall?"

The Compliance Dossier (dossier.py) answers that question for one bidder.
Nothing before this aggregated it across a tender's whole bidder list.

`tender_report()` does no database work, no I/O, and recomputes nothing that
was already computed -- it only aggregates. `bidders` is exactly
GET /tenders/{tender_id}/bidders's "bidders" list, and each element is
exactly what GET /bidders/{id} returns (the same shape dossier.py's
`bidder` argument uses). Collusion clustering in particular is never
redone here: a flagged bidder's own `collusion.cluster_id` is trusted as-is
and only grouped, the same "carry through, never re-derive" rule dossier.py
follows for verdicts and classifications.
"""
from __future__ import annotations

from typing import Any, Mapping

_RISK_LEVELS = ("LOW", "MEDIUM", "HIGH")
_METRIC_KEYS = ("compliance_score", "verification_coverage", "evidence_confidence")


def _summarize(values: list[float | None]) -> dict[str, Any]:
    """Mean/min/max over the non-null values only, plus how many were null --
    a null must never silently vanish from the denominator, and an empty or
    all-null input must never be reported as a fabricated 0."""
    present = [v for v in values if v is not None]
    null_count = len(values) - len(present)
    if not present:
        return {"mean": None, "min": None, "max": None, "count": 0, "null_count": null_count}
    return {
        "mean": sum(present) / len(present),
        "min": min(present),
        "max": max(present),
        "count": len(present),
        "null_count": null_count,
    }


def tender_report(tender_id: str, bidders: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate every bidder's already-computed picture into one report."""
    risk_distribution = {level: 0 for level in _RISK_LEVELS}
    for b in bidders:
        level = b["risk"]["level"]
        risk_distribution[level] = risk_distribution.get(level, 0) + 1

    # Group what each bidder's own collusion field already says -- an
    # unflagged entry (an isolated node with no shared attribute) is not a
    # cluster membership, and a bidder with no collusion signal at all
    # (`collusion` is None) is simply absent from every count below.
    cluster_ids: set[str] = set()
    bidder_clusters: dict[str, str] = {}
    flagged_count = 0
    for b in bidders:
        c = b.get("collusion")
        if c and c.get("flagged"):
            flagged_count += 1
            cluster_ids.add(c["cluster_id"])
            bidder_clusters[b["bidder_id"]] = c["cluster_id"]

    report: dict[str, Any] = {
        "tender_id": tender_id,
        "bidder_count": len(bidders),
        "risk_distribution": risk_distribution,
        "collusion": {
            "cluster_count": len(cluster_ids),
            "flagged_bidder_count": flagged_count,
            "bidder_clusters": bidder_clusters,
        },
    }
    for key in _METRIC_KEYS:
        report[key] = _summarize([b["metrics"][key] for b in bidders])
    return report


def render_tender_report_text(report: Mapping[str, Any]) -> str:
    """A plain-text rendering suitable for printing or pasting into a
    dashboard summary."""
    lines: list[str] = [
        "TENDER COMPLIANCE REPORT",
        f"Tender: {report['tender_id']}",
        f"Bidders: {report['bidder_count']}",
        "",
        "RISK DISTRIBUTION",
    ]
    rd = report["risk_distribution"]
    for level in _RISK_LEVELS:
        lines.append(f"  {level}: {rd.get(level, 0)}")
    lines.append("")

    lines.append("COLLUSION")
    c = report["collusion"]
    lines.append(f"  Clusters: {c['cluster_count']}    Flagged bidders: {c['flagged_bidder_count']}")
    if c["bidder_clusters"]:
        for bidder_id, cluster_id in sorted(c["bidder_clusters"].items()):
            lines.append(f"    {bidder_id} -> {cluster_id}")
    else:
        lines.append("  No bidders flagged.")
    lines.append("")

    labels = {"compliance_score": "COMPLIANCE SCORE",
              "verification_coverage": "VERIFICATION COVERAGE",
              "evidence_confidence": "EVIDENCE CONFIDENCE"}
    for key in _METRIC_KEYS:
        s = report[key]
        lines.append(labels[key])
        if s["count"] == 0:
            lines.append(f"  No data ({s['null_count']} bidder(s) not yet determined).")
        else:
            lines.append(f"  Mean: {s['mean']:.1f}   Min: {s['min']:.1f}   Max: {s['max']:.1f}   "
                          f"({s['count']} determined, {s['null_count']} not yet determined)")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
