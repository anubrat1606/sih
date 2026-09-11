"""The orchestrator's HTTP surface, end to end against a real PostgreSQL."""
import json

import pytest
from fastapi.testclient import TestClient

from satyapramana_store import app as app_module
from satyapramana_store.app import app, db

from .conftest import auth_headers


@pytest.fixture()
def client(conn):
    app.dependency_overrides[db] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, tender, bidder, **attrs):
    return client.post(f"/tenders/{tender}/bidders",
                       json={"bidder_id": bidder, **attrs})


# --- honest capability reporting ---------------------------------------------

def test_capabilities_states_that_nothing_is_live(client):
    body = client.get("/capabilities").json()
    assert body["live_count"] == 0
    assert "UNKNOWN" in body["note"]
    assert "no simulated authority response" in body["note"].lower()


def test_unavailable_capabilities_say_why(client):
    rows = client.get("/capabilities").json()["capabilities"]
    for row in rows:
        if row["status"] == "UNAVAILABLE":
            assert row["detail"], f"{row['adapter_id']} must say why"


# --- verification is honest when nothing is configured ------------------------

def test_verification_returns_unknown_not_pass(client):
    register(client, "T1", "A")
    body = client.post("/bidders/A/verify", params={"tender_id": "T1"}).json()
    assert body["outcomes"], "every registered capability is attempted"
    assert all(o["verdict"] == "UNKNOWN" for o in body["outcomes"])
    assert not any(o["verdict"] == "PASS" for o in body["outcomes"])


def test_the_reason_for_each_unknown_is_machine_readable(client):
    register(client, "T1", "A")
    body = client.post("/bidders/A/verify", params={"tender_id": "T1"}).json()
    for outcome in body["outcomes"]:
        assert outcome["reason_code"].startswith(("AUTHORITY_", "NO_ADAPTER", "AS_OF"))
        assert outcome["detail"]


def test_a_failed_verification_is_recorded_as_an_event(client, conn):
    register(client, "T1", "A")
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM events WHERE event_type='VERIFICATION_FAILED'")
        assert cur.fetchone()[0] > 0, "an unreachable authority is a recorded fact"


# --- collusion registration is not all-or-nothing -----------------------------

def test_a_bidder_links_on_whatever_subset_is_present(client):
    """The Express implementation required all four attributes, so one missing
    field silently disabled collusion detection for that bidder."""
    register(client, "T1", "A", phone="98765 43210")
    body = register(client, "T1", "B", phone="9876543210").json()
    assert body["shared_attribute_links"] == [{"with": "A", "attribute": "phone"}]


def test_attribute_matching_is_whitespace_and_case_insensitive(client):
    register(client, "T1", "A", director_name="  Ramesh   KUMAR ")
    body = register(client, "T1", "B", director_name="ramesh kumar").json()
    assert body["shared_attribute_links"][0]["attribute"] == "director_name"


def test_an_unrelated_bidder_is_not_linked(client):
    register(client, "T1", "A", phone="1111111111")
    body = register(client, "T1", "C", phone="2222222222").json()
    assert body["shared_attribute_links"] == []


def test_raw_attribute_values_never_enter_the_log(client, conn):
    register(client, "T1", "A", bank_account="123456789012")
    register(client, "T1", "B", bank_account="123456789012")
    with conn.cursor() as cur:
        cur.execute("SELECT payload::text FROM events")
        everything = " ".join(r[0] for r in cur.fetchall())
    assert "123456789012" not in everything


def test_the_collusion_endpoint_reports_the_cluster(client):
    register(client, "T1", "A", phone="1111111111")
    register(client, "T1", "B", phone="1111111111")
    register(client, "T1", "C", phone="9999999999")
    by_id = {b["bidder_id"]: b for b in
             client.get("/tenders/T1/collusion").json()["bidders"]}
    assert by_id["A"]["flagged"] and by_id["B"]["flagged"]
    assert by_id["A"]["cluster_id"] == by_id["B"]["cluster_id"] == "cluster_A_B"
    assert by_id["C"]["flagged"] is False


def test_collusion_edges_names_the_specific_pair_and_attribute(client):
    register(client, "T1", "A", phone="1111111111", address="1 Test Rd")
    register(client, "T1", "B", phone="1111111111")
    register(client, "T1", "C", address="9 Other Rd")
    edges = client.get("/tenders/T1/collusion/edges").json()["edges"]
    assert edges == [{"bidder_a": "B", "bidder_b": "A", "attribute": "phone"}]


def test_collusion_edges_for_an_unflagged_tender_is_empty(client):
    register(client, "T1", "A", phone="1111111111")
    assert client.get("/tenders/T1/collusion/edges").json() == {"tender_id": "T1", "edges": []}


def test_listing_tender_bidders_returns_the_same_summary_as_the_single_lookup(client):
    register(client, "T1", "A")
    register(client, "T1", "B")
    listed = client.get("/tenders/T1/bidders").json()["bidders"]
    assert {b["bidder_id"] for b in listed} == {"A", "B"}
    single = client.get("/bidders/A", params={"tender_id": "T1"}).json()
    listed_a = next(b for b in listed if b["bidder_id"] == "A")
    assert listed_a["metrics"] == single["metrics"]


def test_listing_bidders_for_an_empty_tender_is_an_empty_list_not_an_error(client):
    body = client.get("/tenders/T-EMPTY/bidders").json()
    assert body == {"tender_id": "T-EMPTY", "bidders": []}


def test_listing_tenders_returns_every_tender_with_a_registered_bidder(client):
    register(client, "T-LIST-1", "A")
    register(client, "T-LIST-2", "B")
    tenders = client.get("/tenders").json()["tenders"]
    assert "T-LIST-1" in tenders and "T-LIST-2" in tenders


def test_listing_tenders_with_none_registered_is_an_empty_list(client):
    assert client.get("/tenders").json() == {"tenders": []}


# --- read models --------------------------------------------------------------

def test_compliance_score_is_null_not_zero_when_nothing_is_determinate(client):
    register(client, "T1", "A")
    metrics = client.get("/bidders/A", params={"tender_id": "T1"}).json()["metrics"]
    assert metrics["compliance_score"] is None
    assert metrics["compliance_score"] != 0


def test_the_three_metrics_are_reported_separately(client):
    register(client, "T1", "A")
    metrics = client.get("/bidders/A", params={"tender_id": "T1"}).json()["metrics"]
    assert set(metrics) == {"compliance_score", "verification_coverage",
                            "verification_coverage_mandatory", "evidence_confidence"}
    assert "overall" not in metrics and "trust_score" not in metrics


def test_a_collusion_link_drives_risk_to_high(client):
    register(client, "T1", "A", phone="1111111111")
    register(client, "T1", "B", phone="1111111111")
    risk = client.get("/bidders/A", params={"tender_id": "T1"}).json()["risk"]
    assert risk["level"] == "HIGH"
    assert any("collusion" in t for t in risk["triggers"])
    assert risk["function_version"]


# --- officer actions ----------------------------------------------------------

def test_a_decision_is_recorded_with_a_hash(client, conn):
    register(client, "T1", "A")
    body = client.post("/bidders/A/decision", params={"tender_id": "T1"},
                       json={"decision": "DISQUALIFY"},
                       headers=auth_headers(conn)).json()
    assert len(body["hash"]) == 64 and body["decision"] == "DISQUALIFY"


def test_an_invalid_decision_is_refused(client, conn):
    register(client, "T1", "A")
    r = client.post("/bidders/A/decision", params={"tender_id": "T1"},
                    json={"decision": "MAYBE"}, headers=auth_headers(conn))
    assert r.status_code == 422


def test_an_override_without_a_justification_is_refused(client, conn):
    register(client, "T1", "A")
    r = client.post("/bidders/A/override", params={"tender_id": "T1"},
                    json={"requirement_id": "R4.1",
                          "verdict_after": "PASS", "justification": ""},
                    headers=auth_headers(conn))
    assert r.status_code == 422


def test_a_decision_without_a_token_is_refused(client):
    register(client, "T1", "A")
    r = client.post("/bidders/A/decision", params={"tender_id": "T1"},
                    json={"decision": "QUALIFY"})
    assert r.status_code == 401


def test_a_base_officer_cannot_override_a_verdict(client, conn):
    register(client, "T1", "A")
    from satyapramana_store.auth.models import Role
    r = client.post("/bidders/A/override", params={"tender_id": "T1"},
                    json={"requirement_id": "R4.1", "verdict_after": "PASS",
                          "justification": "manual review"},
                    headers=auth_headers(conn, username="junior_officer", role=Role.OFFICER))
    assert r.status_code == 403


# --- audit --------------------------------------------------------------------

def test_the_exported_chain_verifies(client, conn):
    register(client, "T1", "A", phone="1111111111")
    register(client, "T1", "B", phone="1111111111")
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    client.post("/bidders/A/decision", params={"tender_id": "T1"},
                json={"decision": "DISQUALIFY"}, headers=auth_headers(conn))

    report = client.get("/audit/verify").json()
    assert report["intact"] is True
    assert report["events"] == report["linked"] == report["rehashed"] > 0


def test_the_export_is_json_lines_a_third_party_can_check(client):
    register(client, "T1", "A")
    text = client.get("/audit/export").text
    lines = [json.loads(l) for l in text.splitlines() if l.strip()]
    assert lines[0]["chain_format"] == "satyapramana/chain/1"
    assert all("prev_hash" in l and "hash" in l for l in lines[1:])


def test_the_officer_decision_appears_in_the_chain(client, conn):
    register(client, "T1", "A")
    client.post("/bidders/A/decision", params={"tender_id": "T1"},
                json={"decision": "QUALIFY"}, headers=auth_headers(conn))
    lines = [json.loads(l) for l in client.get("/audit/export").text.splitlines()
             if l.strip()][1:]
    decisions = [l for l in lines if l["event_type"] == "DECISION_RECORDED"]
    assert len(decisions) == 1
    assert decisions[0]["actor_kind"] == "HUMAN"
    assert decisions[0]["actor_id"] == "officer_1"


def test_provenance_is_404_when_no_verdict_exists(client):
    register(client, "T1", "A")
    assert client.get("/bidders/A/requirements/R4.1/provenance").status_code == 404


# --- attribute normalisation --------------------------------------------------

@pytest.mark.parametrize("a,b", [
    ("+91 98765 43210", "9876543210"),
    ("098765-43210", "98765 43210"),
    ("98765.43210", "9876543210"),
])
def test_the_same_phone_written_differently_is_one_phone(client, a, b):
    """People concealing a link rarely format their fields identically."""
    register(client, "T1", "A", phone=a)
    body = register(client, "T1", "B", phone=b).json()
    assert body["shared_attribute_links"] == [{"with": "A", "attribute": "phone"}]


@pytest.mark.parametrize("a,b", [
    ("50100 1234 5678", "501001234-5678"),
    ("ABC 0001234", "abc0001234"),
])
def test_the_same_account_written_differently_is_one_account(client, a, b):
    register(client, "T1", "A", bank_account=a)
    body = register(client, "T1", "B", bank_account=b).json()
    assert body["shared_attribute_links"] == [{"with": "A", "attribute": "bank_account"}]


def test_genuinely_different_numbers_are_not_linked(client):
    register(client, "T1", "A", phone="9876543210")
    assert register(client, "T1", "B", phone="9876543211").json()[
        "shared_attribute_links"] == []


def test_an_attribute_does_not_collide_with_another_attribute(client):
    """The fingerprint is salted with the attribute name, so the same digits
    appearing as a phone and as an account number are not a shared attribute."""
    register(client, "T1", "A", phone="9876543210")
    body = register(client, "T1", "B", bank_account="9876543210").json()
    assert body["shared_attribute_links"] == []
