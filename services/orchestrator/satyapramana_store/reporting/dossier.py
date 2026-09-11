"""Compliance Dossier: the single artifact an officer would print, attach to
a decision file, or hand to a supervisor.

docs/satyapramana.md section 11 lists Reporting as its own module, distinct
from Bid Autopsy and Compliance Repair -- a general compliance report/export,
not a diagnostic. This combines a bidder's full picture (score, risk,
verdicts, the autopsy, the repair plan) into one document.

Neither function here touches a database, calls an API, or does I/O. Both
take plain dicts -- exactly what GET /bidders/{id}, GET /bidders/{id}/autopsy,
and GET /bidders/{id}/repair-plan already return -- and return plain data.
Nothing is recomputed or re-judged here: a value this module didn't compute
(a verdict, a metric, a classification, an actionable_by) is carried through
unchanged, never re-derived and never guessed.
"""
from __future__ import annotations

from typing import Any, Mapping


def build_dossier(bidder: Mapping[str, Any], autopsy: Mapping[str, Any],
                   repair: Mapping[str, Any]) -> dict[str, Any]:
    """Combine the three already-computed views into one exportable artifact.

    `bidder` is GET /bidders/{id}'s response, `autopsy` is
    GET /bidders/{id}/autopsy's, `repair` is GET /bidders/{id}/repair-plan's.
    Repair actions are split by `actionable_by` so a renderer can never present
    a SYSTEM-side gap as something the bidder needs to fix -- the same rule
    compliance_repair.py itself follows; this module only carries it through.
    """
    actions_by_bidder = [a for a in repair.get("actions", []) if a["actionable_by"] == "BIDDER"]
    actions_by_system = [a for a in repair.get("actions", []) if a["actionable_by"] == "SYSTEM"]

    return {
        "bidder_id": bidder["bidder_id"],
        "tender_id": bidder["tender_id"],
        "metrics": dict(bidder["metrics"]),
        "risk": dict(bidder["risk"]),
        "collusion": bidder["collusion"],
        "verdicts": list(bidder["verdicts"]),
        "would_qualify": autopsy["would_qualify"],
        "blocking_requirements": list(autopsy["blocking_requirements"]),
        "counterfactual": autopsy["counterfactual"],
        "autopsy_note": autopsy["note"],
        "repair_actions_by_bidder": actions_by_bidder,
        "repair_actions_by_system": actions_by_system,
        "repair_note": repair.get("note"),
    }


def _fmt_metric(value: float | None, suffix: str = "") -> str:
    """Never a fabricated zero. A metric that was never determined renders as
    an honest "not determined", exactly like every other renderer in this
    codebase treats a null figure."""
    return "not determined" if value is None else f"{value:.1f}{suffix}"


def render_dossier_text(dossier: Mapping[str, Any]) -> str:
    """A plain-text rendering suitable for printing, emailing, or pasting into
    a decision file."""
    lines: list[str] = [
        "COMPLIANCE DOSSIER",
        f"Bidder: {dossier['bidder_id']}    Tender: {dossier['tender_id']}",
        "",
        "METRICS",
    ]
    m = dossier["metrics"]
    lines.append(f"  Compliance score:               {_fmt_metric(m['compliance_score'])}")
    lines.append(f"  Verification coverage:          {_fmt_metric(m['verification_coverage'], '%')}")
    lines.append(f"  Verification coverage (mand.):  {_fmt_metric(m['verification_coverage_mandatory'], '%')}")
    lines.append(f"  Evidence confidence:            {_fmt_metric(m['evidence_confidence'], '%')}")
    lines.append("")

    r = dossier["risk"]
    lines.append("RISK")
    lines.append(f"  Level: {r['level']}")
    lines.append(f"  Triggers: {', '.join(r['triggers']) if r['triggers'] else 'none'}")
    lines.append("")

    lines.append("COLLUSION")
    c = dossier["collusion"]
    if c is None:
        lines.append("  No collusion cluster.")
    else:
        lines.append(f"  Flagged: {c['flagged']}. Cluster {c['cluster_id']}. "
                      f"Members: {', '.join(c['members'])}.")
    lines.append("")

    lines.append("QUALIFICATION")
    wq = dossier["would_qualify"]
    if wq is None:
        note = dossier.get("autopsy_note") or ""
        lines.append(f"  Not yet evaluated. {note}".rstrip())
    else:
        lines.append(f"  Would qualify: {'YES' if wq else 'NO'}")
    lines.append("")

    lines.append("VERDICTS")
    if not dossier["verdicts"]:
        lines.append("  No requirements evaluated yet.")
    else:
        for v in dossier["verdicts"]:
            override = f" (overridden by {v['overridden_by']})" if v.get("overridden_by") else ""
            lines.append(f"  {v['requirement_id']}: {v['verdict_effective']} -- "
                          f"{v['reason_effective']}{override}")
    lines.append("")

    lines.append("BLOCKING REQUIREMENTS")
    if not dossier["blocking_requirements"]:
        lines.append("  None.")
    else:
        for b in dossier["blocking_requirements"]:
            lines.append(f"  [{b['classification']}] {b['requirement_id']}: {b['text']} "
                          f"-- {b['reason_code']}")
    lines.append("")

    lines.append("COUNTERFACTUAL")
    cf = dossier["counterfactual"]
    if cf is None:
        lines.append("  No curable path to qualification identified.")
    else:
        outcome = "would qualify" if cf["would_qualify_if_cured"] else "would still not qualify"
        lines.append(f"  Curing {', '.join(cf['curable_requirement_ids'])}: {outcome}.")
        if cf["still_blocking_after_cure"]:
            lines.append(f"  Still blocking after cure: {', '.join(cf['still_blocking_after_cure'])}")
    lines.append("")

    lines.append("REPAIR ACTIONS -- BIDDER")
    if not dossier["repair_actions_by_bidder"]:
        lines.append("  None.")
    else:
        for a in dossier["repair_actions_by_bidder"]:
            lines.append(f"  {a['requirement_id']}: {a['action']}")
    lines.append("")

    lines.append("REPAIR ACTIONS -- SYSTEM")
    if not dossier["repair_actions_by_system"]:
        lines.append("  None.")
    else:
        for a in dossier["repair_actions_by_system"]:
            lines.append(f"  {a['requirement_id']}: {a['action']}")

    return "\n".join(lines)
