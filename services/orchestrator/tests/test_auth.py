"""Officer accounts: password hashing, session tokens, the store, and the
real API surface (login, me, user creation, and the role gate on
SENIOR_OFFICER-only actions). See satyapramana_store/auth/ for the design
rationale -- this only tests it holds.
"""
from __future__ import annotations

import time
from datetime import timedelta

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from satyapramana_store.app import app, db
from satyapramana_store.auth.models import Role, User, role_at_least
from satyapramana_store.auth.passwords import hash_password, verify_password
from satyapramana_store.auth.store import (
    bootstrap_admin, create_user, get_user_by_username, list_users, set_disabled,
    set_password, verify_login,
)
from satyapramana_store.auth.tokens import decode_token, issue_token

from .conftest import auth_headers

TEST_SECRET = "test-secret-not-for-production-32chars+"


# --- passwords --------------------------------------------------------------

def test_a_password_round_trips_through_hash_and_verify():
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored)


def test_the_wrong_password_is_rejected():
    stored = hash_password("correct horse battery staple")
    assert not verify_password("wrong password entirely", stored)


def test_two_hashes_of_the_same_password_differ():
    """Different random salts -- proves the salt is actually random per call,
    not a fixed or empty one that would make two accounts with the same
    password produce an identical, correlatable hash."""
    assert hash_password("same password") != hash_password("same password")


def test_a_malformed_stored_hash_fails_closed_not_open():
    assert not verify_password("anything", "not-a-real-hash-at-all")
    assert not verify_password("anything", "scrypt$not$enough$fields")
    assert not verify_password("anything", "bcrypt$16384$8$1$aa$bb")  # right shape, wrong algo tag


# --- tokens -------------------------------------------------------------------

def _user(role=Role.OFFICER):
    return User(id=1, username="officer_1", display_name="Officer One",
                role=role, disabled=False)


def test_a_token_round_trips_the_username_and_role():
    token = issue_token(_user(Role.SENIOR_OFFICER), TEST_SECRET)
    claims = decode_token(token, TEST_SECRET)
    assert claims["sub"] == "officer_1"
    assert claims["role"] == "SENIOR_OFFICER"


def test_a_token_signed_with_a_different_secret_is_rejected():
    token = issue_token(_user(), TEST_SECRET)
    with pytest.raises(pyjwt.PyJWTError):
        decode_token(token, "a-completely-different-secret-value-32+")


def test_an_expired_token_is_rejected():
    token = issue_token(_user(), TEST_SECRET, ttl=timedelta(seconds=-1))
    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_token(token, TEST_SECRET)


# --- role ordering --------------------------------------------------------

def test_role_ordering_is_total_and_reflexive():
    assert role_at_least(Role.ADMIN, Role.OFFICER)
    assert role_at_least(Role.SENIOR_OFFICER, Role.SENIOR_OFFICER)
    assert not role_at_least(Role.OFFICER, Role.SENIOR_OFFICER)
    assert not role_at_least(Role.SENIOR_OFFICER, Role.ADMIN)


# --- store ------------------------------------------------------------------

def test_create_and_fetch_a_user(conn):
    created = create_user(conn, "priya", "a-real-password-123", "Priya Sharma", Role.OFFICER)
    fetched = get_user_by_username(conn, "priya")
    assert fetched == created


def test_fetching_an_unknown_username_is_none_not_an_error(conn):
    assert get_user_by_username(conn, "nobody-by-this-name") is None


def test_verify_login_succeeds_with_the_right_password(conn):
    create_user(conn, "priya", "a-real-password-123", "Priya Sharma", Role.OFFICER)
    user = verify_login(conn, "priya", "a-real-password-123")
    assert user is not None and user.username == "priya"


def test_verify_login_fails_the_same_way_for_unknown_user_and_wrong_password(conn):
    create_user(conn, "priya", "a-real-password-123", "Priya Sharma", Role.OFFICER)
    assert verify_login(conn, "priya", "the-wrong-password") is None
    assert verify_login(conn, "not-priya-at-all", "a-real-password-123") is None


def test_a_disabled_account_cannot_log_in(conn):
    create_user(conn, "priya", "a-real-password-123", "Priya Sharma", Role.OFFICER)
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET disabled=true WHERE username='priya'")
    assert verify_login(conn, "priya", "a-real-password-123") is None


def test_bootstrap_admin_is_a_noop_without_both_env_vars(conn, monkeypatch):
    monkeypatch.delenv("SATYAPRAMANA_BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("SATYAPRAMANA_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    assert bootstrap_admin(conn) is None


def test_bootstrap_admin_creates_an_admin_from_env_vars(conn, monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_BOOTSTRAP_ADMIN_USERNAME", "root_officer")
    monkeypatch.setenv("SATYAPRAMANA_BOOTSTRAP_ADMIN_PASSWORD", "a-real-bootstrap-password")
    user = bootstrap_admin(conn)
    assert user is not None
    assert user.role is Role.ADMIN
    assert verify_login(conn, "root_officer", "a-real-bootstrap-password") is not None


def test_bootstrap_admin_is_idempotent(conn, monkeypatch):
    monkeypatch.setenv("SATYAPRAMANA_BOOTSTRAP_ADMIN_USERNAME", "root_officer")
    monkeypatch.setenv("SATYAPRAMANA_BOOTSTRAP_ADMIN_PASSWORD", "a-real-bootstrap-password")
    first = bootstrap_admin(conn)
    second = bootstrap_admin(conn)
    assert first == second  # same row, not a duplicate or an error


# --- through the real API ----------------------------------------------------

@pytest.fixture()
def client(conn):
    app.dependency_overrides[db] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_login_with_real_credentials_returns_a_usable_token(client, conn):
    create_user(conn, "priya", "a-real-password-123", "Priya Sharma", Role.SENIOR_OFFICER)
    body = client.post("/auth/login", json={"username": "priya",
                                            "password": "a-real-password-123"}).json()
    assert body["username"] == "priya" and body["role"] == "SENIOR_OFFICER"
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"}).json()
    assert me["username"] == "priya"


def test_login_with_the_wrong_password_is_refused(client, conn):
    create_user(conn, "priya", "a-real-password-123", "Priya Sharma", Role.OFFICER)
    r = client.post("/auth/login", json={"username": "priya", "password": "nope"})
    assert r.status_code == 401


def test_me_without_a_token_is_refused(client):
    assert client.get("/auth/me").status_code == 401


def test_me_with_a_garbage_token_is_refused(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_only_an_admin_can_create_an_officer_account(client, conn):
    r = client.post("/auth/users",
                    json={"username": "new_officer", "password": "a-real-password-1",
                          "display_name": "New Officer", "role": "OFFICER"},
                    headers=auth_headers(conn, username="senior_1", role=Role.SENIOR_OFFICER))
    assert r.status_code == 403


def test_an_admin_can_create_an_officer_account(client, conn):
    r = client.post("/auth/users",
                    json={"username": "new_officer", "password": "a-real-password-1",
                          "display_name": "New Officer", "role": "OFFICER"},
                    headers=auth_headers(conn, username="admin_1", role=Role.ADMIN))
    assert r.status_code == 201
    assert get_user_by_username(conn, "new_officer") is not None


def test_creating_a_duplicate_username_is_refused(client, conn):
    create_user(conn, "existing", "a-real-password-1", "Existing Officer", Role.OFFICER)
    r = client.post("/auth/users",
                    json={"username": "existing", "password": "a-real-password-2",
                          "display_name": "Duplicate", "role": "OFFICER"},
                    headers=auth_headers(conn, username="admin_1", role=Role.ADMIN))
    assert r.status_code == 409


def test_list_users_returns_every_account_oldest_first(conn):
    create_user(conn, "zed_officer", "a-real-password-1", "Zed", Role.OFFICER)
    create_user(conn, "amy_officer", "a-real-password-1", "Amy", Role.OFFICER)
    users = list_users(conn)
    usernames = [u.username for u in users]
    assert usernames.index("zed_officer") < usernames.index("amy_officer")
    assert all(u.created_at is not None for u in users)


def test_set_disabled_flips_the_bit_and_login_then_fails(conn):
    create_user(conn, "to_disable", "a-real-password-1", "Disable Me", Role.OFFICER)
    assert verify_login(conn, "to_disable", "a-real-password-1") is not None
    updated = set_disabled(conn, "to_disable", True)
    assert updated.disabled
    assert verify_login(conn, "to_disable", "a-real-password-1") is None
    reenabled = set_disabled(conn, "to_disable", False)
    assert not reenabled.disabled
    assert verify_login(conn, "to_disable", "a-real-password-1") is not None


def test_set_disabled_on_an_unknown_username_is_none_not_an_error(conn):
    assert set_disabled(conn, "nobody-here", True) is None


def test_set_password_changes_the_password_and_old_one_stops_working(conn):
    create_user(conn, "to_reset", "the-old-password-1", "Reset Me", Role.OFFICER)
    assert verify_login(conn, "to_reset", "the-old-password-1") is not None
    updated = set_password(conn, "to_reset", "a-brand-new-password-2")
    assert updated is not None
    assert verify_login(conn, "to_reset", "the-old-password-1") is None
    assert verify_login(conn, "to_reset", "a-brand-new-password-2") is not None


def test_set_password_on_an_unknown_username_is_none_not_an_error(conn):
    assert set_password(conn, "nobody-here", "whatever-password-1") is None


def test_only_an_admin_can_list_accounts(client, conn):
    r = client.get("/auth/users",
                   headers=auth_headers(conn, username="senior_2", role=Role.SENIOR_OFFICER))
    assert r.status_code == 403


def test_an_admin_can_list_accounts(client, conn):
    create_user(conn, "listed_officer", "a-real-password-1", "Listed", Role.OFFICER)
    r = client.get("/auth/users", headers=auth_headers(conn, username="admin_2", role=Role.ADMIN))
    assert r.status_code == 200
    usernames = {u["username"] for u in r.json()["users"]}
    assert {"listed_officer", "admin_2"} <= usernames


def test_an_admin_can_disable_and_reenable_another_account(client, conn):
    create_user(conn, "disable_target", "a-real-password-1", "Target", Role.OFFICER)
    headers = auth_headers(conn, username="admin_3", role=Role.ADMIN)
    r = client.post("/auth/users/disable_target/disable", headers=headers)
    assert r.status_code == 200 and r.json()["disabled"] is True
    assert verify_login(conn, "disable_target", "a-real-password-1") is None
    r = client.post("/auth/users/disable_target/enable", headers=headers)
    assert r.status_code == 200 and r.json()["disabled"] is False
    assert verify_login(conn, "disable_target", "a-real-password-1") is not None


def test_an_admin_cannot_disable_their_own_account(client, conn):
    headers = auth_headers(conn, username="admin_4", role=Role.ADMIN)
    r = client.post("/auth/users/admin_4/disable", headers=headers)
    assert r.status_code == 422
    assert verify_login(conn, "admin_4", "correct horse battery staple") is not None


def test_disabling_an_unknown_account_is_404(client, conn):
    r = client.post("/auth/users/nobody-here/disable",
                    headers=auth_headers(conn, username="admin_5", role=Role.ADMIN))
    assert r.status_code == 404


def test_a_non_admin_cannot_disable_an_account(client, conn):
    create_user(conn, "untouchable", "a-real-password-1", "Untouchable", Role.OFFICER)
    r = client.post("/auth/users/untouchable/disable",
                    headers=auth_headers(conn, username="senior_3", role=Role.SENIOR_OFFICER))
    assert r.status_code == 403


def test_an_admin_can_reset_another_accounts_password(client, conn):
    create_user(conn, "reset_target", "the-old-password-1", "Target", Role.OFFICER)
    headers = auth_headers(conn, username="admin_6", role=Role.ADMIN)
    r = client.post("/auth/users/reset_target/reset-password", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "reset_target"
    new_password = body["new_password"]
    assert verify_login(conn, "reset_target", "the-old-password-1") is None
    assert verify_login(conn, "reset_target", new_password) is not None


def test_resetting_an_unknown_accounts_password_is_404(client, conn):
    r = client.post("/auth/users/nobody-here/reset-password",
                    headers=auth_headers(conn, username="admin_7", role=Role.ADMIN))
    assert r.status_code == 404


def test_a_non_admin_cannot_reset_a_password(client, conn):
    create_user(conn, "untouchable_pw", "a-real-password-1", "Untouchable", Role.OFFICER)
    r = client.post("/auth/users/untouchable_pw/reset-password",
                    headers=auth_headers(conn, username="senior_4", role=Role.SENIOR_OFFICER))
    assert r.status_code == 403


def test_adopting_a_rule_pack_requires_senior_officer(client, conn):
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"},
                headers=auth_headers(conn, username="junior", role=Role.OFFICER))
    from .test_decide import PACK
    r = client.post("/tenders/T1/rule-pack", json={"pack": PACK},
                    headers=auth_headers(conn, username="junior", role=Role.OFFICER))
    assert r.status_code == 403


def test_recording_a_decision_only_needs_any_authenticated_officer(client, conn):
    client.post("/tenders/T1/bidders", json={"bidder_id": "A"},
                headers=auth_headers(conn, username="junior", role=Role.OFFICER))
    r = client.post("/bidders/A/decision", params={"tender_id": "T1"},
                    json={"decision": "QUALIFY"},
                    headers=auth_headers(conn, username="junior", role=Role.OFFICER))
    assert r.status_code == 201


def test_authentication_is_honestly_unavailable_when_unconfigured(client, monkeypatch):
    from satyapramana_store import app as app_module
    monkeypatch.setattr(app_module, "JWT_SECRET", None)
    r = client.post("/auth/login", json={"username": "anyone", "password": "anything"})
    assert r.status_code == 503
