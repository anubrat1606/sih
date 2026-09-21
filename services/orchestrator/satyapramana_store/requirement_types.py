"""The requirement-type catalog for the admin tender builder.

A named "requirement type" (GST, minimum turnover, OEM authorization, ...) is
UX sugar over the rule pack's real predicate language (schemas/rule_pack.schema.json)
-- it never introduces a second requirement representation. Every entry here
either resolves to a real, currently-producible evidence path (so the guided
builder can pre-fill a working LEAF predicate), or it honestly says it does
not, with the reason.

This module computes that "does a real evidence path exist for this type"
answer from the live registry and the live deterministic-extraction field
list -- the exact same two sources rule pack validation rule 8 checks a
submitted pack against (rulepacks.py::_registry_as_dict). It never hardcodes
a second, possibly-drifting copy of that answer: if a new capability is
registered tomorrow, this catalog's `evidence_backed` flags update with it,
with no edit needed here.

Nothing here fabricates an evidence path. A type with no producing capability
or extraction field stays honestly `evidence_backed: False` -- the frontend
uses that to warn the officer before they submit, and rule 8 would refuse the
resulting pack at validate/adopt time regardless, exactly as it does today
for any other unproducible path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .adapters import Registry
from .extract.ingest import FIELD_PATHS


@dataclass(frozen=True)
class RequirementType:
    #: Stable identifier, used as the value in the frontend's type dropdown.
    id: str
    label: str
    #: Evidence paths this type would naturally check, in preference order.
    #: Not every path need be currently producible -- see `evidence_backed`.
    candidate_fields: tuple[str, ...]
    #: Suggested predicate operators for this type's LEAF, in the vocabulary
    #: schemas/rule_pack.schema.json#/definitions/predicate already defines
    #: (never a new op invented here).
    suggested_ops: tuple[str, ...]
    #: Free text shown to the officer explaining what this type is for and,
    #: when unbacked, exactly what is missing before it can be evaluated.
    note: str


#: The fifteen types the admin builder brief names, at minimum. Order is the
#: order they should appear in the picker.
_CATALOG: tuple[RequirementType, ...] = (
    RequirementType("GST", "GST registration",
        ("bidder.gst.gstin", "bidder.gst.status", "bidder.gst.date_of_expiry"),
        ("exists", "eq", "active_on", "date_after"),
        "Backed by deterministic GSTIN extraction always; bidder.gst.status also "
        "needs the GST_STATUS capability's credentials configured to resolve to "
        "anything but UNKNOWN."),
    RequirementType("PAN", "PAN",
        ("bidder.pan.pan_number", "bidder.pan.status", "bidder.pan.holder_name"),
        ("exists", "eq"),
        "Backed by deterministic PAN extraction always; bidder.pan.status also "
        "needs the PAN_STATUS capability's credentials configured."),
    RequirementType("CIN", "Company Identification Number (CIN)",
        ("bidder.entity.cin", "bidder.entity.status"),
        ("exists", "eq"),
        "Backed by deterministic CIN extraction always; bidder.entity.status "
        "also needs the CIN_STATUS capability's credentials configured."),
    RequirementType("UDYAM", "Udyam / MSME registration",
        ("bidder.udyam.udyam_number", "bidder.udyam.status"),
        ("exists", "eq"),
        "Backed by deterministic Udyam-number extraction always; "
        "bidder.udyam.status also needs the UDYAM_STATUS capability's "
        "credentials configured."),
    RequirementType("DOCUMENT_REQUIRED", "Document required (generic)",
        (),
        ("exists",),
        "Only the four identity documents above (GST/PAN/CIN/Udyam) have a "
        "real extraction path today. A generic 'require this named document' "
        "check for any other document type has no evidence path yet -- this "
        "requirement will be saved with review_required and cannot be "
        "adopted until one is registered."),
    RequirementType("MIN_TURNOVER", "Minimum annual turnover",
        ("bidder.financials.turnover", "bidder.financials.turnover_financial_year"),
        ("gte",),
        "Extracted from a submitted financial statement's own table (turnover "
        "for its most recent reported year, normalized to INR paise using the "
        "statement's own stated unit). There is no authority to verify a "
        "claimed turnover against, so a mandatory requirement built on this "
        "stays capped at PARTIAL (self-declared ceiling) -- extracted, not "
        "yet independently verifiable, never a path to a clean PASS."),
    RequirementType("NET_WORTH", "Minimum net worth",
        ("bidder.financials.net_worth", "bidder.financials.net_worth_financial_year"),
        ("gte",),
        "Extracted from a submitted financial statement's own table, the "
        "same way as minimum turnover -- and capped at PARTIAL for the same "
        "reason: self-declared, with no authority to verify it against."),
    RequirementType("ITR", "Income Tax Return filing",
        (), ("exists", "gte"),
        "No ITR extraction or capability exists yet. Saved for review; not "
        "adoptable until a real evidence path is built."),
    RequirementType("EXPERIENCE", "Years of experience",
        (), ("gte",),
        "No experience-certificate extraction or capability exists yet. "
        "Saved for review; not adoptable until a real evidence path is built."),
    RequirementType("SIMILAR_WORK", "Similar work / past performance",
        (), ("exists", "gte"),
        "No work-completion-certificate extraction or capability exists yet. "
        "Saved for review; not adoptable until a real evidence path is built."),
    RequirementType("OEM_AUTHORIZATION", "OEM authorization",
        (), ("exists",),
        "No OEM-authorization-letter extraction or capability exists yet. "
        "Saved for review; not adoptable until a real evidence path is built."),
    RequirementType("CERTIFICATION", "Certification (ISO, BIS, etc.)",
        (), ("exists",),
        "No certificate extraction or capability exists yet. Saved for "
        "review; not adoptable until a real evidence path is built."),
    RequirementType("EPFO_ESIC", "EPFO / ESIC registration",
        (), ("exists",),
        "Confirmed cut from scope (docs/STATUS.md): no lawful programmatic "
        "source exists anywhere for EPFO/ESIC. Saved for review; this is a "
        "known, permanent gap, not an oversight."),
    RequirementType("DECLARATION", "Self-declaration / undertaking",
        ("bidder.declarations.{requirement_id}",), ("exists",),
        "Captured directly as a real, attributed event when a bidder (or "
        "an officer on their behalf) formally records the attestation "
        "this requirement asks for -- never extracted from a document, "
        "because an undertaking IS the self-declaration; there is nothing "
        "to independently verify it against, by definition, not by "
        "current limitation. The evidence path names this requirement's "
        "own id, normalized to fit a field name (lowercased, \"R4.1\" "
        "becomes \"req_r4_1\") -- type your requirement's ID first, then "
        "pick this type, and the real field fills in automatically."),
    RequirementType("TECHNICAL", "Technical requirement (free-form)",
        (), (),
        "Open-ended by nature. If it reduces to one of the typed checks "
        "above, pick that type instead; otherwise this has no automatic "
        "evidence path and is saved for review."),
)


def _producible_paths(registry: Registry) -> set[str]:
    """The exact same union rule 8 checks a submitted pack against:
    every path a registered adapter capability or the deterministic
    extraction stage can produce -- see rulepacks.py::_registry_as_dict,
    kept in sync by reading the same two sources rather than copying them."""
    paths = set(FIELD_PATHS.values())
    for adapter in registry.adapters:
        for capability in adapter.manifest.capabilities:
            paths.update(capability.provides)
    return paths


def requirement_type_catalog(registry: Registry) -> list[dict[str, Any]]:
    """The catalog, with each type's `evidence_backed` flag computed live
    against the registry passed in -- never a stale, hand-maintained bool."""
    producible = _producible_paths(registry)
    out = []
    for rt in _CATALOG:
        if rt.id == "DECLARATION":
            # This type's one field is a template (bidder.declarations.
            # {requirement_id}), never a literal member of `producible` --
            # it's parameterized by a requirement id that only exists once
            # a pack is being drafted (rulepacks.py's _registry_as_dict
            # computes the real per-pack paths at validation time). Always
            # backed here: the capture mechanism itself (a real recorded
            # human attestation) exists independent of what's registered
            # in the adapter registry.
            backed_fields = list(rt.candidate_fields)
        else:
            backed_fields = [f for f in rt.candidate_fields if f in producible]
        out.append({
            "id": rt.id,
            "label": rt.label,
            "evidence_backed": bool(backed_fields),
            "candidate_fields": list(rt.candidate_fields),
            "backed_fields": backed_fields,
            "suggested_ops": list(rt.suggested_ops),
            "note": rt.note,
        })
    return out


__all__ = ["RequirementType", "requirement_type_catalog"]
