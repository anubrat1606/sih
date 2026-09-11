"""Database access for officer accounts. Ordinary CRUD against `users`
(sql/005_users.sql) -- see that file's own comment for why this is
deliberately not folded into the append-only event log.
"""
from __future__ import annotations

import os

from .models import Role, User
from .passwords import hash_password, verify_password


def create_user(conn, username: str, password: str, display_name: str, role: Role) -> User:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO users (username, password_hash, display_name, role)
               VALUES (%s,%s,%s,%s) RETURNING id, disabled""",
            (username, hash_password(password), display_name, role.value))
        user_id, disabled = cur.fetchone()
    return User(id=user_id, username=username, display_name=display_name,
                role=role, disabled=disabled)


def get_user_by_username(conn, username: str) -> User | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, username, display_name, role, disabled FROM users WHERE username=%s",
            (username,))
        row = cur.fetchone()
    if not row:
        return None
    uid, uname, display_name, role, disabled = row
    return User(id=uid, username=uname, display_name=display_name,
                role=Role(role), disabled=disabled)


def verify_login(conn, username: str, password: str) -> User | None:
    """None for any failure reason (no such user, wrong password, disabled
    account) -- deliberately undifferentiated to the caller, the same
    "don't tell an attacker which half they got wrong" reasoning behind
    every login form that has ever existed."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, username, password_hash, display_name, role, disabled
               FROM users WHERE username=%s""",
            (username,))
        row = cur.fetchone()
    if not row:
        return None
    user_id, uname, pw_hash, display_name, role, disabled = row
    if disabled or not verify_password(password, pw_hash):
        return None
    return User(id=user_id, username=uname, display_name=display_name,
                role=Role(role), disabled=disabled)


def bootstrap_admin(conn) -> User | None:
    """Creates the first ADMIN account from environment variables,
    idempotently, if one with that username doesn't already exist.
    Deployment-friendly on purpose: a managed platform's env-var panel is
    reachable without shell access; a one-off script isn't always.
    Silently does nothing (returns None) if the two env vars aren't both
    set -- an absent bootstrap is a normal, honest state, not an error."""
    username = os.environ.get("SATYAPRAMANA_BOOTSTRAP_ADMIN_USERNAME")
    password = os.environ.get("SATYAPRAMANA_BOOTSTRAP_ADMIN_PASSWORD")
    if not username or not password:
        return None
    existing = get_user_by_username(conn, username)
    if existing:
        return existing
    return create_user(conn, username, password, display_name=username, role=Role.ADMIN)
