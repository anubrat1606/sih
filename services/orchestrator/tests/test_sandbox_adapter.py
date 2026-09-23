"""Live Sandbox.co.in adapters, exercised against their documented contract
shapes via httpx.MockTransport -- no network call, but no fabricated product
behaviour either: this mocks *our own test harness's* dependency on the
network, the same way the rest of the suite mocks nothing and just skips
without a real database. The adapter code itself makes a real HTTP call in
production; the response shape asserted here is the one in Sandbox's own
developer docs.
"""
from __future__ import annotations

import json

import httpx
import pytest

from satyapramana_store.adapters.base import (
    Basis, Failure, FailureCode, LawfulBasis, Success, VerificationRequest,
)
from satyapramana_store.adapters.sandbox_co_in import (
    CinStatusAdapter, GstReturnStatusAdapter, GstStatusAdapter, PanStatusAdapter,
    SandboxSession, build_from_env,
)

BASIS = LawfulBasis(Basis.TENDER_EVALUATION, "officer_1",
                    "Compliance evaluation for tender GEM-X")

AUTH_OK = httpx.Response(200, json={
    "code": 200, "timestamp": 1, "transaction_id": "t1",
    "data": {"access_token": "test-jwt"},
})


def session_with(handler) -> SandboxSession:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return SandboxSession("key", "secret", client=client)


# --- build_from_env -----------------------------------------------------------

def test_no_adapters_without_both_env_vars(monkeypatch):
    monkeypatch.delenv("SATYAPRAMANA_SANDBOX_API_KEY", raising=False)
    monkeypatch.delenv("SATYAPRAMANA_SANDBOX_API_SECRET", raising=False)
    assert build_from_env() == []


def test_four_live_adapters_once_both_are_set(monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_SANDBOX_API_KEY", "k")
    monkeypatch.setenv("SATYAPRAMANA_SANDBOX_API_SECRET", "s")
    adapters = build_from_env()
    assert {a.manifest.adapter_id for a in adapters} == {
        "pan_status", "gst_status", "gst_return_status", "mca_cin"}
    assert all(c.live for a in adapters for c in a.manifest.capabilities)


# --- PAN ------------------------------------------------------------------

def test_pan_verify_success():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/authenticate":
            return AUTH_OK
        assert request.url.path == "/kyc/pan/verify"
        assert request.headers["authorization"] == "test-jwt"
        body = json.loads(request.content)
        assert body["pan"] == "ABCDE1234A"
        # NORMALIZE guarantees the subject arrives as ISO-8601 -- Sandbox's
        # own documented contract is DD/MM/YYYY, and converting between the
        # two is this adapter's job, not upstream's (see _iso_to_ddmmyyyy).
        assert body["date_of_birth"] == "01/01/1990"
        return httpx.Response(200, json={
            "code": 200, "data": {
                "status": "valid", "category": "individual",
                "name_as_per_pan_match": True, "date_of_birth_match": True,
                "aadhaar_seeding_status": "y",
            },
        })

    adapter = PanStatusAdapter(session_with(handler))
    req = VerificationRequest("PAN_STATUS", {
        "pan_number": "ABCDE1234A", "pan_holder_name": "Test Bidder",
        "pan_date_of_birth": "1990-01-01",
    }, BASIS)
    outcome = adapter.verify(req)

    assert isinstance(outcome, Success)
    values = {o.path: o.value for o in outcome.observations}
    assert values == {"bidder.pan.status": "valid", "bidder.pan.holder_category": "individual"}
    assert outcome.raw_response_ref.startswith("unarchived:")


def test_pan_verify_a_non_iso_date_of_birth_is_refused_not_guessed():
    """Real bug, found live (see reporting on the NORMALIZE fix): if the
    resolved subject ever isn't the ISO-8601 shape NORMALIZE is supposed to
    guarantee, this adapter must refuse rather than send Sandbox.co.in a
    value that was never actually validated as a date."""
    adapter = PanStatusAdapter(session_with(lambda r: AUTH_OK))
    outcome = adapter.verify(VerificationRequest("PAN_STATUS", {
        "pan_number": "ABCDE1234A", "pan_holder_name": "Test Bidder",
        "pan_date_of_birth": "01/01/1990",  # the old, wrong-for-this-layer shape
    }, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED
    assert "ISO-8601" in outcome.detail


def test_pan_verify_missing_pan_number_never_calls_the_network():
    def handler(request):
        raise AssertionError("no HTTP call should happen without a PAN number")

    adapter = PanStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("PAN_STATUS", {}, BASIS))
    assert isinstance(outcome, Failure)
    assert outcome.code is FailureCode.MALFORMED
    assert "PAN number" in outcome.detail


def test_pan_verify_missing_name_or_dob_is_refused_not_guessed():
    adapter = PanStatusAdapter(session_with(lambda r: AUTH_OK))
    outcome = adapter.verify(VerificationRequest(
        "PAN_STATUS", {"pan_number": "ABCDE1234A"}, BASIS))
    assert isinstance(outcome, Failure)
    assert outcome.code is FailureCode.MALFORMED
    assert "date of birth" in outcome.detail


def test_pan_verify_unauthorized_maps_correctly():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(401, json={"code": 401, "message": "bad key"})

    adapter = PanStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("PAN_STATUS", {
        "pan_number": "ABCDE1234A", "pan_holder_name": "Test Bidder",
        "pan_date_of_birth": "1990-01-01",
    }, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.UNAUTHORIZED


def test_pan_verify_connection_error_is_unavailable_not_a_crash():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    adapter = PanStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("PAN_STATUS", {
        "pan_number": "ABCDE1234A", "pan_holder_name": "Test Bidder",
        "pan_date_of_birth": "1990-01-01",
    }, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.UNAVAILABLE


# --- GST --------------------------------------------------------------------

def test_gst_search_success():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        assert json.loads(request.content) == {"gstin": "33ABKCS2033B1ZW"}
        return httpx.Response(200, json={
            "code": 200, "data": {
                "data": {"gstin": "33ABKCS2033B1ZW", "lgnm": "Test Traders",
                          "sts": "Active", "rgdt": "01/01/2020"},
                "status_cd": "1",
            },
        })

    adapter = GstStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest(
        "GST_STATUS", {"gstin": "33ABKCS2033B1ZW"}, BASIS))

    assert isinstance(outcome, Success)
    values = {o.path: o.value for o in outcome.observations}
    assert values["bidder.gst.status"] == "Active"
    assert values["bidder.gst.legal_name"] == "Test Traders"


def test_gst_search_not_found():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(200, json={
            "code": 200,
            "data": {"error": {"error_cd": "FO8000", "message": "No records found"},
                      "status_cd": "0"},
        })

    adapter = GstStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest(
        "GST_STATUS", {"gstin": "33ABKCS2033B1ZW"}, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.NOT_FOUND


def test_gst_search_missing_gstin_never_calls_the_network():
    def handler(request):
        raise AssertionError("no HTTP call should happen without a GSTIN")

    adapter = GstStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("GST_STATUS", {}, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED


def test_gst_rate_limited_maps_correctly():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(429, text="slow down")

    adapter = GstStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest(
        "GST_STATUS", {"gstin": "33ABKCS2033B1ZW"}, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.RATE_LIMITED


# --- GST return status --------------------------------------------------------

def test_gst_return_status_picks_the_latest_period_not_list_order():
    """Real fixture, taken verbatim from Sandbox's own OpenAPI example for
    this endpoint -- the list isn't sorted by period, so this proves the
    adapter actually compares (year, month) rather than trusting order."""
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        assert request.url.params["financial_year"] == "FY 2020-21"
        assert "gstr" not in request.url.params
        assert json.loads(request.content) == {"gstin": "33ABKCS2033B1ZW"}
        return httpx.Response(200, json={
            "code": 200, "data": {
                "data": {"EFiledlist": [
                    {"arn": "AA330820000343Z", "dof": "01-02-2023", "mof": "GSP",
                     "ret_prd": "082020", "rtntype": "GSTR1", "status": "Filed", "valid": "Y"},
                    {"arn": "AA331120000360G", "dof": "05-02-2023", "mof": "GSP",
                     "ret_prd": "112020", "rtntype": "GSTR1", "status": "Filed", "valid": "Y"},
                    {"arn": "AA330920000445R", "dof": "01-02-2023", "mof": "GSP",
                     "ret_prd": "092020", "rtntype": "GSTR1", "status": "Filed", "valid": "Y"},
                ]},
                "status_cd": "1",
            },
        })

    adapter = GstReturnStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("GST_RETURN_STATUS", {
        "gstin": "33ABKCS2033B1ZW", "gst_return_financial_year": "FY 2020-21",
    }, BASIS))

    assert isinstance(outcome, Success)
    values = {o.path: o.value for o in outcome.observations}
    assert values["bidder.gst.latest_return_period"] == "112020"
    assert values["bidder.gst.latest_return_filed_date"] == "05-02-2023"
    assert values["bidder.gst.latest_return_status"] == "Filed"
    assert values["bidder.gst.latest_return_type"] == "GSTR1"


def test_gst_return_status_passes_the_optional_return_type_filter():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        assert request.url.params["gstr"] == "GSTR3B"
        return httpx.Response(200, json={
            "code": 200, "data": {
                "data": {"EFiledlist": [
                    {"arn": "A1", "dof": "01-02-2023", "mof": "GSP",
                     "ret_prd": "032021", "rtntype": "GSTR3B", "status": "Filed", "valid": "Y"},
                ]},
                "status_cd": "1",
            },
        })

    adapter = GstReturnStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("GST_RETURN_STATUS", {
        "gstin": "33ABKCS2033B1ZW", "gst_return_financial_year": "FY 2020-21",
        "gst_return_type": "GSTR3B",
    }, BASIS))
    assert isinstance(outcome, Success)


def test_gst_return_status_rtn22_is_our_own_malformed_request_not_a_finding():
    """RTN_22 means Sandbox rejected the financial_year we sent -- a bug in
    the request, never an authority fact about the bidder. Must not be
    confused with RET13510 (a real not-found)."""
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(200, json={
            "code": 200, "data": {
                "error": {"error_code": "RTN_22", "message": "Please select a valid financial year"},
                "status_cd": "0",
            },
        })

    adapter = GstReturnStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("GST_RETURN_STATUS", {
        "gstin": "3418FIN00001UNY", "gst_return_financial_year": "not a real FY",
    }, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED
    assert "financial year" in outcome.detail.lower()


def test_gst_return_status_ret13510_is_honestly_not_found():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(200, json={
            "code": 200, "data": {
                "error": {"error_code": "RET13510", "message": "No Record found for the provided Inputs"},
                "status_cd": "0",
            },
        })

    adapter = GstReturnStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("GST_RETURN_STATUS", {
        "gstin": "07CQZCD1111I4Z7", "gst_return_financial_year": "FY 2020-21",
    }, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.NOT_FOUND


def test_gst_return_status_unrecognised_error_code_is_ambiguous_not_guessed():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(200, json={
            "code": 200, "data": {
                "error": {"error_code": "SOMETHING_NEW", "message": "unexpected"},
                "status_cd": "0",
            },
        })

    adapter = GstReturnStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("GST_RETURN_STATUS", {
        "gstin": "33ABKCS2033B1ZW", "gst_return_financial_year": "FY 2020-21",
    }, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.AMBIGUOUS


def test_gst_return_status_invalid_gstin_pattern_is_the_documented_422():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(422, json={"code": 422, "message": "Invalid GSTIN pattern"})

    adapter = GstReturnStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("GST_RETURN_STATUS", {
        "gstin": "34ACXP00001E0Z0", "gst_return_financial_year": "FY 2020-21",
    }, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED


def test_gst_return_status_missing_gstin_never_calls_the_network():
    def handler(request):
        raise AssertionError("no HTTP call should happen without a GSTIN")

    adapter = GstReturnStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest(
        "GST_RETURN_STATUS", {"gst_return_financial_year": "FY 2020-21"}, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED


def test_gst_return_status_missing_financial_year_is_refused_not_defaulted():
    """No per-bidder source for financial_year exists in this deployment yet
    -- this must refuse honestly, never silently default to 'this year' and
    risk checking the wrong period."""
    def handler(request):
        raise AssertionError("no HTTP call should happen without a financial_year")

    adapter = GstReturnStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest(
        "GST_RETURN_STATUS", {"gstin": "33ABKCS2033B1ZW"}, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED
    assert "financial_year" in outcome.detail


# --- CIN --------------------------------------------------------------------

def test_cin_master_data_success():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        assert json.loads(request.content) == {"cin": "U74999DL2015PTC284875"}
        return httpx.Response(200, json={
            "code": 200, "data": [{
                "@entity": "in.co.sandbox.kyc.mca.company_master_data",
                "cin": "U74999DL2015PTC284875", "company_name": "Test Traders Pvt Ltd",
                "company_status": "Active", "company_registration_date": "01/01/2015",
            }],
        })

    adapter = CinStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest(
        "CIN_STATUS", {"cin": "U74999DL2015PTC284875"}, BASIS))

    assert isinstance(outcome, Success)
    values = {o.path: o.value for o in outcome.observations}
    assert values["bidder.entity.legal_name_canonical"] == "Test Traders Pvt Ltd"
    assert values["bidder.entity.status"] == "Active"
    assert "bidder.entity.directors" not in values, (
        "Sandbox's director lookup is discontinued -- never claim to provide it")


def test_cin_not_found_uses_the_documented_521():
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(521, text="Company master data not found for CIN: X")

    adapter = CinStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("CIN_STATUS", {"cin": "X"}, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.NOT_FOUND


def test_cin_missing_is_refused_not_guessed():
    def handler(request):
        raise AssertionError("no HTTP call should happen without a CIN")

    adapter = CinStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest("CIN_STATUS", {}, BASIS))
    assert isinstance(outcome, Failure) and outcome.code is FailureCode.MALFORMED


# --- archiving, with a real database -----------------------------------------

def test_credentials_are_never_archived(conn):
    def handler(request):
        if request.url.path == "/authenticate":
            return AUTH_OK
        return httpx.Response(200, json={
            "code": 200, "data": {"data": {"sts": "Active", "lgnm": "Test Traders"},
                                   "status_cd": "1"},
        })

    adapter = GstStatusAdapter(session_with(handler))
    outcome = adapter.verify(VerificationRequest(
        "GST_STATUS", {"gstin": "33ABKCS2033B1ZW"}, BASIS), conn)

    assert isinstance(outcome, Success)
    with conn.cursor() as cur:
        cur.execute("SELECT request_headers::text, response_body FROM raw_responses "
                    "WHERE content_sha256=%s", (outcome.raw_response_ref,))
        headers_text, response_body = cur.fetchone()
    assert "test-jwt" not in headers_text
    assert "[REDACTED]" in headers_text
    assert "Active" in response_body, "the real response is still stored verbatim"
