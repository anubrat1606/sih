"""DigiLocker consent-flow integration (round 10, PS26100 point 8).

Same testing stance as test_sandbox_adapter.py: httpx.MockTransport mocks
our own test harness's dependency on the network, never product behaviour.
Response shapes asserted here come from Sandbox's own published OpenAPI
spec (developer.sandbox.co.in/api-reference/kyc/digilocker/endpoints/),
not guessed.
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest

from satyapramana_store.adapters import Registry
from satyapramana_store.adapters.base import (
    Basis, Failure, FailureCode, LawfulBasis, VerificationRequest,
)
from satyapramana_store.adapters.digilocker import (
    DIGILOCKER_CAPABILITY, DigilockerPlaceholderAdapter, FetchedDocument,
    InitiateResult, SessionStatus, build_from_env, check_session_status,
    fetch_document, initiate_session,
)
from satyapramana_store.adapters.sandbox_co_in import SandboxSession
from satyapramana_store.events import Actor, append
from satyapramana_store.evidence import rebuild_evidence

BASIS = LawfulBasis(Basis.TENDER_EVALUATION, "officer_1", "Compliance evaluation for tender GEM-X")
CONSENT_BASIS = LawfulBasis(Basis.BIDDER_CONSENT, "officer_1", "Document retrieval",
                            consent_reference="sess-1")

AUTH_OK = httpx.Response(200, json={
    "code": 200, "timestamp": 1, "transaction_id": "t1",
    "data": {"access_token": "test-jwt"},
})


def session_with(handler) -> SandboxSession:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SandboxSession("key", "secret", client=client)


# --- build_from_env -------------------------------------------------------------

def test_no_session_without_both_env_vars(monkeypatch):
    monkeypatch.delenv("SATYAPRAMANA_SANDBOX_API_KEY", raising=False)
    monkeypatch.delenv("SATYAPRAMANA_SANDBOX_API_SECRET", raising=False)
    assert build_from_env() is None


def test_a_real_session_once_both_are_set(monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_SANDBOX_API_KEY", "k")
    monkeypatch.setenv("SATYAPRAMANA_SANDBOX_API_SECRET", "s")
    session = build_from_env()
    assert isinstance(session, SandboxSession)


# --- initiate_session -------------------------------------------------------------

def test_initiate_session_success():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/authenticate":
            return AUTH_OK
        assert request.url.path == "/kyc/digilocker/sessions/init"
        body = json.loads(request.content)
        assert body == {
            "@entity": "in.co.sandbox.kyc.digilocker.session.request",
            "flow": "signin", "redirect_url": "https://frontend.example/callback",
            "doc_types": ["aadhaar"],
        }
        return httpx.Response(200, json={
            "code": 200, "data": {
                "@entity": "in.co.sandbox.kyc.digilocker.session.response",
                "authorization_url": "https://digilocker.meripehchaan.gov.in/authorize?x=1",
                "session_id": "sess-1",
            },
        })

    outcome = initiate_session(
        session_with(handler), redirect_url="https://frontend.example/callback",
        doc_types=("aadhaar",), lawful_basis=BASIS)
    assert isinstance(outcome, InitiateResult)
    assert outcome.session_id == "sess-1"
    assert outcome.authorization_url.startswith("https://digilocker.meripehchaan.gov.in")


def test_initiate_session_refuses_a_non_https_redirect_never_calls_the_network():
    def handler(request):
        raise AssertionError("no HTTP call should happen with a non-https redirect_url")

    outcome = initiate_session(
        session_with(handler), redirect_url="http://insecure.example/callback",
        doc_types=("aadhaar",), lawful_basis=BASIS)
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED


def test_initiate_session_refuses_an_unsupported_doc_type():
    outcome = initiate_session(
        session_with(lambda r: AUTH_OK), redirect_url="https://frontend.example/callback",
        doc_types=("passport",), lawful_basis=BASIS)
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED


def test_initiate_session_400_is_malformed():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(400, json={"code": 400, "message": "Invalid redirect_url"})

    outcome = initiate_session(
        session_with(handler), redirect_url="https://frontend.example/callback",
        doc_types=("aadhaar",), lawful_basis=BASIS)
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED


# --- check_session_status -------------------------------------------------------------

def test_session_status_created():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        assert request.url.path == "/kyc/digilocker/sessions/sess-1/status"
        return httpx.Response(200, json={
            "code": 200, "data": {
                "id": "sess-1", "created_at": 1, "@entity": "in.co.sandbox.kyc.digilocker.session",
                "status": "created",
            },
        })

    outcome = check_session_status(session_with(handler), "sess-1", lawful_basis=BASIS)
    assert isinstance(outcome, SessionStatus)
    assert outcome.status == "created"
    assert outcome.documents_consented == ()


def test_session_status_succeeded_lists_consented_documents():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(200, json={
            "code": 200, "data": {
                "id": "sess-1", "created_at": 1, "updated_at": 2,
                "@entity": "in.co.sandbox.kyc.digilocker.session",
                "status": "succeeded", "documents_consented": ["aadhaar"],
            },
        })

    outcome = check_session_status(session_with(handler), "sess-1", lawful_basis=BASIS)
    assert outcome.status == "succeeded"
    assert outcome.documents_consented == ("aadhaar",)


def test_session_status_unknown_session_id_is_not_found():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(521, json={"code": 521, "message": "Data not found for: sess-1"})

    outcome = check_session_status(session_with(handler), "sess-1", lawful_basis=BASIS)
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.NOT_FOUND


def test_session_status_archives_as_a_real_get_not_a_guessed_post(conn):
    """The bug this module's own change to sandbox_co_in.py's _record()
    exists to prevent: a GET request archived with method="POST" would be
    a false record of what actually happened."""
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(200, json={
            "code": 200, "data": {
                "id": "sess-1", "created_at": 1, "@entity": "x", "status": "created",
            },
        })

    check_session_status(session_with(handler), "sess-1", lawful_basis=BASIS, conn=conn)
    with conn.cursor() as cur:
        cur.execute("SELECT request_method FROM raw_responses WHERE capability_id='DIGILOCKER_DOCUMENT' "
                    "ORDER BY observed_at DESC LIMIT 1")
        (method,) = cur.fetchone()
    assert method == "GET"


# --- fetch_document -------------------------------------------------------------

def test_fetch_document_success():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        assert request.url.path == "/kyc/digilocker/sessions/sess-1/documents/aadhaar"
        return httpx.Response(200, json={
            "code": 200, "data": {"files": [{
                "@entity": "org.quicko.drive.file",
                "url": "https://s3.example/presigned", "size": 16598,
                "metadata": {"ContentType": "application/xml", "issuer_id": "in.gov.uidai",
                             "issuer": "Unique Identification Authority of India (UIDAI)",
                             "LastModified": "09/05/2025", "description": "Aadhaar Card"},
            }]},
        })

    outcome = fetch_document(session_with(handler), "sess-1", "aadhaar", lawful_basis=CONSENT_BASIS)
    assert isinstance(outcome, FetchedDocument)
    assert outcome.files[0]["metadata"]["issuer"] == "Unique Identification Authority of India (UIDAI)"


def test_fetch_document_no_consent_given_is_malformed():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(400, json={"code": 400, "message": "Consent for aadhaar not provided"})

    outcome = fetch_document(session_with(handler), "sess-1", "aadhaar", lawful_basis=CONSENT_BASIS)
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED


def test_fetch_document_not_found():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(404, json={"code": 404, "message": "Doctype not found"})

    outcome = fetch_document(session_with(handler), "sess-1", "aadhaar", lawful_basis=CONSENT_BASIS)
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.NOT_FOUND


def test_fetch_document_session_not_usable_yet_is_unavailable_not_a_guess():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(523, json={"code": 523, "message": "Invalid session status: created"})

    outcome = fetch_document(session_with(handler), "sess-1", "aadhaar", lawful_basis=CONSENT_BASIS)
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.UNAVAILABLE


def test_fetch_document_refuses_an_unsupported_doc_type_never_calls_the_network():
    def handler(request):
        raise AssertionError("no HTTP call should happen with an unsupported doc_type")

    outcome = fetch_document(session_with(handler), "sess-1", "passport", lawful_basis=CONSENT_BASIS)
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED


# --- parsing the real Aadhaar XML, and the PAN identity cross-check ------------------------

from satyapramana_store.adapters.digilocker import (  # noqa: E402
    AadhaarIdentity, download_document_file, names_match, parse_aadhaar_xml,
)

# The exact structure documented in Sandbox's own sample-responses page
# (developer.sandbox.co.in/api-reference/kyc/digilocker/sample-responses),
# not guessed -- Poa/LData/Pht included the same way a real response would,
# so the test proves parse_aadhaar_xml actually ignores them, not just that
# it works on an artificially minimal document.
REAL_AADHAAR_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Certificate>
  <CertificateData>
    <KycRes code="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" ret="Y"
            ts="2026-01-15T12:00:00.000+05:30" ttl="2027-01-15T12:00:00"
            txn="UKC:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx">
      <UidData tkn="" uid="xxxxxxxx1234">
        <Poi dob="01-01-1990" gender="M" name="SAMPLE NAME"/>
        <Poa co="C/O SAMPLE GUARDIAN" country="India" dist="Sample District"
             house="A 101, Sample Apartment" lm="Nr Sample Landmark"
             loc="Sample Locality" pc="380001" po="Sample Post Office"
             state="Gujarat" subdist="Sample Sub-District" vtc="Sample City"/>
        <Pht><!-- Base64-encoded JPEG photo --></Pht>
      </UidData>
    </KycRes>
  </CertificateData>
  <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
    <!-- Digital signature issued by Digital India Corporation -->
  </Signature>
</Certificate>"""


def test_parse_aadhaar_xml_reads_name_and_dob():
    identity = parse_aadhaar_xml(REAL_AADHAAR_XML)
    assert identity == AadhaarIdentity(name="SAMPLE NAME", dob_iso="1990-01-01")


def test_parse_aadhaar_xml_never_reads_address_or_photo():
    """The point of the PII-minimisation stance in this module's docstring
    -- prove it, not just claim it: nothing this function returns can leak
    the address or photo, because the return type has no field for either."""
    identity = parse_aadhaar_xml(REAL_AADHAAR_XML)
    assert set(identity.__dataclass_fields__) == {"name", "dob_iso"}


def test_parse_aadhaar_xml_malformed_document_is_none_not_a_guess():
    assert parse_aadhaar_xml(b"not xml at all") is None


def test_parse_aadhaar_xml_wrong_document_shape_is_none():
    assert parse_aadhaar_xml(b"<Certificate><Other/></Certificate>") is None


def test_names_match_tolerates_case_and_whitespace_not_substance():
    assert names_match("Sample Name", "  SAMPLE   NAME ")
    assert not names_match("Sample Name", "Sample K Name")


def test_download_document_file_is_a_plain_get_no_sandbox_auth(monkeypatch):
    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        return httpx.Response(200, content=b"<xml/>", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    content = download_document_file("https://s3.example/presigned?sig=abc")
    assert content == b"<xml/>"
    assert calls == ["https://s3.example/presigned?sig=abc"]


# --- the placeholder adapter -------------------------------------------------------------

def test_placeholder_adapter_refuses_the_generic_verify_loop():
    adapter = DigilockerPlaceholderAdapter()
    outcome = adapter.verify(VerificationRequest("DIGILOCKER_DOCUMENT", {}, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.NOT_CAPABLE
    assert "digilocker/session" in outcome.detail


def test_placeholder_manifest_matches_the_shared_capability_object():
    adapter = DigilockerPlaceholderAdapter()
    assert adapter.manifest.capabilities == (DIGILOCKER_CAPABILITY,)


# --- the real API endpoints -------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from satyapramana_store import app as _app_module  # noqa: E402
from satyapramana_store.app import app, db  # noqa: E402
from satyapramana_store.auth.models import Role  # noqa: E402
from satyapramana_store.evidence import ProjectionResolver  # noqa: E402

from .conftest import auth_headers  # noqa: E402


@pytest.fixture()
def client(conn):
    app.dependency_overrides[db] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_digilocker_session_endpoint_503s_when_unconfigured(client, conn, monkeypatch):
    monkeypatch.setattr(_app_module, "DIGILOCKER_SESSION", None)
    client.post("/tenders/T-DL/bidders", json={"bidder_id": "A"}, headers=auth_headers(conn))
    r = client.post("/bidders/A/digilocker/session?tender_id=T-DL",
                    json={"redirect_url": "https://frontend.example/callback"},
                    headers=auth_headers(conn))
    assert r.status_code == 503


def test_digilocker_session_endpoint_requires_officer_or_self(client, conn, monkeypatch):
    monkeypatch.setattr(_app_module, "DIGILOCKER_SESSION",
                        session_with(lambda r: AUTH_OK))
    client.post("/tenders/T-DL/bidders", json={"bidder_id": "A"}, headers=auth_headers(conn))
    r = client.post("/bidders/A/digilocker/session?tender_id=T-DL",
                    json={"redirect_url": "https://frontend.example/callback"},
                    headers=auth_headers(conn, username="stranger", role=Role.BIDDER))
    assert r.status_code == 403


def test_digilocker_session_endpoint_returns_a_real_authorization_url(client, conn, monkeypatch):
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(200, json={
            "code": 200, "data": {
                "@entity": "x", "authorization_url": "https://digilocker.meripehchaan.gov.in/authorize?x=1",
                "session_id": "sess-1",
            },
        })
    monkeypatch.setattr(_app_module, "DIGILOCKER_SESSION", session_with(handler))
    client.post("/tenders/T-DL/bidders", json={"bidder_id": "A"}, headers=auth_headers(conn))
    r = client.post("/bidders/A/digilocker/session?tender_id=T-DL",
                    json={"redirect_url": "https://frontend.example/callback"},
                    headers=auth_headers(conn))
    assert r.status_code == 201
    body = r.json()
    assert body["session_id"] == "sess-1"
    assert body["authorization_url"].startswith("https://digilocker.meripehchaan.gov.in")


def test_digilocker_status_endpoint_created_records_no_event(client, conn, monkeypatch):
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(200, json={
            "code": 200, "data": {"id": "sess-1", "created_at": 1, "@entity": "x", "status": "created"},
        })
    monkeypatch.setattr(_app_module, "DIGILOCKER_SESSION", session_with(handler))
    client.post("/tenders/T-DL/bidders", json={"bidder_id": "A"}, headers=auth_headers(conn))
    r = client.get("/bidders/A/digilocker/status?tender_id=T-DL&session_id=sess-1",
                   headers=auth_headers(conn))
    assert r.status_code == 200 and r.json() == {"status": "created"}
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM events WHERE tender_id='T-DL' AND bidder_id='A' "
                    "AND event_type LIKE 'VERIFICATION_%'")
        assert cur.fetchone()[0] == 0


def test_digilocker_status_endpoint_succeeded_fetches_and_records_a_real_observation(client, conn, monkeypatch):
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={
                "code": 200, "data": {"id": "sess-1", "created_at": 1, "@entity": "x",
                                       "status": "succeeded", "documents_consented": ["aadhaar"]},
            })
        return httpx.Response(200, json={
            "code": 200, "data": {"files": [{
                "@entity": "x", "url": "https://s3.example/presigned", "size": 100,
                "metadata": {"ContentType": "application/xml", "issuer_id": "in.gov.uidai",
                             "issuer": "Unique Identification Authority of India (UIDAI)",
                             "LastModified": "09/05/2025", "description": "Aadhaar Card"},
            }]},
        })
    monkeypatch.setattr(_app_module, "DIGILOCKER_SESSION", session_with(handler))
    client.post("/tenders/T-DL/bidders", json={"bidder_id": "A"}, headers=auth_headers(conn))
    r = client.get("/bidders/A/digilocker/status?tender_id=T-DL&session_id=sess-1",
                   headers=auth_headers(conn))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "succeeded" and body["document_fetch"] == "ok"
    assert body["issuer"] == "Unique Identification Authority of India (UIDAI)"

    resolver = ProjectionResolver(conn, "A")
    resolved = resolver.field("bidder.digilocker.aadhaar_verified")
    assert resolved.ok and resolved.value == "VERIFIED"


def _digilocker_status_handler(xml_bytes):
    """Shared plumbing for the identity-match tests below: mocks both the
    Sandbox session (status + fetch_document) and the plain httpx.get that
    downloads the pre-signed S3 file -- two different HTTP clients, real in
    production, both need mocking here."""
    def sandbox_handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={
                "code": 200, "data": {"id": "sess-1", "created_at": 1, "@entity": "x",
                                       "status": "succeeded", "documents_consented": ["aadhaar"]},
            })
        return httpx.Response(200, json={
            "code": 200, "data": {"files": [{
                "@entity": "x", "url": "https://s3.example/presigned", "size": 100,
                "metadata": {"ContentType": "application/xml", "issuer_id": "in.gov.uidai",
                             "issuer": "Unique Identification Authority of India (UIDAI)",
                             "LastModified": "09/05/2025", "description": "Aadhaar Card"},
            }]},
        })

    def fake_get(url, timeout=None):
        return httpx.Response(200, content=xml_bytes, request=httpx.Request("GET", url))

    return sandbox_handler, fake_get


def _set_pan_holder_name(conn, bidder_id, name):
    """Same real mechanism deterministic extraction itself uses -- a real
    FIELD_EXTRACTED event, folded into proj_evidence via rebuild_evidence
    -- never a hand-crafted row against a guessed table shape."""
    append(conn, event_type="FIELD_EXTRACTED", actor=Actor("SYSTEM", "extract-deterministic@1.0.0"),
          correlation_id=str(uuid.uuid4()), tender_id="T-DL", bidder_id=bidder_id,
          payload={"path": "bidder.pan.holder_name", "value": name,
                   "page": 1, "region": [0, 0, 1, 1], "confidence": 1.0})
    rebuild_evidence(conn, bidder_id, Registry())


def test_digilocker_status_endpoint_pan_name_matches(client, conn, monkeypatch):
    sandbox_handler, fake_get = _digilocker_status_handler(REAL_AADHAAR_XML)  # holder "SAMPLE NAME"
    monkeypatch.setattr(_app_module, "DIGILOCKER_SESSION", session_with(sandbox_handler))
    monkeypatch.setattr(httpx, "get", fake_get)
    client.post("/tenders/T-DL/bidders", json={"bidder_id": "A"}, headers=auth_headers(conn))

    # A real PAN already on file for this bidder, same name (case/whitespace
    # differences only -- the same tolerance names_match itself proves).
    _set_pan_holder_name(conn, "A", "sample   name")

    r = client.get("/bidders/A/digilocker/status?tender_id=T-DL&session_id=sess-1",
                   headers=auth_headers(conn))
    assert r.status_code == 200
    assert r.json()["pan_identity_match"] == "MATCH"

    resolver = ProjectionResolver(conn, "A")
    resolved = resolver.field("bidder.digilocker.pan_identity_match")
    assert resolved.ok and resolved.value == "MATCH"
    assert resolver.field("bidder.digilocker.aadhaar_name").value == "SAMPLE NAME"
    assert resolver.field("bidder.digilocker.aadhaar_dob").value == "1990-01-01"


def test_digilocker_status_endpoint_pan_name_mismatches_is_reported_honestly(client, conn, monkeypatch):
    sandbox_handler, fake_get = _digilocker_status_handler(REAL_AADHAAR_XML)  # holder "SAMPLE NAME"
    monkeypatch.setattr(_app_module, "DIGILOCKER_SESSION", session_with(sandbox_handler))
    monkeypatch.setattr(httpx, "get", fake_get)
    client.post("/tenders/T-DL/bidders", json={"bidder_id": "A"}, headers=auth_headers(conn))
    _set_pan_holder_name(conn, "A", "a completely different person")

    r = client.get("/bidders/A/digilocker/status?tender_id=T-DL&session_id=sess-1",
                   headers=auth_headers(conn))
    assert r.json()["pan_identity_match"] == "MISMATCH"


def test_digilocker_status_endpoint_no_pan_on_file_reports_no_match_field(client, conn, monkeypatch):
    """Nothing to compare against yet -- an honest absence, not a guessed
    MATCH or a fabricated MISMATCH."""
    sandbox_handler, fake_get = _digilocker_status_handler(REAL_AADHAAR_XML)
    monkeypatch.setattr(_app_module, "DIGILOCKER_SESSION", session_with(sandbox_handler))
    monkeypatch.setattr(httpx, "get", fake_get)
    client.post("/tenders/T-DL/bidders", json={"bidder_id": "A"}, headers=auth_headers(conn))

    r = client.get("/bidders/A/digilocker/status?tender_id=T-DL&session_id=sess-1",
                   headers=auth_headers(conn))
    assert r.json()["pan_identity_match"] is None
    resolver = ProjectionResolver(conn, "A")
    assert not resolver.field("bidder.digilocker.pan_identity_match").ok


def test_digilocker_status_endpoint_failed_records_verification_failed(client, conn, monkeypatch):
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(200, json={
            "code": 200, "data": {"id": "sess-1", "created_at": 1, "@entity": "x", "status": "failed"},
        })
    monkeypatch.setattr(_app_module, "DIGILOCKER_SESSION", session_with(handler))
    client.post("/tenders/T-DL/bidders", json={"bidder_id": "A"}, headers=auth_headers(conn))
    r = client.get("/bidders/A/digilocker/status?tender_id=T-DL&session_id=sess-1",
                   headers=auth_headers(conn))
    assert r.status_code == 200
    assert r.json() == {"status": "failed", "verdict": "UNKNOWN"}
    with conn.cursor() as cur:
        cur.execute("SELECT event_type FROM events WHERE tender_id='T-DL' AND bidder_id='A' "
                    "AND event_type LIKE 'VERIFICATION_%' ORDER BY seq")
        rows = [r[0] for r in cur.fetchall()]
    assert rows == ["VERIFICATION_REQUESTED", "VERIFICATION_FAILED"]
