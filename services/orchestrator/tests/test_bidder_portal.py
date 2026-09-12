"""Round 6: a BIDDER account is a real, narrower user of this same system --
never a second auth system, never able to see another bidder or anything
officer-only. Every test here proves one edge of that boundary against a
real running app and real Postgres, not an assumption about the code.
"""
import pytest
from fastapi.testclient import TestClient

from satyapramana_store.app import app, db
from satyapramana_store.auth.models import Role
from satyapramana_store.auth.store import create_user

from .conftest import auth_headers
from .test_decide import EVAL, PACK, adopt


@pytest.fixture()
def client(conn):
    with TestClient(app) as c:
        from .conftest import auth_headers as _auth_headers
        c.headers.update(_auth_headers(conn, username="fixture_senior"))
        yield c
    app.dependency_overrides.clear()


def bidder_headers(conn, bidder_id: str, username: str | None = None) -> dict[str, str]:
    """Creates a real BIDDER account linked to `bidder_id` and returns a
    real, verifiable Authorization header -- the same shape an officer's
    header is, just a different role."""
    from satyapramana_store.auth.tokens import issue_token
    import os
    username = username or f"bidder_{bidder_id.lower()}"
    from satyapramana_store.auth.store import get_user_by_username
    user = get_user_by_username(conn, username)
    if user is None:
        user = create_user(conn, username, "correct horse battery staple",
                           display_name=f"Bidder {bidder_id}", role=Role.BIDDER,
                           bidder_id=bidder_id)
    token = issue_token(user, os.environ["SATYAPRAMANA_JWT_SECRET"])
    return {"Authorization": f"Bearer {token}"}


def register_and_adopt(client, conn, bidder_id="A"):
    adopt(client, conn)
    client.post("/tenders/T1/bidders", json={"bidder_id": bidder_id})


# --- identity and role separation ----------------------------------------------

def test_a_bidder_account_carries_its_bidder_id(conn):
    user = create_user(conn, "bidder_x", "correct horse battery staple",
                       "X Enterprises", Role.BIDDER, bidder_id="X")
    assert user.bidder_id == "X"
    assert user.role == Role.BIDDER


def test_creating_a_bidder_account_requires_a_bidder_id(client, conn):
    r = client.post("/auth/users", json={"username": "no_bidder_id", "password": "a-real-password-123",
                                         "display_name": "Nobody", "role": "BIDDER"},
                    headers=auth_headers(conn, username="admin_1", role=Role.ADMIN))
    assert r.status_code == 422


def test_bidder_id_is_refused_for_a_non_bidder_role(client, conn):
    r = client.post("/auth/users", json={"username": "over_specified", "password": "a-real-password-123",
                                         "display_name": "Someone", "role": "OFFICER", "bidder_id": "A"},
                    headers=auth_headers(conn, username="admin_1", role=Role.ADMIN))
    assert r.status_code == 422


def test_auth_me_reports_bidder_id_only_for_bidder_role(client, conn):
    register_and_adopt(client, conn, "A")
    r = client.get("/auth/me", headers=bidder_headers(conn, "A"))
    assert r.json() == {"username": "bidder_a", "display_name": "Bidder A",
                         "role": "BIDDER", "bidder_id": "A"}


# --- a bidder can read their own data, and nothing more ------------------------

def test_a_bidder_reads_their_own_tenders(client, conn):
    register_and_adopt(client, conn, "A")
    r = client.get("/me/tenders", headers=bidder_headers(conn, "A"))
    assert r.status_code == 200
    tenders = {t["tender_id"]: t for t in r.json()["tenders"]}
    assert tenders["T1"]["registered"] is True
    assert tenders["T1"]["requirements_published"] is True


def test_a_bidder_reads_their_own_requirements_with_no_constants_leaked(client, conn):
    register_and_adopt(client, conn, "A")
    r = client.get("/me/tenders/T1/requirements", headers=bidder_headers(conn, "A"))
    assert r.status_code == 200
    body = r.json()
    assert body == {"tender_id": "T1", "requirements": body["requirements"]}
    for req in body["requirements"]:
        assert set(req.keys()) == {"id", "text", "obligation", "source_page", "evidence_expected"}
    ids = {r["id"] for r in body["requirements"]}
    assert ids == {req["id"] for req in PACK["requirements"]}


def test_requirements_is_honestly_empty_with_no_adopted_pack(client, conn):
    client.post("/tenders/T2/bidders", json={"bidder_id": "B"})
    r = client.get("/me/tenders/T2/requirements", headers=bidder_headers(conn, "B"))
    assert r.status_code == 200
    assert r.json() == {"tender_id": "T2", "requirements": []}


def test_submission_status_is_scoped_to_its_own_tender(client, conn):
    """Found by Rishika during round-6 live testing: proj_verdicts was
    queried by bidder_id alone, so a bidder with a verdict on one tender
    showed UNDER_EVALUATION on every other tender they're registered on
    too, even ones with zero activity."""
    register_and_adopt(client, conn, "A")
    client.post("/tenders/T2/bidders", json={"bidder_id": "A"})
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)
    t1 = client.get("/me/tenders/T1/submission", headers=bidder_headers(conn, "A")).json()
    t2 = client.get("/me/tenders/T2/submission", headers=bidder_headers(conn, "A")).json()
    assert t1["status"] == "UNDER_EVALUATION"
    assert t2["status"] == "REGISTERED"


def test_a_bidder_reads_their_own_submission_and_status_progresses(client, conn):
    register_and_adopt(client, conn, "A")
    r = client.get("/me/tenders/T1/submission", headers=bidder_headers(conn, "A"))
    assert r.json()["status"] == "REGISTERED"
    assert r.json()["documents"] == []

    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    r = client.get("/me/tenders/T1/submission", headers=bidder_headers(conn, "A"))
    # no document uploaded in this test -- still REGISTERED, never guessed forward
    assert r.json()["status"] == "REGISTERED"


def test_result_is_honestly_unpublished_before_a_decision(client, conn):
    register_and_adopt(client, conn, "A")
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)
    r = client.get("/me/tenders/T1/result", headers=bidder_headers(conn, "A"))
    assert r.json() == {"tender_id": "T1", "bidder_id": "A", "published": False}


def test_result_is_published_once_an_officer_decides(client, conn):
    register_and_adopt(client, conn, "A")
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)
    client.post("/bidders/A/decision", params={"tender_id": "T1"},
               json={"decision": "DISQUALIFY", "note": "GST could not be confirmed."})
    r = client.get("/me/tenders/T1/result", headers=bidder_headers(conn, "A"))
    body = r.json()
    assert body["published"] is True
    assert body["decision"] == "DISQUALIFY"
    assert body["note"] == "GST could not be confirmed."
    # Never leaked to the bidder: metrics, risk, collusion, officer identity.
    assert not {"metrics", "risk", "collusion", "officer_id"} & body.keys()
    assert body["outcomes"], "expected at least one per-requirement outcome"
    for outcome in body["outcomes"]:
        assert set(outcome.keys()) == {"requirement_id", "verdict"}


# --- a bidder cannot read another bidder, or anything officer-only ------------

def test_a_bidder_cannot_read_another_bidders_submission_by_url(client, conn):
    register_and_adopt(client, conn, "A")
    client.post("/tenders/T1/bidders", json={"bidder_id": "B"})
    # There is no bidder_id in the /me/* path at all -- B's own token can
    # only ever see B's own data, by construction, not by a check that
    # could be forgotten on one endpoint.
    r = client.get("/me/tenders/T1/submission", headers=bidder_headers(conn, "B"))
    assert r.json()["bidder_id"] == "B"


def test_a_bidder_cannot_call_officer_only_endpoints(client, conn):
    register_and_adopt(client, conn, "A")
    headers = bidder_headers(conn, "A")
    assert client.get("/dashboard", headers=headers).status_code == 403
    assert client.get("/review-queue", headers=headers).status_code == 403
    assert client.get("/bidders/A", params={"tender_id": "T1"}, headers=headers).status_code == 403
    assert client.get("/tenders/T1/bidders", headers=headers).status_code == 403
    assert client.get("/audit/export", headers=headers).status_code == 403
    assert client.post("/bidders/A/decision", params={"tender_id": "T1"},
                       json={"decision": "QUALIFY"}, headers=headers).status_code == 403


def test_a_bidder_cannot_register_another_bidder_or_upload_for_one(client, conn):
    register_and_adopt(client, conn, "A")
    client.post("/tenders/T1/bidders", json={"bidder_id": "B"})
    headers = bidder_headers(conn, "A")
    assert client.post("/tenders/T1/bidders", json={"bidder_id": "C"},
                       headers=headers).status_code == 403
    r = client.post("/bidders/B/documents", params={"tender_id": "T1"},
                    files={"file": ("x.pdf", b"%PDF-1.4")}, headers=headers)
    assert r.status_code == 403


def test_a_bidder_can_upload_their_own_documents(client, conn):
    register_and_adopt(client, conn, "A")
    headers = bidder_headers(conn, "A")
    r = client.post("/bidders/A/documents", params={"tender_id": "T1"},
                    files={"file": ("x.pdf", b"%PDF-1.4\n%%EOF")}, headers=headers)
    assert r.status_code == 201


# --- the review queue (officer side) -------------------------------------------

def test_review_queue_lists_a_registered_bidder_needing_a_decision(client, conn):
    register_and_adopt(client, conn, "A")
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)
    r = client.get("/review-queue")
    assert r.status_code == 200
    row = next(b for b in r.json()["bidders"] if b["tender_id"] == "T1" and b["bidder_id"] == "A")
    assert row["status"] == "UNDER_EVALUATION"
    assert row["needs_decision"] is True


def test_review_queue_excludes_nobody_but_marks_decided_bidders(client, conn):
    register_and_adopt(client, conn, "A")
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)
    client.post("/bidders/A/decision", params={"tender_id": "T1"}, json={"decision": "QUALIFY"})
    r = client.get("/review-queue")
    row = next(b for b in r.json()["bidders"] if b["tender_id"] == "T1" and b["bidder_id"] == "A")
    assert row["status"] == "DECIDED"
    assert row["needs_decision"] is False


def test_review_queue_requires_an_officer(client, conn):
    register_and_adopt(client, conn, "A")
    r = client.get("/review-queue", headers=bidder_headers(conn, "A"))
    assert r.status_code == 403


# --- the officer's pre-decision preview of what the bidder will see -----------

def test_result_preview_matches_what_the_bidder_would_see(client, conn):
    register_and_adopt(client, conn, "A")
    client.post("/bidders/A/verify", params={"tender_id": "T1"})
    client.post("/bidders/A/evaluate", params={"tender_id": "T1"}, json=EVAL)
    client.post("/bidders/A/decision", params={"tender_id": "T1"},
               json={"decision": "QUALIFY", "note": "All mandatory requirements met."})
    officer_view = client.get("/tenders/T1/bidders/A/result-preview").json()
    bidder_view = client.get("/me/tenders/T1/result", headers=bidder_headers(conn, "A")).json()
    assert officer_view == bidder_view


def test_result_preview_is_honestly_unpublished_before_a_decision(client, conn):
    register_and_adopt(client, conn, "A")
    r = client.get("/tenders/T1/bidders/A/result-preview")
    assert r.json() == {"tender_id": "T1", "bidder_id": "A", "published": False}


def test_result_preview_requires_an_officer(client, conn):
    register_and_adopt(client, conn, "A")
    r = client.get("/tenders/T1/bidders/A/result-preview", headers=bidder_headers(conn, "A"))
    assert r.status_code == 403


# --- bidder-id lookup for the admin's account-creation form -------------------

def test_bidder_ids_lists_every_bidder_with_its_tenders(client, conn):
    register_and_adopt(client, conn, "A")
    client.post("/tenders/T2/bidders", json={"bidder_id": "B"})
    r = client.get("/bidder-ids")
    assert r.status_code == 200
    by_id = {row["bidder_id"]: row["tender_ids"] for row in r.json()["bidders"]}
    assert by_id["A"] == ["T1"]
    assert by_id["B"] == ["T2"]


def test_bidder_ids_requires_an_officer(client, conn):
    register_and_adopt(client, conn, "A")
    r = client.get("/bidder-ids", headers=bidder_headers(conn, "A"))
    assert r.status_code == 403
