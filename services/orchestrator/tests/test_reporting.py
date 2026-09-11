"""Bid Autopsy and Compliance Repair. Pure-function tests first (no database),
then a couple of tests through the real API to confirm the wiring."""
from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from satyapramana.verdicts import Reason
from satyapramana_store.adapters import Registry
from satyapramana_store.app import app, db
from satyapramana_store.reporting.bid_autopsy import autopsy, classify
from satyapramana_store.reporting.compliance_repair import repair_plan
from satyapramana_store.reporting.dossier import build_dossier, render_dossier_text
from satyapramana_store.reporting.tender_report import tender_report, render_tender_report_text
from satyapramana_store.reporting.csv_export import bidders_to_csv
from satyapramana_store.reporting.blocker_summary import blocker_summary
from satyapramana_store.reporting.evidence_graph import build_evidence_graph

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


def test_dossier_endpoint_composes_the_other_three_real_endpoints(client):
    client.post("/tenders/T1/rule-pack", json={"officer_id": "officer_1", "pack": {
        "rule_pack_id": "test.dossier", "semver": "1.0.0",
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

    body = client.get("/bidders/A/dossier", params={"tender_id": "T1"}).json()
    assert body["bidder_id"] == "A" and body["tender_id"] == "T1"
    assert body["would_qualify"] is False
    assert {b["requirement_id"] for b in body["blocking_requirements"]} == {"L1", "L2"}
    assert all(a["actionable_by"] == "SYSTEM" for a in body["repair_actions_by_system"])
    assert body["repair_actions_by_bidder"] == []

    text = client.get("/bidders/A/dossier", params={"tender_id": "T1", "as_text": "true"}).text
    assert "COMPLIANCE DOSSIER" in text and "A" in text


def test_dossier_endpoint_refuses_without_an_adopted_pack(client):
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    assert client.get("/bidders/A/dossier", params={"tender_id": "T1"}).status_code == 409


# --- EXPLAIN --------------------------------------------------------------
# satyapramana.md 2.2: a narrator, never a judge. No test here makes a real
# call to a provider -- see test_explain.py's own docstring for why.

def test_explain_endpoint_refuses_without_an_adopted_pack(client):
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    assert client.get("/bidders/A/explain", params={"tender_id": "T1"}).status_code == 409


def test_explain_endpoint_is_honestly_unavailable_without_a_configured_provider(client):
    """The test environment has no SATYAPRAMANA_GEMINI_API_KEY -- the same
    honest-degrade shape as every unconfigured verification capability."""
    client.post("/tenders/T1/rule-pack", json={"officer_id": "officer_1", "pack": {
        "rule_pack_id": "test.explain", "semver": "1.0.0",
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

    body = client.get("/bidders/A/explain", params={"tender_id": "T1"}).json()
    assert body["bidder_id"] == "A" and body["tender_id"] == "T1"
    assert body["available"] is False
    assert body["narrative"] is None
    assert "not configured" in body["reason"]
    assert body["model"] is None and body["generated_at"] is None


def test_explain_endpoint_returns_a_narrative_from_a_configured_provider(client, monkeypatch):
    """Swaps in a fake Explainer, structurally identical to GeminiExplainer,
    to prove the endpoint's wiring end-to-end without a real provider call."""
    from datetime import datetime, timezone

    from satyapramana_store import app as app_module
    from satyapramana_store.explain import Narrated

    class _FakeExplainer:
        def narrate(self, dossier_text):
            assert "COMPLIANCE DOSSIER" in dossier_text  # the real dossier, not a stub
            return Narrated(narrative="A fake but real narrative.",
                            model="fake-model", generated_at=datetime.now(timezone.utc))

    monkeypatch.setattr(app_module, "EXPLAINER", _FakeExplainer())

    client.post("/tenders/T1/rule-pack", json={"officer_id": "officer_1", "pack": {
        "rule_pack_id": "test.explain2", "semver": "1.0.0",
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

    body = client.get("/bidders/A/explain", params={"tender_id": "T1"}).json()
    assert body["available"] is True
    assert body["narrative"] == "A fake but real narrative."
    assert body["model"] == "fake-model"
    assert body["reason"] is None
    assert body["generated_at"] is not None


def test_tender_report_endpoint_aggregates_the_real_bidder_list(client):
    client.post("/tenders/T1/bidders", json={"bidder_id": "A", "phone": "1111111111"})
    client.post("/tenders/T1/bidders", json={"bidder_id": "B", "phone": "1111111111"})
    client.post("/tenders/T1/bidders", json={"bidder_id": "C"})

    body = client.get("/tenders/T1/report").json()
    assert body["tender_id"] == "T1" and body["bidder_count"] == 3
    assert body["collusion"]["cluster_count"] == 1
    assert body["collusion"]["flagged_bidder_count"] == 2
    assert set(body["collusion"]["bidder_clusters"]) == {"A", "B"}

    text = client.get("/tenders/T1/report", params={"as_text": "true"}).text
    assert "TENDER COMPLIANCE REPORT" in text and "Bidders: 3" in text


def test_tender_report_csv_endpoint_round_trips_the_real_bidder_list(client):
    client.post("/tenders/T1/bidders", json={"bidder_id": "A", "phone": "1111111111"})
    client.post("/tenders/T1/bidders", json={"bidder_id": "B", "phone": "1111111111"})

    resp = client.get("/tenders/T1/report/csv")
    assert resp.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert {r["bidder_id"] for r in rows} == {"A", "B"}
    # No evaluation has run -- every metric is honestly unset, not a
    # fabricated 0 or the string "None".
    assert rows[0]["compliance_score"] == ""
    assert rows[0]["collusion_flagged"] == "True"
    assert rows[0]["collusion_cluster_id"] != ""


def test_tender_blockers_endpoint_refuses_without_an_adopted_pack(client):
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    assert client.get("/tenders/T1/blockers").status_code == 409


def test_tender_blockers_endpoint_aggregates_real_autopsies(client):
    client.post("/tenders/T1/rule-pack", json={"officer_id": "officer_1", "pack": {
        "rule_pack_id": "test.blockers", "semver": "1.0.0",
        "tender_reference": {"tender_id": "T1", "source_document_sha256": "a" * 64,
                             "issuing_authority": "Test Authority"},
        "constants": {"partial_credit": 0.5, "w_mandatory": 1.0, "w_desirable": 0.3,
                     "recency_floor": 0.5, "corroboration_step": 0.1,
                     "coverage_floor_high": 50, "coverage_floor_medium": 80,
                     "confidence_floor": 70, "freshness_days": {"GST_STATUS": 30}},
        "requirements": PACK["requirements"],
    }})
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    client.post("/tenders/T1/bidders", json={"bidder_id": "B"})
    for bidder_id in ("A", "B"):
        client.post(f"/bidders/{bidder_id}/verify", params={"tender_id": "T1"})
        client.post(f"/bidders/{bidder_id}/evaluate", params={"tender_id": "T1"},
                   json={"bid_submission_date": "2026-09-22"})

    body = client.get("/tenders/T1/blockers").json()
    assert body["tender_id"] == "T1"
    blocked_ids = {b["requirement_id"] for b in body["blockers"]}
    assert blocked_ids == {"L1", "L2"}
    assert all(b["blocked_bidder_count"] == 2 for b in body["blockers"])


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


# --- Tender Compliance Report --------------------------------------------------
# Pure-function tests only, no database: tender_report() aggregates a plain
# list of dicts shaped exactly like GET /bidders/{id} returns (the same shape
# the dossier tests above already use for BIDDER_QUALIFYING etc.), and does
# no I/O of its own.

def bidder_fixture(bidder_id, *, score=None, coverage=None, confidence=None,
                    risk_level="MEDIUM", collusion=None):
    return {
        "bidder_id": bidder_id, "tender_id": "T1",
        "verdicts": [],
        "metrics": {"compliance_score": score, "verification_coverage": coverage,
                    "verification_coverage_mandatory": coverage, "evidence_confidence": confidence},
        "risk": {"level": risk_level, "triggers": [], "function_version": "risk@1"},
        "collusion": collusion,
    }


def test_tender_report_on_an_empty_tender_is_honest_zeros_not_fabricated_data():
    report = tender_report("T1", [])
    assert report["bidder_count"] == 0
    assert report["risk_distribution"] == {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    assert report["collusion"] == {"cluster_count": 0, "flagged_bidder_count": 0, "bidder_clusters": {}}
    assert report["compliance_score"] == {"mean": None, "min": None, "max": None,
                                           "count": 0, "null_count": 0}


def test_tender_report_mean_excludes_null_scores_and_counts_them_separately():
    bidders = [bidder_fixture("A", score=80.0), bidder_fixture("B", score=60.0),
               bidder_fixture("C", score=None)]
    cs = tender_report("T1", bidders)["compliance_score"]
    assert cs == {"mean": 70.0, "min": 60.0, "max": 80.0, "count": 2, "null_count": 1}


def test_tender_report_groups_two_separate_clusters_and_leaves_one_bidder_unflagged():
    """E is a tracked-but-isolated node (collusion present, flagged False) --
    not a cluster membership. F has no collusion signal at all."""
    bidders = [
        bidder_fixture("A", collusion={"flagged": True, "cluster_id": "cluster_A_B", "members": ["A", "B"]}),
        bidder_fixture("B", collusion={"flagged": True, "cluster_id": "cluster_A_B", "members": ["A", "B"]}),
        bidder_fixture("C", collusion={"flagged": True, "cluster_id": "cluster_C_D", "members": ["C", "D"]}),
        bidder_fixture("D", collusion={"flagged": True, "cluster_id": "cluster_C_D", "members": ["C", "D"]}),
        bidder_fixture("E", collusion={"flagged": False, "cluster_id": "cluster_E", "members": ["E"]}),
        bidder_fixture("F", collusion=None),
    ]
    c = tender_report("T1", bidders)["collusion"]
    assert c["cluster_count"] == 2
    assert c["flagged_bidder_count"] == 4
    assert c["bidder_clusters"] == {"A": "cluster_A_B", "B": "cluster_A_B",
                                     "C": "cluster_C_D", "D": "cluster_C_D"}
    assert "E" not in c["bidder_clusters"] and "F" not in c["bidder_clusters"]


def test_tender_report_risk_distribution_when_every_bidder_is_high_risk():
    bidders = [bidder_fixture(x, risk_level="HIGH") for x in "ABC"]
    report = tender_report("T1", bidders)
    assert report["risk_distribution"] == {"LOW": 0, "MEDIUM": 0, "HIGH": 3}
    assert report["bidder_count"] == 3


def test_tender_report_is_identical_when_built_twice_from_the_same_input():
    bidders = [
        bidder_fixture("A", score=80.0,
                        collusion={"flagged": True, "cluster_id": "cluster_A_B", "members": ["A", "B"]}),
        bidder_fixture("B", score=None, risk_level="HIGH"),
    ]
    first = tender_report("T1", bidders)
    second = tender_report("T1", bidders)
    assert first == second
    assert render_tender_report_text(first) == render_tender_report_text(second)


def test_render_tender_report_text_shows_the_right_facts_without_fabricating_a_zero():
    bidders = [
        bidder_fixture("A", score=80.0, coverage=60.0, confidence=70.0, risk_level="LOW"),
        bidder_fixture("B", risk_level="HIGH",
                        collusion={"flagged": True, "cluster_id": "cluster_B_C", "members": ["B", "C"]}),
        bidder_fixture("C", risk_level="HIGH",
                        collusion={"flagged": True, "cluster_id": "cluster_B_C", "members": ["B", "C"]}),
    ]
    text = render_tender_report_text(tender_report("T1", bidders))
    assert "Bidders: 3" in text
    assert "LOW: 1" in text
    assert "HIGH: 2" in text
    assert "Clusters: 1" in text
    assert "Flagged bidders: 2" in text
    assert "B -> cluster_B_C" in text
    assert "1 determined, 2 not yet determined" in text


# --- CSV export -----------------------------------------------------------
# Pure-function tests only, no database: bidders_to_csv() takes the same
# plain bidder-list shape the tender report tests above already use.

def test_bidders_to_csv_on_an_empty_list_is_a_header_row_only():
    text = bidders_to_csv([])
    reader = csv.DictReader(io.StringIO(text))
    assert reader.fieldnames == ["bidder_id", "risk_level", "compliance_score",
                                  "verification_coverage", "evidence_confidence",
                                  "collusion_flagged", "collusion_cluster_id"]
    assert list(reader) == []


def test_bidders_to_csv_round_trips_real_values_and_a_flagged_cluster():
    bidders = [
        bidder_fixture("A", score=80.0, coverage=60.0, confidence=70.0, risk_level="LOW"),
        bidder_fixture("B", risk_level="HIGH",
                        collusion={"flagged": True, "cluster_id": "cluster_B_C", "members": ["B", "C"]}),
    ]
    rows = list(csv.DictReader(io.StringIO(bidders_to_csv(bidders))))
    assert rows[0]["bidder_id"] == "A"
    assert rows[0]["risk_level"] == "LOW"
    assert rows[0]["compliance_score"] == "80.0"
    assert rows[0]["collusion_flagged"] == "False"
    assert rows[0]["collusion_cluster_id"] == ""
    assert rows[1]["bidder_id"] == "B"
    assert rows[1]["collusion_flagged"] == "True"
    assert rows[1]["collusion_cluster_id"] == "cluster_B_C"


def test_bidders_to_csv_never_writes_none_or_a_fabricated_zero_for_a_null_metric():
    bidders = [bidder_fixture("A")]  # every metric None by default
    rows = list(csv.DictReader(io.StringIO(bidders_to_csv(bidders))))
    assert rows[0]["compliance_score"] == ""
    assert rows[0]["verification_coverage"] == ""
    assert rows[0]["evidence_confidence"] == ""
    text = bidders_to_csv(bidders)
    assert "None" not in text
    assert "null" not in text.lower()


def test_bidders_to_csv_an_unflagged_tracked_bidder_shows_no_cluster_id():
    """A tracked-but-isolated node (collusion present, flagged False) is not a
    cluster membership worth a column -- same rule tender_report.py follows."""
    bidders = [bidder_fixture("A", collusion={"flagged": False, "cluster_id": "cluster_A",
                                               "members": ["A"]})]
    rows = list(csv.DictReader(io.StringIO(bidders_to_csv(bidders))))
    assert rows[0]["collusion_flagged"] == "False"
    assert rows[0]["collusion_cluster_id"] == ""


# --- tender-wide blocker summary --------------------------------------------

def _blocked_autopsy(*blocking):
    return {"would_qualify": False, "blocking_requirements": list(blocking),
            "counterfactual": None, "note": None}


def _blocking_row(rid, classification):
    return {"requirement_id": rid, "text": "irrelevant here", "verdict": "FAIL",
            "reason_code": "AUTHORITY_CONTRADICTED", "classification": classification,
            "overridden_by": None}


def test_blocker_summary_counts_and_sorts_by_how_many_bidders_are_blocked():
    autopsies = [
        _blocked_autopsy(_blocking_row("L1", "FATAL")),
        _blocked_autopsy(_blocking_row("L1", "FATAL"), _blocking_row("L2", "CURABLE")),
        _blocked_autopsy(_blocking_row("L2", "CURABLE")),
    ]
    assert blocker_summary(autopsies) == [
        {"requirement_id": "L1", "blocked_bidder_count": 2, "classifications": ["FATAL"]},
        {"requirement_id": "L2", "blocked_bidder_count": 2, "classifications": ["CURABLE"]},
    ]


def test_blocker_summary_skips_bidders_never_evaluated_or_already_qualifying():
    autopsies = [
        {"would_qualify": None, "blocking_requirements": [], "counterfactual": None,
         "note": "not yet evaluated"},
        {"would_qualify": True, "blocking_requirements": [], "counterfactual": None, "note": None},
        _blocked_autopsy(_blocking_row("L1", "FATAL")),
    ]
    assert blocker_summary(autopsies) == [
        {"requirement_id": "L1", "blocked_bidder_count": 1, "classifications": ["FATAL"]}]


def test_blocker_summary_on_no_autopsies_is_an_empty_list():
    assert blocker_summary([]) == []


def test_blocker_summary_records_every_classification_seen_for_a_requirement():
    """The same requirement can be FATAL for one bidder and CURABLE for
    another -- different bidders can hit the same leaf via different reason
    codes."""
    autopsies = [
        _blocked_autopsy(_blocking_row("L1", "FATAL")),
        _blocked_autopsy(_blocking_row("L1", "CURABLE")),
    ]
    assert blocker_summary(autopsies) == [
        {"requirement_id": "L1", "blocked_bidder_count": 2, "classifications": ["CURABLE", "FATAL"]}]


# --- Evidence Graph ---------------------------------------------------------
# Pure-function tests first (no database, no live adapter needed --
# Registry.from_file() loads the declarative manifest, which carries every
# authority's display name regardless of credential status).

def test_evidence_graph_skips_composite_requirements_and_includes_leaves():
    verdicts = [row("ROOT", "FAIL", "REQUIREMENT_NOT_SATISFIED"),
                row("L1", "PASS", "AUTHORITY_CONFIRMED"),
                row("L2", "FAIL", "AUTHORITY_CONTRADICTED")]
    evidence_by_path = {
        "bidder.gst.status": {"resolved": True, "value": "ACTIVE",
                               "unresolved_reason": None, "tier": "C",
                               "channel": None, "capability_id": None},
        "bidder.pan.status": {"resolved": True, "value": "VALID",
                               "unresolved_reason": None, "tier": "C",
                               "channel": None, "capability_id": None},
    }
    graph = build_evidence_graph(PACK, verdicts, evidence_by_path, Registry())
    assert {r["requirement_id"] for r in graph["requirements"]} == {"L1", "L2"}
    assert {e["path"] for e in graph["evidence"]} == {"bidder.gst.status", "bidder.pan.status"}
    # Self-declared only (no capability_id anywhere) -- no authority was ever
    # asked, so no authority node and no evidence->authority edge.
    assert graph["authorities"] == []
    assert all(e["to_kind"] != "authority" for e in graph["edges"])
    assert {(e["from_id"], e["to_id"]) for e in graph["edges"] if e["from_kind"] == "requirement"} == {
        ("L1", "bidder.gst.status"), ("L2", "bidder.pan.status")}


def test_evidence_graph_adds_an_authority_node_only_for_a_path_actually_verified():
    verdicts = [row("L1", "PASS", "AUTHORITY_CONFIRMED"), row("L2", "FAIL", "SELF_DECLARED_CEILING")]
    evidence_by_path = {
        "bidder.gst.status": {"resolved": True, "value": "ACTIVE",
                               "unresolved_reason": None, "tier": "A",
                               "channel": "AGGREGATOR", "capability_id": "GST_STATUS"},
        "bidder.pan.status": {"resolved": True, "value": "VALID",
                               "unresolved_reason": None, "tier": "C",
                               "channel": None, "capability_id": None},
    }
    graph = build_evidence_graph(PACK, verdicts, evidence_by_path, Registry.from_file())
    assert graph["authorities"] == [
        {"capability_id": "GST_STATUS", "authority": "Goods and Services Tax Network"}]
    authority_edges = [e for e in graph["edges"] if e["to_kind"] == "authority"]
    assert len(authority_edges) == 1
    assert authority_edges[0] == {
        "from_kind": "evidence", "from_id": "bidder.gst.status",
        "to_kind": "authority", "to_id": "GST_STATUS",
        "requirement_id": "L1", "verdict": "PASS", "resolved": True}


def test_evidence_graph_an_unattempted_path_still_gets_an_honest_evidence_node():
    """A path derived_bindings names but proj_evidence has nothing for at all
    -- never extracted, never verified -- must still be a real, visible node,
    not silently dropped."""
    graph = build_evidence_graph(PACK, [], {}, Registry())
    assert {e["path"] for e in graph["evidence"]} == {"bidder.gst.status", "bidder.pan.status"}
    assert all(e["resolved"] is False and e["value"] is None for e in graph["evidence"])
    assert graph["authorities"] == []


def test_evidence_graph_falls_back_to_the_capability_id_when_the_registry_has_no_manifest():
    verdicts = [row("L1", "FAIL", "AUTHORITY_UNAVAILABLE"), row("L2", "PASS", "AUTHORITY_CONFIRMED")]
    evidence_by_path = {
        "bidder.gst.status": {"resolved": False, "value": None,
                               "unresolved_reason": "AUTHORITY_UNAVAILABLE", "tier": None,
                               "channel": None, "capability_id": "GST_STATUS"},
        "bidder.pan.status": {"resolved": True, "value": "VALID", "unresolved_reason": None,
                               "tier": "A", "channel": "AGGREGATOR", "capability_id": "PAN_STATUS"},
    }
    graph = build_evidence_graph(PACK, verdicts, evidence_by_path, Registry())  # empty registry
    assert {a["capability_id"] for a in graph["authorities"]} == {"GST_STATUS", "PAN_STATUS"}
    # No manifest to resolve a display name from -- the capability id itself,
    # never a guessed or fabricated authority name.
    assert {a["authority"] for a in graph["authorities"]} == {"GST_STATUS", "PAN_STATUS"}


def test_evidence_graph_is_identical_when_built_twice_from_the_same_input():
    verdicts = [row("L1", "PASS", "AUTHORITY_CONFIRMED"), row("L2", "PASS", "AUTHORITY_CONFIRMED")]
    evidence_by_path = {
        "bidder.gst.status": {"resolved": True, "value": "ACTIVE", "unresolved_reason": None,
                               "tier": "A", "channel": "AGGREGATOR", "capability_id": "GST_STATUS"},
        "bidder.pan.status": {"resolved": True, "value": "VALID", "unresolved_reason": None,
                               "tier": "A", "channel": "AGGREGATOR", "capability_id": "PAN_STATUS"},
    }
    reg = Registry.from_file()
    assert build_evidence_graph(PACK, verdicts, evidence_by_path, reg) == \
        build_evidence_graph(PACK, verdicts, evidence_by_path, reg)


# --- through the real API ----------------------------------------------------

def test_evidence_graph_endpoint_refuses_without_an_adopted_pack(client):
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    assert client.get("/bidders/A/evidence-graph", params={"tender_id": "T1"}).status_code == 409


def test_evidence_graph_endpoint_after_a_real_evaluation(client):
    """No live capability is configured in this test environment (the same
    as every other through-the-API reporting test) -- verification genuinely
    runs and genuinely fails UNAUTHORIZED, which is exactly the case that
    proves an authority node appears for an *attempted*, not just a
    *successful*, verification."""
    client.post("/tenders/T1/rule-pack", json={"officer_id": "officer_1", "pack": {
        "rule_pack_id": "test.evidence-graph", "semver": "1.0.0",
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

    body = client.get("/bidders/A/evidence-graph", params={"tender_id": "T1"}).json()
    assert body["bidder_id"] == "A" and body["tender_id"] == "T1"
    assert {r["requirement_id"] for r in body["requirements"]} == {"L1", "L2"}
    assert {e["path"] for e in body["evidence"]} == {"bidder.gst.status", "bidder.pan.status"}
    assert all(not e["resolved"] for e in body["evidence"])  # unconfigured -- honestly unresolved
    assert {a["capability_id"] for a in body["authorities"]} == {"GST_STATUS", "PAN_STATUS"}
    req_evidence_edges = [e for e in body["edges"] if e["to_kind"] == "evidence"]
    evidence_authority_edges = [e for e in body["edges"] if e["to_kind"] == "authority"]
    assert len(req_evidence_edges) == 2
    assert len(evidence_authority_edges) == 2
    assert all(e["requirement_id"] in {"L1", "L2"} for e in req_evidence_edges)
