"""Rule pack validation, including against the real schema and registry files."""
import copy
import json
from pathlib import Path

import pytest

from satyapramana.rulepack import (
    content_hash, derived_bindings, rule_pack_version, validate,
)

SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"
SCHEMA = json.loads((SCHEMAS / "rule_pack.schema.json").read_text())
REGISTRY = json.loads((SCHEMAS / "capability_registry.json").read_text())

BASE = {
    "rule_pack_id": "cpcl.tender.2026.gem-xxxxxx",
    "semver": "1.0.0",
    "tender_reference": {
        "tender_id": "GEM-XXXXXX",
        "source_document_sha256": "b" * 64,
        "issuing_authority": "Chennai Petroleum Corporation Limited",
    },
    "constants": {
        "partial_credit": 0.5, "w_mandatory": 1.0, "w_desirable": 0.3,
        "recency_floor": 0.5, "corroboration_step": 0.1,
        "coverage_floor_high": 50, "coverage_floor_medium": 80,
        "confidence_floor": 70, "freshness_days": {"GST_STATUS": 30},
    },
    "requirements": [
        {"id": "R4", "text": "GST and PAN.", "source": {"page": 14},
         "obligation": "mandatory", "operator": "ALL_OF",
         "children": ["R4.1", "R4.2"]},
        {"id": "R4.1", "text": "Valid GST registration.", "source": {"page": 14},
         "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "active_on",
                       "subject": {"field": "bidder.gst.status_history"},
                       "at": {"context": "bid_submission_date"}}},
        {"id": "R4.2", "text": "Valid PAN.", "source": {"page": 14},
         "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "eq", "left": {"field": "bidder.pan.status"},
                       "right": {"literal": "VALID"}}},
    ],
}


def pack(**over):
    p = copy.deepcopy(BASE)
    p.update(over)
    p["content_hash"] = content_hash(p)
    return p


def mutate(fn):
    p = copy.deepcopy(BASE)
    fn(p)
    p["content_hash"] = content_hash(p)
    return p


def rules(violations):
    return sorted({v.rule for v in violations})


def test_a_well_formed_pack_validates_against_the_real_schema_and_registry():
    assert validate(pack(), REGISTRY, SCHEMA) == []


def test_content_hash_is_stable_and_excludes_itself():
    p = pack()
    assert content_hash(p) == p["content_hash"]
    reordered = {k: p[k] for k in reversed(list(p))}
    assert content_hash(reordered) == content_hash(p)


def test_version_carries_id_semver_and_hash():
    v = rule_pack_version(pack())
    assert v.startswith("cpcl.tender.2026.gem-xxxxxx@1.0.0+") and len(v.split("+")[1]) == 12


def test_editing_in_place_is_detected():
    p = pack()
    p["requirements"][2]["predicate"]["right"]["literal"] = "ANYTHING"
    assert 13 in rules(validate(p, REGISTRY, SCHEMA))


# --- rule 8: the one that stops permanently-unknowable requirements ----------

def test_an_unproducible_evidence_path_is_rejected():
    p = mutate(lambda p: p["requirements"][2]["predicate"]["left"].update(
        {"field": "bidder.astrology.sign"}))
    v = validate(p, REGISTRY, SCHEMA)
    assert 8 in rules(v)
    assert any("could only ever be UNKNOWN" in x.message for x in v)


def test_registry_backed_paths_are_accepted():
    assert 8 not in rules(validate(pack(), REGISTRY, SCHEMA))


def test_bindings_are_derived_from_the_predicate_not_declared():
    req = BASE["requirements"][2]
    assert derived_bindings(req) == {"bidder.pan.status"}


def test_aggregate_bindings_are_derived_too():
    req = {"predicate": {"op": "gte",
           "left": {"aggregate": "mean", "over": "bidder.financials",
                    "select": "annual_turnover_minor"},
           "right": {"literal": 1}}}
    assert derived_bindings(req) == {"bidder.financials.annual_turnover_minor"}


# --- rule 10: no wall clock ---------------------------------------------------

def test_reading_the_system_clock_is_rejected():
    p = mutate(lambda p: p["requirements"][2].update({"predicate": {
        "op": "date_before", "left": {"field": "bidder.pan.status"},
        "right": {"field": "today"}}}))
    assert 10 in rules(validate(p, REGISTRY, SCHEMA))


# --- the remaining structural rules ------------------------------------------

def test_duplicate_ids_are_rejected():
    p = mutate(lambda p: p["requirements"].append(copy.deepcopy(p["requirements"][1])))
    assert 2 in rules(validate(p, REGISTRY, SCHEMA))


def test_unresolvable_child_reference_is_rejected():
    p = mutate(lambda p: p["requirements"][0]["children"].append("R9.9"))
    assert 2 in rules(validate(p, REGISTRY, SCHEMA))


def test_a_cycle_is_rejected():
    p = mutate(lambda p: p["requirements"][1].update(
        {"operator": "ALL_OF", "children": ["R4"], "predicate": None}))
    p["requirements"][1].pop("predicate")
    v = validate(p, REGISTRY, SCHEMA)
    assert 3 in rules(v)
    assert any("cycle" in x.message for x in v)


def test_k_out_of_range_is_rejected():
    p = mutate(lambda p: p["requirements"][0].update({"operator": "K_OF_N", "k": 7}))
    assert 4 in rules(validate(p, REGISTRY, SCHEMA))


def test_not_with_two_children_is_rejected():
    p = mutate(lambda p: p["requirements"][0].update({"operator": "NOT"}))
    assert 6 in rules(validate(p, REGISTRY, SCHEMA))


def test_unknown_operator_is_rejected():
    p = mutate(lambda p: p["requirements"][2]["predicate"].update({"op": "vibes"}))
    assert 7 in rules(validate(p, REGISTRY, SCHEMA))


def test_float_currency_is_rejected():
    p = mutate(lambda p: p["requirements"][2]["predicate"]["right"].update(
        {"literal": 3.0e10}))
    assert 9 in rules(validate(p, REGISTRY, SCHEMA))


def test_unreviewed_uncertainty_blocks_adoption():
    """A pack containing an unreviewed uncertain requirement cannot be adopted.
    This is validated, not merely advised."""
    p = mutate(lambda p: p["requirements"][2].update(
        {"review_required": True, "review_note": "clause 7.2 is ambiguous"}))
    v = validate(p, REGISTRY, SCHEMA)
    assert 11 in rules(v)
    assert any("clause 7.2 is ambiguous" in x.message for x in v)


def test_missing_source_page_is_rejected():
    p = mutate(lambda p: p["requirements"][2].update({"source": {}}))
    assert 12 in rules(validate(p, REGISTRY, SCHEMA))


def test_validation_never_repairs_a_pack():
    """A malformed pack is rejected, never coerced into something evaluable."""
    p = mutate(lambda p: p["requirements"][2]["predicate"].update({"op": "vibes"}))
    before = copy.deepcopy(p)
    validate(p, REGISTRY, SCHEMA)
    assert p == before
