"""DigiLocker consent-flow integration (round 10, PS26100 point 8).

Same testing stance as test_sandbox_adapter.py: httpx.MockTransport mocks
our own test harness's dependency on the network, never product behaviour.
Response shapes asserted here come from Sandbox's own published OpenAPI
spec (developer.sandbox.co.in/api-reference/kyc/digilocker/endpoints/),
not guessed.
"""
from __future__ import annotations

import json

import httpx
import pytest

from satyapramana_store.adapters.base import (
    Basis, Failure, FailureCode, LawfulBasis, VerificationRequest,
)
from satyapramana_store.adapters.digilocker import (
    DIGILOCKER_CAPABILITY, DigilockerPlaceholderAdapter, FetchedDocument,
    InitiateResult, SessionStatus, build_from_env, check_session_status,
    fetch_document, initiate_session,
)
from satyapramana_store.adapters.sandbox_co_in import SandboxSession

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
