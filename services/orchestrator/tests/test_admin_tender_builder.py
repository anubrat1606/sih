"""The government-official admin tender builder: tender-level document
upload, the requirement-type catalog, and rule pack dry-run validation.

Nothing here introduces a second requirement representation or a second
validator -- see satyapramana_store/requirement_types.py and
rulepacks.py::validate_only, both of which reuse the existing schema,
the existing live registry, and the existing rule-8-through-13 checker
exactly as POST /tenders/{id}/rule-pack always has.
"""
import copy

import pytest
from fastapi.testclient import TestClient

from satyapramana_store.app import app, db

from .conftest import auth_headers
from .conftest_pdf import text_pdf
from .test_decide import PACK


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


# --- tender document upload ---------------------------------------------------

def test_tender_document_upload_requires_authentication(client):
    client.headers.pop("Authorization", None)  # this one request must be anonymous
    r = client.post("/tenders/T1/documents", files={"file": ("notice.pdf", text_pdf(["a tender notice"]))})
    assert r.status_code == 401


def test_tender_document_upload_is_recorded_and_retrievable(client, conn):
    data = text_pdf(["Supply of centrifugal pumps -- eligibility criteria on page 14."])
    r = client.post("/tenders/T1/documents", files={"file": ("notice.pdf", data, "application/pdf")},
                    headers=auth_headers(conn, username="priya"))
    assert r.status_code == 201
    body = r.json()
    assert body["tender_id"] == "T1"
    assert len(body["document_sha256"]) == 64

    # Retrievable by hash, the same endpoint bidder documents use.
    got = client.get(f"/documents/{body['document_sha256']}")
    assert got.status_code == 200
    assert got.content == data


def test_tender_document_upload_is_recorded_as_the_real_authenticated_officer(client, conn):
    """DOCUMENT_INGESTED is not in events.HUMAN_EVENT_TYPES -- append()
    refuses a HUMAN actor for it, the same reason bidder document upload
    records it under the SYSTEM ingest actor. The authenticated officer who
    triggered the upload is still real, just recorded in the payload
    (`uploaded_by`), the same place TENDER_CREATED already puts
    `created_by`."""
    data = text_pdf(["a tender notice"])
    client.post("/tenders/T1/documents", files={"file": ("notice.pdf", data)},
               headers=auth_headers(conn, username="priya"))
    with conn.cursor() as cur:
        cur.execute("SELECT actor_kind, actor_id, payload FROM events "
                    "WHERE event_type='DOCUMENT_INGESTED' AND tender_id='T1'")
        kind, actor, payload = cur.fetchone()
    assert kind == "SYSTEM"
    assert payload["uploaded_by"] == "priya"
    assert payload["declared_type"] == "TENDER_NOTICE"


def test_tender_document_upload_runs_no_identifier_extraction(client, conn):
    """A tender notice is not a bidder identity document -- uploading one
    must not emit FIELD_EXTRACTED events, even if it happens to contain a
    structurally GSTIN-shaped or PAN-shaped substring."""
    from .conftest_pdf import valid_gstin
    data = text_pdf([f"Reference GSTIN of the issuing department: {valid_gstin()}"])
    client.post("/tenders/T1/documents", files={"file": ("notice.pdf", data)},
               headers=auth_headers(conn))
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM events WHERE event_type='FIELD_EXTRACTED' AND tender_id='T1'")
        assert cur.fetchone()[0] == 0


def test_tender_document_upload_rejects_an_empty_file(client, conn):
    r = client.post("/tenders/T1/documents", files={"file": ("empty.pdf", b"")},
                    headers=auth_headers(conn))
    assert r.status_code == 400


# --- requirement-type catalog --------------------------------------------------

def test_requirement_types_endpoint_lists_every_type_the_brief_names(client):
    body = client.get("/requirement-types").json()
    ids = {t["id"] for t in body["requirement_types"]}
    for expected in ("GST", "PAN", "CIN", "UDYAM", "DOCUMENT_REQUIRED", "MIN_TURNOVER",
                     "NET_WORTH", "ITR", "EXPERIENCE", "SIMILAR_WORK", "OEM_AUTHORIZATION",
                     "CERTIFICATION", "EPFO_ESIC", "DECLARATION", "TECHNICAL",
                     # round 10
                     "DIGILOCKER_AADHAAR", "STARTUP_INDIA", "NSIC", "MAKE_IN_INDIA",
                     "BLACKLIST_DEBARMENT"):
        assert expected in ids


def test_requirement_types_marks_identity_documents_as_evidence_backed(client):
    body = client.get("/requirement-types").json()
    by_id = {t["id"]: t for t in body["requirement_types"]}
    for backed in ("GST", "PAN", "CIN", "UDYAM"):
        assert by_id[backed]["evidence_backed"] is True
        assert by_id[backed]["backed_fields"]  # at least one real, live-producible path


def test_requirement_types_marks_digilocker_aadhaar_as_evidence_backed(client):
    """Round 10: declared as a real capability in schemas/capability_registry.json
    (not a null adapter -- a real consent flow exists, unlike Udyam), so it's
    producible the same way PAN/GST/CIN are, credentials or not -- evidence_backed
    reflects whether a real evidence *path* exists, never whether it's currently
    configured (that distinction is what AWAITING_CREDENTIALS vs LIVE is for)."""
    body = client.get("/requirement-types").json()
    entry = {t["id"]: t for t in body["requirement_types"]}["DIGILOCKER_AADHAAR"]
    assert entry["evidence_backed"] is True
    assert "bidder.digilocker.aadhaar_verified" in entry["backed_fields"]


def test_requirement_types_honestly_flags_unbacked_types(client):
    """No fabricated evidence path for the types nothing in this system can
    currently produce -- each says so, with a real reason, not a bare false.
    MIN_TURNOVER/NET_WORTH, DECLARATION, OEM_AUTHORIZATION/STARTUP_INDIA/
    NSIC/MAKE_IN_INDIA/BLACKLIST_DEBARMENT, then EXPERIENCE/SIMILAR_WORK/
    CERTIFICATION, and finally ITR/EPFO_ESIC (a further round-11 follow-up)
    all moved out of this list in turn, each onto the same self-declared
    mechanism DECLARATION uses, each with its own honest weaker-evidence
    caveat -- see test_declarations.py's growing family of
    ..._are_also_evidence_backed tests. DOCUMENT_REQUIRED and TECHNICAL are
    the only two types left with no backed field, and that is by design,
    not a gap: both are intentionally generic/open-ended (see their own
    notes in requirement_types.py), never candidates for a self-declared
    path the way a named, specific fact like "filed ITR" is."""
    body = client.get("/requirement-types").json()
    by_id = {t["id"]: t for t in body["requirement_types"]}
    for unbacked in ("DOCUMENT_REQUIRED", "TECHNICAL"):
        assert by_id[unbacked]["evidence_backed"] is False
        assert by_id[unbacked]["backed_fields"] == []
        assert by_id[unbacked]["note"]  # a real, non-empty explanation


def test_requirement_types_marks_financial_types_as_evidence_backed(client):
    """MIN_TURNOVER/NET_WORTH are extracted from a submitted financial
    statement (extract/financials.py) -- real evidence, though self-
    declared (no authority exists to verify a claimed turnover or net
    worth against), which the note must say plainly rather than implying
    a path to a verified PASS."""
    body = client.get("/requirement-types").json()
    by_id = {t["id"]: t for t in body["requirement_types"]}
    for backed in ("MIN_TURNOVER", "NET_WORTH"):
        assert by_id[backed]["evidence_backed"] is True
        assert by_id[backed]["backed_fields"]
        assert "self-declared" in by_id[backed]["note"].lower()


def test_requirement_types_endpoint_needs_no_authentication(client):
    """Read-only, commits nothing -- an officer should see the catalog
    before logging in to start drafting, the same reasoning capabilities()
    already uses."""
    assert client.get("/requirement-types").status_code == 200


# --- rule pack dry-run validation ----------------------------------------------

def test_validate_endpoint_confirms_a_valid_pack_without_adopting(client, conn):
    r = client.post("/tenders/T1/rule-pack/validate", json={"pack": PACK}, headers=auth_headers(conn))
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["violations"] == []
    assert len(body["content_hash"]) == 64
    assert body["requirement_count"] == 3
    # Nothing was actually adopted: no RULE_PACK_ADOPTED event, no rule_packs row.
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM events WHERE event_type='RULE_PACK_ADOPTED'")
        assert cur.fetchone()[0] == 0
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM rule_packs")
        assert cur.fetchone()[0] == 0


def test_validate_endpoint_reports_the_same_violations_adopt_would(client, conn):
    bad = copy.deepcopy(PACK)
    bad["requirements"][2]["predicate"]["left"]["field"] = "bidder.astrology.sign"
    r = client.post("/tenders/T1/rule-pack/validate", json={"pack": bad}, headers=auth_headers(conn))
    body = r.json()
    assert body["valid"] is False
    assert any(v["rule"] == 8 for v in body["violations"])


def test_validate_endpoint_requires_authentication(client):
    client.headers.pop("Authorization", None)  # this one request must be anonymous
    r = client.post("/tenders/T1/rule-pack/validate", json={"pack": PACK})
    assert r.status_code == 401


def test_validate_endpoint_is_open_to_a_base_officer_not_just_senior(client, conn):
    """Checking a draft commits nothing -- the higher bar belongs on
    adoption alone (POST /tenders/{id}/rule-pack, already SENIOR_OFFICER+)."""
    from satyapramana_store.auth.models import Role
    r = client.post("/tenders/T1/rule-pack/validate", json={"pack": PACK},
                    headers=auth_headers(conn, username="junior", role=Role.OFFICER))
    assert r.status_code == 200
    assert r.json()["valid"] is True
