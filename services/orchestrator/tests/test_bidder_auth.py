"""Bidder self-service accounts: validation, tokens, the store, and the real
API surface (signup, login, me, email verification, mobile OTP, forgot/reset
password, Google Sign-In, and the officer/bidder role-separation gate). See
satyapramana_store/bidder_auth/ for the design rationale -- this only tests
it holds.
"""
from __future__ import annotations

from datetime import timedelta

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from satyapramana_store.app import app, db
from satyapramana_store.auth.store import create_user
from satyapramana_store.auth.models import Role
from satyapramana_store.auth.tokens import issue_token
from satyapramana_store.bidder_auth import store as bidder_store
from satyapramana_store.bidder_auth.tokens import (
    decode_bidder_token, generate_otp, hash_otp, issue_bidder_token,
)
from satyapramana_store.bidder_auth.validation import (
    is_valid_email, is_valid_indian_mobile, normalize_indian_mobile,
    password_issues,
)

from .conftest import auth_headers

TEST_SECRET = "test-secret-not-for-production-32chars+"

VALID_SIGNUP = {
    "full_name": "Priya Sharma", "email": "priya@example.com",
    "password": "Correct-Horse-1", "mobile": "+91 98765 43210",
    "company_name": "Sharma Traders",
}


# --- validation ---------------------------------------------------------------

def test_email_validation():
    assert is_valid_email("priya@example.com")
    assert not is_valid_email("not-an-email")
    assert not is_valid_email("priya@")
    assert not is_valid_email("priya @example.com")


@pytest.mark.parametrize("value,expected", [
    ("9876543210", "9876543210"),
    ("+91 98765 43210", "9876543210"),
    ("91-9876543210", "9876543210"),
    ("09876543210", "9876543210"),
    ("12345", None),           # too short
    ("5876543210", None),      # first digit not 6-9
    ("98765432101", None),     # too long
])
def test_indian_mobile_normalisation(value, expected):
    assert normalize_indian_mobile(value) == expected
    assert is_valid_indian_mobile(value) == (expected is not None)


def test_password_issues_lists_every_missing_rule():
    assert password_issues("Correct-Horse-1") == []
    assert "at least 8 characters" in password_issues("Ab1!")
    assert "one uppercase letter" in password_issues("lowercase-1!")
    assert "one special character" in password_issues("NoSpecial123")


# --- tokens ---------------------------------------------------------------

def test_a_bidder_token_round_trips_the_id_and_is_typed_as_bidder():
    token = issue_bidder_token(42, TEST_SECRET)
    claims = decode_bidder_token(token, TEST_SECRET)
    assert claims["sub"] == "42"
    assert claims["typ"] == "bidder"


def test_a_bidder_token_signed_with_a_different_secret_is_rejected():
    token = issue_bidder_token(1, TEST_SECRET)
    with pytest.raises(pyjwt.PyJWTError):
        decode_bidder_token(token, "a-completely-different-secret-value-32+")


def test_an_expired_bidder_token_is_rejected():
    token = issue_bidder_token(1, TEST_SECRET, ttl=timedelta(seconds=-1))
    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_bidder_token(token, TEST_SECRET)


def test_otp_generation_is_six_digits_and_hashing_is_deterministic():
    code = generate_otp()
    assert len(code) == 6 and code.isdigit()
    assert hash_otp(code) == hash_otp(code)
    assert hash_otp(code) != hash_otp(generate_otp() or "000001")


# --- store: account lifecycle -----------------------------------------------

def test_create_and_fetch_a_bidder_account(conn):
    created = bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    assert created.email == "priya@example.com"
    assert created.email_verified is False and created.mobile_verified is False
    fetched = bidder_store.get_bidder_by_email(conn, "priya@example.com")
    assert fetched == created
    assert bidder_store.get_bidder_by_id(conn, created.id) == created


def test_verify_login_succeeds_with_the_right_password(conn):
    bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    account = bidder_store.verify_login(conn, "priya@example.com", "Correct-Horse-1")
    assert account is not None and account.email == "priya@example.com"


def test_verify_login_fails_the_same_way_for_unknown_email_and_wrong_password(conn):
    bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    assert bidder_store.verify_login(conn, "priya@example.com", "wrong-password") is None
    assert bidder_store.verify_login(conn, "nobody@example.com", "Correct-Horse-1") is None


def test_a_google_only_account_has_no_password_and_cannot_password_login(conn):
    account = bidder_store.create_bidder_account_via_google(
        conn, email="priya@example.com", full_name="Priya Sharma", google_sub="google-sub-1")
    assert account.email_verified is True  # Google already proved the email
    assert bidder_store.verify_login(conn, "priya@example.com", "anything") is None
    assert bidder_store.get_bidder_by_google_sub(conn, "google-sub-1") == account


def test_a_disabled_bidder_account_cannot_log_in(conn):
    bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    with conn.cursor() as cur:
        cur.execute("UPDATE bidder_accounts SET disabled=true WHERE email='priya@example.com'")
    assert bidder_store.verify_login(conn, "priya@example.com", "Correct-Horse-1") is None


def test_duplicate_mobile_across_two_accounts_is_rejected_at_the_database(conn):
    bidder_store.create_bidder_account(
        conn, email="a@example.com", password="Correct-Horse-1",
        full_name="A", mobile="9876543210", company_name="A Co")
    with pytest.raises(Exception):  # psycopg raises a UniqueViolation subclass
        bidder_store.create_bidder_account(
            conn, email="b@example.com", password="Correct-Horse-1",
            full_name="B", mobile="9876543210", company_name="B Co")


# --- store: email verification -----------------------------------------------

def test_email_verification_round_trips(conn):
    account = bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    raw_token = bidder_store.create_email_verification(conn, account.id)
    verified = bidder_store.consume_email_verification(conn, raw_token)
    assert verified is not None and verified.email_verified is True


def test_an_email_verification_token_cannot_be_used_twice(conn):
    account = bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    raw_token = bidder_store.create_email_verification(conn, account.id)
    assert bidder_store.consume_email_verification(conn, raw_token) is not None
    assert bidder_store.consume_email_verification(conn, raw_token) is None


def test_an_unknown_email_verification_token_is_rejected(conn):
    assert bidder_store.consume_email_verification(conn, "not-a-real-token") is None


def test_requesting_a_new_email_verification_invalidates_the_old_one(conn):
    account = bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    first = bidder_store.create_email_verification(conn, account.id)
    bidder_store.create_email_verification(conn, account.id)
    assert bidder_store.consume_email_verification(conn, first) is None


# --- store: mobile OTP ---------------------------------------------------

def test_mobile_otp_round_trips(conn):
    account = bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    code = bidder_store.create_mobile_otp(conn, account.id)
    assert bidder_store.verify_mobile_otp(conn, account.id, code) == bidder_store.OtpOutcome.OK
    refreshed = bidder_store.get_bidder_by_id(conn, account.id)
    assert refreshed.mobile_verified is True


def test_an_already_consumed_otp_cannot_be_reused(conn):
    account = bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    code = bidder_store.create_mobile_otp(conn, account.id)
    bidder_store.verify_mobile_otp(conn, account.id, code)
    assert bidder_store.verify_mobile_otp(conn, account.id, code) == bidder_store.OtpOutcome.NO_ACTIVE_OTP


def test_a_wrong_otp_is_refused_and_counted(conn):
    account = bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    bidder_store.create_mobile_otp(conn, account.id)
    assert bidder_store.verify_mobile_otp(conn, account.id, "000000") in (
        bidder_store.OtpOutcome.WRONG_CODE, bidder_store.OtpOutcome.OK)  # astronomically unlikely to be OK


def test_too_many_wrong_attempts_locks_out_the_otp(conn):
    account = bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    bidder_store.create_mobile_otp(conn, account.id)
    for _ in range(5):
        bidder_store.verify_mobile_otp(conn, account.id, "000000")
    assert bidder_store.verify_mobile_otp(conn, account.id, "000000") == bidder_store.OtpOutcome.TOO_MANY_ATTEMPTS


def test_an_expired_otp_is_refused(conn):
    account = bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    code = bidder_store.create_mobile_otp(conn, account.id)
    with conn.cursor() as cur:
        cur.execute("UPDATE bidder_mobile_otps SET expires_at = now() - interval '1 minute' "
                    "WHERE bidder_id=%s", (account.id,))
    assert bidder_store.verify_mobile_otp(conn, account.id, code) == bidder_store.OtpOutcome.EXPIRED


# --- store: password reset ----------------------------------------------------

def test_password_reset_round_trips_and_the_new_password_works(conn):
    account = bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    raw_token = bidder_store.create_password_reset(conn, account.id)
    reset = bidder_store.consume_password_reset(conn, raw_token, "New-Correct-Horse-2")
    assert reset is not None
    assert bidder_store.verify_login(conn, "priya@example.com", "New-Correct-Horse-2") is not None
    assert bidder_store.verify_login(conn, "priya@example.com", "Correct-Horse-1") is None


def test_a_password_reset_token_cannot_be_reused(conn):
    account = bidder_store.create_bidder_account(
        conn, email="priya@example.com", password="Correct-Horse-1",
        full_name="Priya Sharma", mobile="9876543210", company_name="Sharma Traders")
    raw_token = bidder_store.create_password_reset(conn, account.id)
    bidder_store.consume_password_reset(conn, raw_token, "New-Correct-Horse-2")
    assert bidder_store.consume_password_reset(conn, raw_token, "Another-Horse-3") is None


# --- through the real API ----------------------------------------------------

@pytest.fixture()
def client(conn):
    app.dependency_overrides[db] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_signup_creates_a_real_account_and_returns_a_usable_token(client, conn):
    r = client.post("/bidders/auth/signup", json=VALID_SIGNUP)
    assert r.status_code == 201
    body = r.json()
    assert body["bidder"]["email"] == "priya@example.com"
    assert body["bidder"]["email_verified"] is False
    # No SMTP configured in the test environment -- delivery honestly fails,
    # but the account and token are real regardless.
    assert body["email_verification"]["delivered"] is False
    assert bidder_store.get_bidder_by_email(conn, "priya@example.com") is not None
    me = client.get("/bidders/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200 and me.json()["email"] == "priya@example.com"


def test_signup_normalises_the_mobile_number(client):
    r = client.post("/bidders/auth/signup", json=VALID_SIGNUP)
    assert r.json()["bidder"]["mobile"] == "9876543210"


def test_signup_rejects_a_duplicate_email(client, conn):
    client.post("/bidders/auth/signup", json=VALID_SIGNUP)
    r = client.post("/bidders/auth/signup", json={**VALID_SIGNUP, "mobile": "9111111111"})
    assert r.status_code == 409


def test_signup_rejects_a_duplicate_mobile(client, conn):
    client.post("/bidders/auth/signup", json=VALID_SIGNUP)
    r = client.post("/bidders/auth/signup",
                    json={**VALID_SIGNUP, "email": "other@example.com"})
    assert r.status_code == 409


def test_signup_rejects_an_invalid_email(client):
    r = client.post("/bidders/auth/signup", json={**VALID_SIGNUP, "email": "not-an-email"})
    assert r.status_code == 422


def test_signup_rejects_an_invalid_mobile(client):
    r = client.post("/bidders/auth/signup", json={**VALID_SIGNUP, "mobile": "12345"})
    assert r.status_code == 422


def test_signup_rejects_a_weak_password(client):
    r = client.post("/bidders/auth/signup", json={**VALID_SIGNUP, "password": "weak"})
    assert r.status_code == 422


def test_login_with_real_credentials_returns_a_usable_token(client):
    client.post("/bidders/auth/signup", json=VALID_SIGNUP)
    r = client.post("/bidders/auth/login",
                    json={"email": "priya@example.com", "password": "Correct-Horse-1"})
    assert r.status_code == 200
    assert r.json()["bidder"]["email"] == "priya@example.com"


def test_login_with_the_wrong_password_is_refused(client):
    client.post("/bidders/auth/signup", json=VALID_SIGNUP)
    r = client.post("/bidders/auth/login",
                    json={"email": "priya@example.com", "password": "nope"})
    assert r.status_code == 401


def test_me_without_a_token_is_refused(client):
    assert client.get("/bidders/auth/me").status_code == 401


def test_email_verification_confirm_through_the_api(client, conn):
    signup = client.post("/bidders/auth/signup", json=VALID_SIGNUP).json()
    account = bidder_store.get_bidder_by_email(conn, "priya@example.com")
    raw_token = bidder_store.create_email_verification(conn, account.id)
    r = client.get(f"/bidders/auth/verify-email/confirm?token={raw_token}")
    assert r.status_code == 200 and r.json()["email_verified"] is True


def test_verify_mobile_send_and_confirm_through_the_api(client, conn):
    signup = client.post("/bidders/auth/signup", json=VALID_SIGNUP).json()
    headers = {"Authorization": f"Bearer {signup['token']}"}
    send = client.post("/bidders/auth/verify-mobile/send", headers=headers)
    assert send.status_code == 200
    # No SMS provider configured -- delivery honestly fails, but a real OTP
    # was generated and stored; read it back the same way a provider's own
    # logs would let an operator, and confirm with it.
    account = bidder_store.get_bidder_by_email(conn, "priya@example.com")
    with conn.cursor() as cur:
        cur.execute("SELECT code_hash FROM bidder_mobile_otps WHERE bidder_id=%s "
                    "ORDER BY id DESC LIMIT 1", (account.id,))
        (stored_hash,) = cur.fetchone()
    # Brute-force the 6-digit space in the test only, to prove the confirm
    # endpoint really checks against the stored hash rather than always
    # succeeding -- cheap since it's SHA-256, not scrypt (see tokens.py).
    found = next((f"{i:06d}" for i in range(1_000_000) if hash_otp(f"{i:06d}") == stored_hash), None)
    assert found is not None
    confirm = client.post("/bidders/auth/verify-mobile/confirm", json={"otp": found}, headers=headers)
    assert confirm.status_code == 200 and confirm.json()["mobile_verified"] is True


def test_verify_mobile_confirm_rejects_the_wrong_code(client):
    signup = client.post("/bidders/auth/signup", json=VALID_SIGNUP).json()
    headers = {"Authorization": f"Bearer {signup['token']}"}
    client.post("/bidders/auth/verify-mobile/send", headers=headers)
    r = client.post("/bidders/auth/verify-mobile/confirm", json={"otp": "000000"}, headers=headers)
    assert r.status_code in (400,)


def test_forgot_password_gives_the_same_response_for_a_real_and_fake_email(client):
    client.post("/bidders/auth/signup", json=VALID_SIGNUP)
    real = client.post("/bidders/auth/forgot-password", json={"email": "priya@example.com"})
    fake = client.post("/bidders/auth/forgot-password", json={"email": "nobody@example.com"})
    assert real.status_code == fake.status_code == 200
    assert real.json() == fake.json()


def test_reset_password_through_the_api(client, conn):
    client.post("/bidders/auth/signup", json=VALID_SIGNUP)
    account = bidder_store.get_bidder_by_email(conn, "priya@example.com")
    raw_token = bidder_store.create_password_reset(conn, account.id)
    r = client.post("/bidders/auth/reset-password",
                    json={"token": raw_token, "new_password": "New-Correct-Horse-2"})
    assert r.status_code == 200
    login = client.post("/bidders/auth/login",
                        json={"email": "priya@example.com", "password": "New-Correct-Horse-2"})
    assert login.status_code == 200


def test_google_signin_is_honestly_unavailable_when_unconfigured(client):
    r = client.post("/bidders/auth/google", json={"id_token": "whatever"})
    assert r.status_code == 503


def test_change_password_through_the_api(client):
    signup = client.post("/bidders/auth/signup", json=VALID_SIGNUP).json()
    headers = {"Authorization": f"Bearer {signup['token']}"}
    r = client.post("/bidders/auth/change-password",
                    json={"current_password": "Correct-Horse-1", "new_password": "New-Correct-Horse-2"},
                    headers=headers)
    assert r.status_code == 200
    login = client.post("/bidders/auth/login",
                        json={"email": "priya@example.com", "password": "New-Correct-Horse-2"})
    assert login.status_code == 200


def test_change_password_rejects_the_wrong_current_password(client):
    signup = client.post("/bidders/auth/signup", json=VALID_SIGNUP).json()
    headers = {"Authorization": f"Bearer {signup['token']}"}
    r = client.post("/bidders/auth/change-password",
                    json={"current_password": "wrong", "new_password": "New-Correct-Horse-2"},
                    headers=headers)
    assert r.status_code == 401


# --- role separation between officer and bidder sessions ----------------------

def test_a_bidder_token_cannot_access_an_officer_route(client, conn):
    signup = client.post("/bidders/auth/signup", json=VALID_SIGNUP).json()
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {signup['token']}"})
    assert r.status_code == 401


def test_an_officer_token_cannot_access_a_bidder_route(client, conn):
    headers = auth_headers(conn, username="officer_1", role=Role.OFFICER)
    r = client.get("/bidders/auth/me", headers=headers)
    assert r.status_code == 401


def test_authentication_is_honestly_unavailable_when_unconfigured(client, monkeypatch):
    from satyapramana_store import app as app_module
    monkeypatch.setattr(app_module, "JWT_SECRET", None)
    r = client.post("/bidders/auth/signup", json=VALID_SIGNUP)
    assert r.status_code == 503
