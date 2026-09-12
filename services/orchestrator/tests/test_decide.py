"""The closed loop: adopt a rule pack, verify, evaluate, walk the provenance.

The rule pack here encodes illustrative requirement text pending a real GeM
tender PDF. It is a structural fixture, not simulated evidence: no authority
response is fabricated anywhere, which is why every verdict below comes out
UNKNOWN.
"""
import copy

import pytest
from fastapi.testclient import TestClient

from satyapramana_store.app import app, db

from .conftest import auth_headers

PACK = {
    "rule_pack_id": "cpcl.tender.2026.gem-test",
    "semver": "1.0.0",
    "tender_reference": {
        "tender_id": "T1",
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
        {"id": "R4", "text": "Bidder shall hold valid GST registration and PAN.",
         "source": {"page": 14, "region": [72, 410, 523, 468]},
         "obligation": "mandatory", "operator": "ALL_OF",
         "children": ["R4.1", "R4.2"]},
        {"id": "R4.1", "text": "Valid GST registration, active on the bid submission date.",
         "source": {"page": 14, "region": [72, 470, 523, 494]},
         "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "active_on",
                       "subject": {"field": "bidder.gst.status_history"},
                       "at": {"context": "bid_submission_date"}}},
        {"id": "R4.2", "text": "Valid PAN issued to the bidding entity.",
         "source": {"page": 14, "region": [72, 496, 523, 520]},
         "obligation": "mandatory", "operator": "LEAF",
         "predicate": {"op": "eq", "left": {"field": "bidder.pan.status"},
                       "right": {"literal": "VALID"}}},
    ],
}

EVAL = {"as_of": "2026-09-10", "bid_submission_date": "2026-09-22"}


@pytest.fixture()
def client(conn):
    app.dependency_overrides[db] = lambda: conn
    with TestClient(app) as c:
        # Default senior-officer header: every non-public route requires a
        # login now. Per-request lower-role headers in gate tests override it.
        from .conftest import auth_headers
        c.headers.update(auth_headers(conn, username="fixture_senior"))
        yield c
    app.dependency_overrides.clear()


def adopt(client, conn, pack=None):
    return client.post("/tenders/T1/rule-pack",
                       json={"pack": pack or PACK}, headers=auth_headers(conn))


def full_run(client, conn):
    adopt(client, conn)
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    return client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)


# --- adoption -----------------------------------------------------------------

def test_a_valid_pack_is_adopted_with_a_content_addressed_version(client, conn):
    body = adopt(client, conn).json()
    assert body["rule_pack_version"].startswith("cpcl.tender.2026.gem-test@1.0.0+")
    assert len(body["rule_pack_version"].split("+")[1]) == 12


def test_adoption_is_a_human_event(client, conn):
    adopt(client, conn)
    with conn.cursor() as cur:
        cur.execute("SELECT actor_kind, actor_id, payload FROM events "
                    "WHERE event_type='RULE_PACK_ADOPTED'")
        kind, actor, payload = cur.fetchone()
    assert kind == "HUMAN" and actor == "officer_1"
    assert payload["requirement_count"] == 3


def test_a_pack_referencing_an_unproducible_path_is_refused(client, conn):
    """Rule 8, against the live registry. Otherwise the requirement would become
    a permanent, unexplained UNKNOWN in production."""
    bad = copy.deepcopy(PACK)
    bad["requirements"][2]["predicate"]["left"]["field"] = "bidder.astrology.sign"
    r = adopt(client, conn, bad)
    assert r.status_code == 422
    violations = r.json()["detail"]["violations"]
    assert any(v["rule"] == 8 for v in violations)


def test_an_unreviewed_requirement_blocks_adoption(client, conn):
    bad = copy.deepcopy(PACK)
    bad["requirements"][2]["review_required"] = True
    bad["requirements"][2]["review_note"] = "clause 7.2 is ambiguous"
    r = adopt(client, conn, bad)
    assert r.status_code == 422
    assert any(v["rule"] == 11 for v in r.json()["detail"]["violations"])


def test_a_pack_reading_the_system_clock_is_refused(client, conn):
    bad = copy.deepcopy(PACK)
    bad["requirements"][2]["predicate"] = {
        "op": "date_before", "left": {"field": "bidder.pan.status"},
        "right": {"field": "today"}}
    assert any(v["rule"] == 10
               for v in adopt(client, conn, bad).json()["detail"]["violations"])


def test_an_adopted_pack_cannot_be_mutated(client, conn):
    import psycopg
    adopt(client, conn)
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        with conn.cursor() as cur:
            cur.execute("UPDATE rule_packs SET semver='9.9.9'")


def test_a_published_tender_cannot_silently_change_its_approved_requirements(client, conn):
    """Adopting a new rule pack version for the same tender must never
    mutate what an earlier version said, and a verdict already computed
    against v1 must keep pointing at v1 -- the versioned, content-addressed
    design (docs/RULE_PACKS.md) exists specifically so 'publish' is never a
    silent edit of the requirements bidders were already evaluated against.
    """
    v1 = adopt(client, conn).json()
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    result_v1 = client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL).json()
    assert result_v1["rule_pack_version"] == v1["rule_pack_version"]

    v2_pack = copy.deepcopy(PACK)
    v2_pack["semver"] = "2.0.0"
    v2_pack["requirements"][2]["text"] = "A materially different requirement text, v2 only."
    v2 = adopt(client, conn, v2_pack).json()
    assert v2["rule_pack_version"] != v1["rule_pack_version"]

    # v1's stored body is byte-for-byte unchanged -- fetched by its own
    # version string, not silently rewritten by v2's adoption.
    with conn.cursor() as cur:
        cur.execute("SELECT body FROM rule_packs WHERE rule_pack_version=%s", (v1["rule_pack_version"],))
        v1_body_after = cur.fetchone()[0]
    assert v1_body_after["requirements"][2]["text"] == "Valid PAN issued to the bidding entity."
    assert v1_body_after["semver"] == "1.0.0"

    # The verdict already recorded against v1 still names v1 -- adopting v2
    # did not retroactively reattribute it.
    with conn.cursor() as cur:
        cur.execute("SELECT payload->>'rule_pack_version' FROM events "
                    "WHERE event_type='REQUIREMENT_EVALUATED' AND bidder_id='A' "
                    "ORDER BY seq LIMIT 1")
        first_evaluation_version = cur.fetchone()[0]
    assert first_evaluation_version == v1["rule_pack_version"]

    # Both versions remain independently stored and citable.
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM rule_packs WHERE tender_id='T1'")
        assert cur.fetchone()[0] == 2


def test_evaluation_without_an_adopted_pack_is_refused(client):
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    r = client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)
    assert r.status_code == 409


# --- the decision stage -------------------------------------------------------

def test_every_requirement_is_evaluated(client, conn):
    body = full_run(client, conn).json()
    assert set(body["verdicts"]) == {"R4", "R4.1", "R4.2"}


def test_with_no_authority_configured_everything_is_unknown_never_pass(client, conn):
    verdicts = full_run(client, conn).json()["verdicts"]
    assert all(v["verdict"] == "UNKNOWN" for v in verdicts.values())
    assert not any(v["verdict"] == "PASS" for v in verdicts.values())


def test_the_reason_propagates_from_the_evidence_record(client, conn):
    """Not a generic placeholder: the officer sees why."""
    verdicts = full_run(client, conn).json()["verdicts"]
    assert verdicts["R4.2"]["reason"] == "AUTHORITY_UNAUTHORIZED"
    assert "awaiting credentials" not in verdicts["R4.2"]["reason"].lower()


def test_unknown_children_compose_to_unknown_not_fail(client, conn):
    verdicts = full_run(client, conn).json()["verdicts"]
    assert verdicts["R4"]["verdict"] == "UNKNOWN"


def test_every_verdict_records_the_rule_pack_that_produced_it(client, conn):
    version = full_run(client, conn).json()["rule_pack_version"]
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT payload->>'rule_pack_version' FROM events "
                    "WHERE event_type='REQUIREMENT_EVALUATED'")
        assert [r[0] for r in cur.fetchall()] == [version]


def test_evaluation_is_deterministic(client, conn):
    """Same evidence, same rule pack, same verdicts -- every time."""
    adopt(client, conn)
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"})
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    first = client.post("/bidders/A/evaluate", params={"tender_id": "T1"},
                        json=EVAL).json()["verdicts"]
    for _ in range(5):
        again = client.post("/bidders/A/evaluate", params={"tender_id": "T1"},
                            json=EVAL).json()["verdicts"]
        assert again == first


def test_the_verdict_carries_its_clause_location_in_the_tender(client, conn):
    """The other half of provenance: verdict -> rule -> quoted clause."""
    full_run(client, conn)
    with conn.cursor() as cur:
        cur.execute("SELECT payload->'source' FROM events "
                    "WHERE event_type='REQUIREMENT_EVALUATED' "
                    "AND payload->>'requirement_id'='R4.1'")
        assert cur.fetchone()[0] == {"page": 14, "region": [72, 470, 523, 494]}


# --- provenance, end to end ---------------------------------------------------

def test_the_provenance_walk_reaches_the_evidence(client, conn):
    full_run(client, conn)
    trail = client.get("/bidders/A/requirements/R4.2/provenance").json()["trail"]
    kinds = [t["event_type"] for t in trail]
    assert kinds[0] == "REQUIREMENT_EVALUATED"
    assert "EVIDENCE_FUSED" in kinds
    assert "VERIFICATION_FAILED" in kinds, (
        "an unreachable authority is part of the evidence chain, not a gap in it")


def test_the_trail_explains_an_unknown(client, conn):
    full_run(client, conn)
    trail = client.get("/bidders/A/requirements/R4.2/provenance").json()["trail"]
    failure = next(t for t in trail if t["event_type"] == "VERIFICATION_FAILED")
    assert failure["payload"]["failure_code"] == "UNAUTHORIZED"
    assert "awaiting credentials" in failure["payload"]["detail"]


def test_a_composed_verdict_walks_to_its_first_child(client, conn):
    full_run(client, conn)
    trail = client.get("/bidders/A/requirements/R4/provenance").json()["trail"]
    assert trail[0]["payload"]["requirement_id"] == "R4"
    assert trail[1]["payload"]["requirement_id"] == "R4.1"


# --- the read model -----------------------------------------------------------

def test_metrics_report_zero_coverage_honestly(client, conn):
    full_run(client, conn)
    body = client.get("/bidders/A", params={"tender_id": "T1"}).json()
    assert body["metrics"]["verification_coverage"] == 0.0
    assert body["metrics"]["compliance_score"] is None, (
        "nothing determinate -- must be null, never zero")


def test_an_unverified_mandatory_requirement_is_high_risk(client, conn):
    full_run(client, conn)
    risk = client.get("/bidders/A", params={"tender_id": "T1"}).json()["risk"]
    assert risk["level"] == "HIGH"
    assert any("unverified" in t for t in risk["triggers"])
    assert not any("failed" in t for t in risk["triggers"]), (
        "UNKNOWN must never be reported as a failure")


def test_an_override_keeps_the_systems_own_conclusion(client, conn):
    full_run(client, conn)
    client.post("/bidders/A/override", params={"tender_id": "T1"},
                json={"requirement_id": "R4.2",
                      "verdict_after": "PASS",
                      "justification": "Original PAN card produced in person."},
                headers=auth_headers(conn))
    verdicts = {v["requirement_id"]: v for v in
                client.get("/bidders/A", params={"tender_id": "T1"}).json()["verdicts"]}
    assert verdicts["R4.2"]["verdict_system"] == "UNKNOWN"
    assert verdicts["R4.2"]["verdict_effective"] == "PASS"
    assert verdicts["R4.2"]["overridden_by"] == "officer_1"


def test_the_chain_stays_intact_across_the_whole_flow(client, conn):
    import json
    full_run(client, conn)
    client.post("/bidders/A/decision", params={"tender_id": "T1"},
                json={"decision": "DISQUALIFY"}, headers=auth_headers(conn))

    report = client.get("/audit/verify").json()
    assert report["intact"]
    assert report["events"] == report["linked"] == report["rehashed"] > 0

    # Every stage of the flow is present in the one chain, and only the two
    # human acts carry a HUMAN actor.
    lines = [json.loads(l) for l in client.get("/audit/export").text.splitlines()
             if l.strip()][1:]
    kinds = {l["event_type"] for l in lines}
    assert {"RULE_PACK_ADOPTED", "BIDDER_REGISTERED", "VERIFICATION_REQUESTED",
            "VERIFICATION_FAILED", "EVIDENCE_FUSED", "REQUIREMENT_EVALUATED",
            "DECISION_RECORDED"} <= kinds
    human = {l["event_type"] for l in lines if l["actor_kind"] == "HUMAN"}
    assert human == {"RULE_PACK_ADOPTED", "DECISION_RECORDED"}
