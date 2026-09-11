"""Bid Autopsy and Compliance Repair. Pure-function tests first (no database),
then a couple of tests through the real API to confirm the wiring."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from satyapramana.verdicts import Reason
from satyapramana_store.adapters import Registry
from satyapramana_store.app import app, db
from satyapramana_store.reporting.bid_autopsy import autopsy, classify
from satyapramana_store.reporting.compliance_repair import repair_plan
from satyapramana_store.reporting.dossier import build_dossier, render_dossier_text

_SOURCE = {"page": 1, "region": [0, 0, 100, 20]}

PACK = {
    "requirements": [
        {"id": "ROOT", "text": "Bidder is compliant", "source": _SOURCE,
         "obligation": "mandatory", "operator": "ALL_OF", "children": ["L1", "L2"]},
        {"id": "L1", "text": "GST is active", "source": _SOURCE,
         "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "eq", "left": {"field": "bidder.gst.status"},
                       "right": {"literal": "ACTIVE"}}},
        {"id": "L2", "text": "PAN is valid", "source": _SOURCE,
         "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "eq", "left": {"field": "bidder.pan.status"},
                       "right": {"literal": "VALID"}}},
    ],
}


def row(rid, verdict, reason):
    return {"requirement_id": rid, "verdict_system": verdict, "reason_system": reason,
            "verdict_effective": verdict, "reason_effective": reason,
            "overridden_by": None, "override_justification": None,
            "rule_pack_version": "test@1.0.0+abc"}


# --- classify -------------------------------------------------------------

def test_positive_contradiction_is_fatal():
    assert classify(Reason.AUTHORITY_CONTRADICTED) == "FATAL"
    assert classify(Reason.DOCUMENT_EXPIRED) == "FATAL"


def test_absence_of_evidence_is_curable():
    assert classify(Reason.AUTHORITY_UNAVAILABLE) == "CURABLE"
    assert classify(Reason.MANDATORY_DOCUMENT_ABSENT) == "CURABLE"
    assert classify(Reason.AUTHORITY_UNAUTHORIZED) == "CURABLE"


def test_a_pass_reason_is_unclassified_not_fatal_or_curable():
    """PASS reasons never appear on a blocking leaf in practice, but classify()
    should not silently mislabel one if it ever did."""
    assert classify(Reason.AUTHORITY_CONFIRMED) == "UNCLASSIFIED"


# --- autopsy: the basics ----------------------------------------------------

def test_no_verdicts_yet_is_honestly_unknown_not_vacuously_true():
    report = autopsy(PACK, [])
    assert report["would_qualify"] is None
    assert report["blocking_requirements"] == []
    assert report["counterfactual"] is None
    assert "not yet evaluated" in report["note"]


def test_all_pass_qualifies_with_nothing_blocking():
    rows = [row("ROOT", "PASS", "THRESHOLD_MET"),
            row("L1", "PASS", "AUTHORITY_CONFIRMED"),
            row("L2", "PASS", "AUTHORITY_CONFIRMED")]
    report = autopsy(PACK, rows)
    assert report["would_qualify"] is True
    assert report["blocking_requirements"] == []
    assert report["counterfactual"] is None


def test_a_fatal_leaf_blocks_and_is_never_offered_a_cure():
    rows = [row("ROOT", "FAIL", "SUBREQUIREMENT_UNREACHABLE"),
            row("L1", "FAIL", "AUTHORITY_CONTRADICTED"),
            row("L2", "PASS", "AUTHORITY_CONFIRMED")]
    report = autopsy(PACK, rows)
    assert report["would_qualify"] is False
    ids = {b["requirement_id"] for b in report["blocking_requirements"]}
    assert ids == {"L1"}
    assert report["blocking_requirements"][0]["classification"] == "FATAL"
    # No curable leaves -> nothing to build a counterfactual from.
    assert report["counterfactual"] is None


def test_fatal_is_ranked_before_curable():
    rows = [row("ROOT", "UNKNOWN", "SUBREQUIREMENTS_UNVERIFIED"),
            row("L1", "FAIL", "AUTHORITY_CONTRADICTED"),
            row("L2", "UNKNOWN", "AUTHORITY_UNAVAILABLE")]
    report = autopsy(PACK, rows)
    assert [b["requirement_id"] for b in report["blocking_requirements"]] == ["L1", "L2"]


# --- autopsy: the counterfactual --------------------------------------------

def test_the_charter_example_curing_everything_flips_the_verdict():
    """satyapramana.md section 11: 'had these three items been present, this
    bid would have moved from FAIL to PASS.' Both leaves here are curable."""
    rows = [row("ROOT", "UNKNOWN", "SUBREQUIREMENTS_UNVERIFIED"),
            row("L1", "UNKNOWN", "AUTHORITY_UNAVAILABLE"),
            row("L2", "UNKNOWN", "AUTHORITY_UNAUTHORIZED")]
    report = autopsy(PACK, rows)
    cf = report["counterfactual"]
    assert set(cf["curable_requirement_ids"]) == {"L1", "L2"}
    assert cf["would_qualify_if_cured"] is True
    assert cf["still_blocking_after_cure"] == []


def test_curing_only_the_curable_leaf_is_not_enough_when_another_is_fatal():
    rows = [row("ROOT", "FAIL", "SUBREQUIREMENT_UNREACHABLE"),
            row("L1", "FAIL", "AUTHORITY_CONTRADICTED"),
            row("L2", "UNKNOWN", "AUTHORITY_UNAVAILABLE")]
    report = autopsy(PACK, rows)
    cf = report["counterfactual"]
    assert cf["curable_requirement_ids"] == ["L2"]
    assert cf["would_qualify_if_cured"] is False
    # Reports the still-unsatisfied root, not every leaf beneath it -- L1
    # stays FAIL, so ROOT (ALL_OF) stays FAIL even after L2 is cured.
    assert cf["still_blocking_after_cure"] == ["ROOT"]


def test_an_officer_override_is_read_as_the_effective_verdict():
    rows = [{"requirement_id": "ROOT", "verdict_system": "FAIL", "reason_system": "SUBREQUIREMENT_UNREACHABLE",
             "verdict_effective": "PASS", "reason_effective": "AUTHORITY_CONFIRMED",
             "overridden_by": "officer_1", "override_justification": "manual review",
             "rule_pack_version": "test@1.0.0+abc"},
            row("L1", "FAIL", "AUTHORITY_CONTRADICTED"),
            row("L2", "PASS", "AUTHORITY_CONFIRMED")]
    report = autopsy(PACK, rows)
    # ROOT itself isn't a LEAF so it never appears in blocking_requirements
    # (only leaves do) -- but would_qualify reads every mandatory row's
    # effective verdict, ROOT included, so the override is what decides it.
    assert report["would_qualify"] is True


# --- compliance repair -------------------------------------------------------

def test_fatal_leaves_get_no_repair_action():
    rows = [row("ROOT", "FAIL", "SUBREQUIREMENT_UNREACHABLE"),
            row("L1", "FAIL", "AUTHORITY_CONTRADICTED"),
            row("L2", "PASS", "AUTHORITY_CONFIRMED")]
    plan = repair_plan(PACK, rows, Registry())
    assert plan["actions"] == []


def test_curable_leaves_get_a_bidder_actionable_repair():
    rows = [row("ROOT", "FAIL", "SUBREQUIREMENT_UNREACHABLE"),
            row("L1", "FAIL", "MANDATORY_DOCUMENT_ABSENT"),
            row("L2", "PASS", "AUTHORITY_CONFIRMED")]
    plan = repair_plan(PACK, rows, Registry())
    assert len(plan["actions"]) == 1
    action = plan["actions"][0]
    assert action["requirement_id"] == "L1"
    assert action["actionable_by"] == "BIDDER"
    assert "bidder.gst.status" in action["action"]


def test_a_system_side_gap_is_never_told_to_the_bidder_as_theirs():
    rows = [row("ROOT", "UNKNOWN", "SUBREQUIREMENTS_UNVERIFIED"),
            row("L1", "UNKNOWN", "AUTHORITY_UNAUTHORIZED"),
            row("L2", "PASS", "AUTHORITY_CONFIRMED")]
    plan = repair_plan(PACK, rows, Registry())
    assert plan["actions"][0]["actionable_by"] == "SYSTEM"
    assert "awaiting credentials" in plan["actions"][0]["action"]


def test_no_deadline_is_ever_fabricated_into_an_action():
    """This system tracks no bid-submission deadline anywhere queryable after
    the fact -- inventing one would be exactly the fabrication the project
    refuses everywhere else."""
    rows = [row("ROOT", "FAIL", "SUBREQUIREMENT_UNREACHABLE"),
            row("L1", "FAIL", "MANDATORY_DOCUMENT_ABSENT"),
            row("L2", "PASS", "AUTHORITY_CONFIRMED")]
    plan = repair_plan(PACK, rows, Registry())
    for action in plan["actions"]:
        assert "deadline" not in action["action"].lower()
        assert "2026" not in action["action"]


def test_unevaluated_bidder_yields_no_actions_with_the_same_honest_note():
    plan = repair_plan(PACK, [], Registry())
    assert plan == {"actions": [], "note": "not yet evaluated -- no rule pack has been run against this bidder"}


# --- through the real API ----------------------------------------------------

@pytest.fixture()
def client(conn):
    app.dependency_overrides[db] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_autopsy_endpoint_refuses_without_an_adopted_pack(client):
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    r = client.get("/bidders/A/autopsy", params={"tender_id": "T1"})
    assert r.status_code == 409


def test_autopsy_and_repair_plan_endpoints_after_a_real_evaluation(client):
    client.post("/tenders/T1/rule-pack", json={"officer_id": "officer_1", "pack": {
        "rule_pack_id": "test.autopsy", "semver": "1.0.0",
        "tender_reference": {"tender_id": "T1", "source_document_sha256": "a" * 64,
                             "issuing_authority": "Test Authority"},
        "constants": {"partial_credit": 0.5, "w_mandatory": 1.0, "w_desirable": 0.3,
                     "recency_floor": 0.5, "corroboration_step": 0.1,
                     "coverage_floor_high": 50, "coverage_floor_medium": 80,
                     "confidence_floor": 70, "freshness_days": {"GST_STATUS": 30}},
        "requirements": PACK["requirements"],
    }})
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"},
               json={"bid_submission_date": "2026-09-22"})

    autopsy_body = client.get("/bidders/A/autopsy", params={"tender_id": "T1"}).json()
    # No live capability is configured in this test environment -- every leaf
    # is UNKNOWN/AUTHORITY_UNAUTHORIZED, all curable.
    assert autopsy_body["would_qualify"] is False
    assert {b["requirement_id"] for b in autopsy_body["blocking_requirements"]} == {"L1", "L2"}
    assert all(b["classification"] == "CURABLE" for b in autopsy_body["blocking_requirements"])
    assert autopsy_body["counterfactual"]["would_qualify_if_cured"] is True

    repair_body = client.get("/bidders/A/repair-plan", params={"tender_id": "T1"}).json()
    assert {a["requirement_id"] for a in repair_body["actions"]} == {"L1", "L2"}
    assert all(a["actionable_by"] == "SYSTEM" for a in repair_body["actions"])


# --- Compliance Dossier -------------------------------------------------------
# Pure-function tests only, no database: build_dossier() and render_dossier_text()
# take plain dicts shaped exactly like GET /bidders/{id}, GET /bidders/{id}/autopsy,
# and GET /bidders/{id}/repair-plan already return, and do no I/O of their own.

BIDDER_QUALIFYING = {
    "bidder_id": "A", "tender_id": "T1",
    "verdicts": [
        {"requirement_id": "ROOT", "verdict_system": "PASS", "reason_system": "THRESHOLD_MET",
         "verdict_effective": "PASS", "reason_effective": "THRESHOLD_MET",
         "overridden_by": None, "override_justification": None,
         "rule_pack_version": "test@1.0.0+abc"},
    ],
    "metrics": {"compliance_score": 100.0, "verification_coverage": 100.0,
                "verification_coverage_mandatory": 100.0, "evidence_confidence": 95.0},
    "risk": {"level": "LOW", "triggers": [], "function_version": "risk@1"},
    "collusion": None,
}
AUTOPSY_QUALIFYING = {"would_qualify": True, "blocking_requirements": [],
                       "counterfactual": None, "note": None}
REPAIR_QUALIFYING = {"actions": [], "note": None}

BIDDER_BLOCKED = {
    "bidder_id": "A", "tender_id": "T1",
    "verdicts": [
        row("ROOT", "FAIL", "SUBREQUIREMENT_UNREACHABLE"),
        row("L1", "FAIL", "AUTHORITY_CONTRADICTED"),
        row("L2", "UNKNOWN", "MANDATORY_DOCUMENT_ABSENT"),
    ],
    "metrics": {"compliance_score": 40.0, "verification_coverage": 50.0,
                "verification_coverage_mandatory": 50.0, "evidence_confidence": 60.0},
    "risk": {"level": "HIGH", "triggers": ["collusion_edge"], "function_version": "risk@1"},
    "collusion": {"flagged": True, "cluster_id": "cluster_A_B", "members": ["A", "B"]},
}
AUTOPSY_BLOCKED = {
    "would_qualify": False,
    "blocking_requirements": [
        {"requirement_id": "L1", "text": "GST is active", "verdict": "FAIL",
         "reason_code": "AUTHORITY_CONTRADICTED", "classification": "FATAL", "overridden_by": None},
        {"requirement_id": "L2", "text": "PAN is valid", "verdict": "UNKNOWN",
         "reason_code": "MANDATORY_DOCUMENT_ABSENT", "classification": "CURABLE", "overridden_by": None},
    ],
    "counterfactual": {"curable_requirement_ids": ["L2"], "would_qualify_if_cured": False,
                        "still_blocking_after_cure": ["ROOT"]},
    "note": None,
}
REPAIR_BLOCKED = {
    "actions": [
        {"requirement_id": "L2", "text": "PAN is valid", "reason_code": "MANDATORY_DOCUMENT_ABSENT",
         "evidence_paths": ["bidder.pan.pan_number"], "authority": None,
         "actionable_by": "BIDDER", "action": "Upload a document providing bidder.pan.pan_number."},
    ],
    "note": None,
}

BIDDER_UNEVALUATED = {
    "bidder_id": "A", "tender_id": "T1",
    "verdicts": [],
    "metrics": {"compliance_score": None, "verification_coverage": None,
                "verification_coverage_mandatory": None, "evidence_confidence": None},
    "risk": {"level": "HIGH", "triggers": ["mandatory_unverified"], "function_version": "risk@1"},
    "collusion": None,
}
_UNEVALUATED_NOTE = "not yet evaluated -- no rule pack has been run against this bidder"
AUTOPSY_UNEVALUATED = {"would_qualify": None, "blocking_requirements": [],
                        "counterfactual": None, "note": _UNEVALUATED_NOTE}
REPAIR_UNEVALUATED = {"actions": [], "note": _UNEVALUATED_NOTE}


def test_dossier_for_a_qualifying_bidder_has_no_blocking_requirements():
    d = build_dossier(BIDDER_QUALIFYING, AUTOPSY_QUALIFYING, REPAIR_QUALIFYING)
    assert d["would_qualify"] is True
    assert d["blocking_requirements"] == []
    assert d["repair_actions_by_bidder"] == []
    assert d["repair_actions_by_system"] == []
    assert d["collusion"] is None


def test_dossier_splits_repair_actions_by_who_can_act():
    """A SYSTEM-side gap must never end up in the bidder's list -- the same
    rule compliance_repair.py itself follows."""
    d = build_dossier(BIDDER_BLOCKED, AUTOPSY_BLOCKED, REPAIR_BLOCKED)
    assert [a["requirement_id"] for a in d["repair_actions_by_bidder"]] == ["L2"]
    assert d["repair_actions_by_system"] == []
    assert d["would_qualify"] is False
    assert d["collusion"]["flagged"] is True
    assert d["collusion"]["cluster_id"] == "cluster_A_B"


def test_dossier_never_turns_a_null_metric_or_unknown_qualification_into_a_guess():
    """A bidder never evaluated: would_qualify is None, not False; every metric
    is None, not 0."""
    d = build_dossier(BIDDER_UNEVALUATED, AUTOPSY_UNEVALUATED, REPAIR_UNEVALUATED)
    assert d["would_qualify"] is None
    assert d["metrics"]["compliance_score"] is None
    assert d["metrics"]["verification_coverage"] is None
    assert d["repair_actions_by_bidder"] == []
    assert d["repair_actions_by_system"] == []


def test_dossier_is_identical_when_built_twice_from_the_same_input():
    first = build_dossier(BIDDER_BLOCKED, AUTOPSY_BLOCKED, REPAIR_BLOCKED)
    second = build_dossier(BIDDER_BLOCKED, AUTOPSY_BLOCKED, REPAIR_BLOCKED)
    assert first == second
    assert render_dossier_text(first) == render_dossier_text(second)


def test_render_never_prints_a_fabricated_zero_for_a_null_metric():
    d = build_dossier(BIDDER_UNEVALUATED, AUTOPSY_UNEVALUATED, REPAIR_UNEVALUATED)
    text = render_dossier_text(d)
    assert "not determined" in text
    assert "0.0" not in text
    assert "Not yet evaluated" in text
    assert _UNEVALUATED_NOTE in text


def test_render_shows_the_qualifying_verdict_and_score():
    d = build_dossier(BIDDER_QUALIFYING, AUTOPSY_QUALIFYING, REPAIR_QUALIFYING)
    text = render_dossier_text(d)
    assert "Would qualify: YES" in text
    assert "100.0" in text
    assert "No collusion cluster." in text


def test_render_shows_blocking_requirements_with_their_classification_and_repair_split():
    d = build_dossier(BIDDER_BLOCKED, AUTOPSY_BLOCKED, REPAIR_BLOCKED)
    text = render_dossier_text(d)
    assert "Would qualify: NO" in text
    assert "[FATAL] L1: GST is active -- AUTHORITY_CONTRADICTED" in text
    assert "[CURABLE] L2: PAN is valid -- MANDATORY_DOCUMENT_ABSENT" in text
    assert "REPAIR ACTIONS -- BIDDER" in text
    assert "L2: Upload a document providing bidder.pan.pan_number." in text
    # No system-side gaps here, and the bidder section must never carry one.
    bidder_section = text.split("REPAIR ACTIONS -- BIDDER")[1].split("REPAIR ACTIONS -- SYSTEM")[0]
    assert "SYSTEM" not in bidder_section
    assert "Flagged: True. Cluster cluster_A_B. Members: A, B." in text
