"""Compliance Repair: the forward-looking inverse of Bid Autopsy.

satyapramana.md section 11: "a prioritised, actionable remediation plan. Not
'obtain the required certificate,' but [specific field, specific authority,
specific action]." Deterministic in *what* is required; only the phrasing
would ever be LLM-drafted, and nothing here drafts with a model -- these are
plain templates over reason codes and evidence paths, the same class of thing
as the adapter failure-code mapping in services/core/satyapramana/verdicts.py.

No deadline appears in any action. This system has no Tender Management module
(satyapramana.md section 9, "declined infrastructure cost") and does not track
a bid-submission deadline anywhere queryable after the fact -- inventing one
here would be exactly the fabrication the whole project refuses.
"""
from __future__ import annotations

from typing import Any, Mapping

from satyapramana.rulepack import derived_bindings
from satyapramana.verdicts import Reason

from ..adapters import Registry
from .bid_autopsy import autopsy

#: (actionable_by, message template). {paths} and {authority} are filled from
#: the requirement's derived evidence paths and the registry -- never guessed.
_TEMPLATES: dict[Reason, tuple[str, str]] = {
    Reason.MANDATORY_DOCUMENT_ABSENT: ("BIDDER", "Upload a document providing {paths}."),
    Reason.EXTRACTION_FAILED: ("BIDDER", "The uploaded document could not be read for {paths}; upload a clearer scan or a text-layer PDF."),
    Reason.SELF_DECLARED_CEILING: ("BIDDER", "{paths} currently rests solely on self-declaration; provide it from an authority-verifiable (Tier A) source to lift the ceiling."),
    Reason.CORROBORATION_INCOMPLETE: ("BIDDER", "Provide an additional corroborating source for {paths}."),
    Reason.AUTHORITY_NOT_FOUND: ("BIDDER", "{authority} has no record matching the submitted identifier for {paths}; confirm the identifier and resubmit."),
    Reason.AUTHORITY_AMBIGUOUS: ("BIDDER", "{authority}'s response for {paths} was ambiguous; provide a more specific identifier."),
    Reason.ENTITY_UNRESOLVED: ("BIDDER", "Documents supporting {paths} do not resolve to the same legal entity; submit documents whose identifiers cross-reference correctly."),
    Reason.STALE_VERIFICATION: ("SYSTEM", "The verification for {paths} has gone stale; re-run verification."),
    Reason.AUTHORITY_UNAVAILABLE: ("SYSTEM", "{authority} was unreachable while verifying {paths}; retry verification."),
    Reason.AUTHORITY_RATE_LIMITED: ("SYSTEM", "{authority} rate-limited verification of {paths}; retry after the limit clears."),
    Reason.AUTHORITY_MALFORMED: ("SYSTEM", "The request to {authority} for {paths} could not be completed; this is a platform-side gap, not a bidder action."),
    Reason.AUTHORITY_UNAUTHORIZED: ("SYSTEM", "{authority} verification for {paths} is not yet configured (awaiting credentials)."),
    Reason.NO_ADAPTER_FOR_FIELD: ("SYSTEM", "No verification capability exists yet for {paths}."),
    Reason.AS_OF_UNSUPPORTED: ("SYSTEM", "{authority} does not support the historical (as-of) query needed for {paths}."),
    Reason.SUBREQUIREMENT_UNREACHABLE: ("SYSTEM", "The sub-requirements behind {paths} could not all be reached; see the individual leaves."),
    Reason.SUBREQUIREMENTS_UNVERIFIED: ("SYSTEM", "The sub-requirements behind {paths} remain unverified; see the individual leaves."),
}


def _authority_for(paths: set[str], registry: Registry) -> str | None:
    for path in sorted(paths):
        found = registry.for_path(path)
        if found:
            return found[0].manifest.authority or found[1].capability_id
    return None


def repair_plan(pack: Mapping[str, Any], verdict_rows: list[Mapping[str, Any]],
                registry: Registry) -> dict[str, Any]:
    """One action per CURABLE blocking leaf. FATAL leaves get no action here --
    satyapramana.md's whole point about Tier C evidence and positive
    contradiction is that some findings are not fixed by paperwork; those stay
    visible in the autopsy, not papered over with an instruction that would not
    actually change anything."""
    report = autopsy(pack, verdict_rows)
    if report["would_qualify"] is None:
        return {"actions": [], "note": report["note"]}

    index = {r["id"]: r for r in pack["requirements"]}
    actions = []
    for row in report["blocking_requirements"]:
        if row["classification"] != "CURABLE":
            continue
        req = index[row["requirement_id"]]
        paths = derived_bindings(req)
        reason = Reason(row["reason_code"])
        actionable_by, template = _TEMPLATES.get(
            reason, ("SYSTEM", "This gap ({reason}) has no repair template yet for {paths}."))
        authority = _authority_for(paths, registry)
        actions.append({
            "requirement_id": row["requirement_id"],
            "text": row["text"],
            "reason_code": row["reason_code"],
            "evidence_paths": sorted(paths),
            "authority": authority,
            "actionable_by": actionable_by,
            "action": template.format(
                paths=", ".join(sorted(paths)) or "this requirement",
                authority=authority or "the relevant authority",
                reason=reason.value,
            ),
        })

    # Bidder-actionable first -- those are the ones a bid can actually still be
    # saved by; system-side gaps are visible but nobody submitting a bid can
    # act on them.
    actions.sort(key=lambda a: (a["actionable_by"] != "BIDDER", a["requirement_id"]))
    return {"actions": actions, "note": None}
