"""Database access for bidder self-service accounts. Ordinary CRUD against
`bidder_accounts` and its three one-time-secret tables (sql/008_bidder_
accounts.sql) -- see that file's own comment for why this is deliberately
not folded into the append-only event log, the same reasoning auth/store.py
gives for the officer `users` table.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..auth.passwords import hash_password, verify_password
from .models import BidderAccount
from .tokens import (
    EMAIL_VERIFICATION_TTL, MOBILE_OTP_MAX_ATTEMPTS, MOBILE_OTP_TTL,
    PASSWORD_RESET_TTL, generate_opaque_token, generate_otp,
    hash_opaque_token, hash_otp,
)

_COLUMNS = (
    "id, email, full_name, mobile, company_name, gstin, "
    "email_verified, mobile_verified, disabled, google_sub, created_at"
)


def _row_to_account(row) -> BidderAccount:
    (bidder_id, email, full_name, mobile, company_name, gstin,
     email_verified, mobile_verified, disabled, google_sub, created_at) = row
    return BidderAccount(
        id=bidder_id, email=email, full_name=full_name, mobile=mobile,
        company_name=company_name, gstin=gstin, email_verified=email_verified,
        mobile_verified=mobile_verified, disabled=disabled,
        google_linked=google_sub is not None, created_at=created_at,
    )


# --- account lifecycle -------------------------------------------------------

def create_bidder_account(
    conn, *, email: str, password: str, full_name: str,
    mobile: str | None = None, company_name: str | None = None,
    gstin: str | None = None,
) -> BidderAccount:
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO bidder_accounts
                   (email, password_hash, full_name, mobile, company_name, gstin)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING {_COLUMNS}""",
            (email, hash_password(password), full_name, mobile, company_name, gstin),
        )
        row = cur.fetchone()
    return _row_to_account(row)


def create_bidder_account_via_google(
    conn, *, email: str, full_name: str, google_sub: str,
) -> BidderAccount:
    """A Google sign-up arrives with only a verified email and a name --
    Google has already proven the email is real, so email_verified starts
    true; mobile and company_name are collected afterwards, not invented."""
    with conn.cursor() as cur:
        cur.execute(
            f"""INSERT INTO bidder_accounts (email, full_name, google_sub, email_verified)
                VALUES (%s,%s,%s,true) RETURNING {_COLUMNS}""",
            (email, full_name, google_sub),
        )
        row = cur.fetchone()
    return _row_to_account(row)


def get_bidder_by_id(conn, bidder_account_id: int) -> BidderAccount | None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM bidder_accounts WHERE id=%s", (bidder_account_id,))
        row = cur.fetchone()
    return _row_to_account(row) if row else None


def get_bidder_by_email(conn, email: str) -> BidderAccount | None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM bidder_accounts WHERE email=%s", (email,))
        row = cur.fetchone()
    return _row_to_account(row) if row else None


def get_bidder_by_mobile(conn, mobile: str) -> BidderAccount | None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM bidder_accounts WHERE mobile=%s", (mobile,))
        row = cur.fetchone()
    return _row_to_account(row) if row else None


def get_bidder_by_google_sub(conn, google_sub: str) -> BidderAccount | None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM bidder_accounts WHERE google_sub=%s", (google_sub,))
        row = cur.fetchone()
    return _row_to_account(row) if row else None


def verify_login(conn, email: str, password: str) -> BidderAccount | None:
    """None for any failure reason (no such account, wrong password,
    disabled account, or a Google-only account with no password set) --
    deliberately undifferentiated to the caller, the same
    "don't tell an attacker which half they got wrong" reasoning as
    auth.store.verify_login for officers."""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT password_hash, {_COLUMNS} FROM bidder_accounts WHERE email=%s",
            (email,),
        )
        row = cur.fetchone()
    if not row:
        return None
    pw_hash, *account_row = row
    account = _row_to_account(account_row)
    if account.disabled or not pw_hash or not verify_password(password, pw_hash):
        return None
    return account


def set_password(conn, bidder_id: int, new_password: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE bidder_accounts SET password_hash=%s WHERE id=%s",
            (hash_password(new_password), bidder_id),
        )


def link_google_account(conn, bidder_id: int, google_sub: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE bidder_accounts SET google_sub=%s WHERE id=%s",
            (google_sub, bidder_id),
        )


def update_profile(
    conn, bidder_id: int, *, mobile: str | None = None,
    company_name: str | None = None, gstin: str | None = None,
) -> BidderAccount:
    """Sets mobile/company_name/gstin when given, without disturbing the
    fields not passed -- COALESCE keeps this one statement idempotent-safe
    rather than requiring the caller to re-fetch and re-send every field."""
    with conn.cursor() as cur:
        cur.execute(
            f"""UPDATE bidder_accounts
                   SET mobile=COALESCE(%s, mobile),
                       company_name=COALESCE(%s, company_name),
                       gstin=COALESCE(%s, gstin)
                 WHERE id=%s RETURNING {_COLUMNS}""",
            (mobile, company_name, gstin, bidder_id),
        )
        row = cur.fetchone()
    return _row_to_account(row)


def mark_email_verified(conn, bidder_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE bidder_accounts SET email_verified=true WHERE id=%s", (bidder_id,))


def mark_mobile_verified(conn, bidder_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE bidder_accounts SET mobile_verified=true WHERE id=%s", (bidder_id,))


# --- email verification -----------------------------------------------------

def create_email_verification(conn, bidder_id: int) -> str:
    """Invalidates any earlier, still-unconsumed token for this account
    first -- only the most recently requested link should ever work, so an
    old email sitting in an inbox can't be used after a bidder has asked for
    a fresh one. Returns the raw token (only ever held in memory / the
    outgoing email, never the database, which stores only its hash)."""
    raw_token = generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + EMAIL_VERIFICATION_TTL
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE bidder_email_verifications SET consumed_at=now() "
            "WHERE bidder_id=%s AND consumed_at IS NULL", (bidder_id,))
        cur.execute(
            "INSERT INTO bidder_email_verifications (bidder_id, token_hash, expires_at) "
            "VALUES (%s,%s,%s)",
            (bidder_id, hash_opaque_token(raw_token), expires_at),
        )
    return raw_token


def consume_email_verification(conn, raw_token: str) -> BidderAccount | None:
    """None for any failure (no such token, already used, expired) --
    same undifferentiated-failure shape as a login, for the same reason: a
    verification link is a bearer secret too."""
    token_hash = hash_opaque_token(raw_token)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, bidder_id, expires_at, consumed_at FROM bidder_email_verifications "
            "WHERE token_hash=%s", (token_hash,))
        row = cur.fetchone()
        if not row:
            return None
        record_id, bidder_id, expires_at, consumed_at = row
        if consumed_at is not None or expires_at < datetime.now(timezone.utc):
            return None
        cur.execute(
            "UPDATE bidder_email_verifications SET consumed_at=now() WHERE id=%s",
            (record_id,))
        cur.execute(
            "UPDATE bidder_accounts SET email_verified=true WHERE id=%s RETURNING " + _COLUMNS,
            (bidder_id,))
        account_row = cur.fetchone()
    return _row_to_account(account_row)


# --- mobile OTP --------------------------------------------------------------

def create_mobile_otp(conn, bidder_id: int) -> str:
    """Same invalidate-the-previous-one-first shape as email verification.
    Returns the raw 6-digit code -- callers hand it to an SMS sender, they
    never persist it and never return it in an API response."""
    raw_code = generate_otp()
    expires_at = datetime.now(timezone.utc) + MOBILE_OTP_TTL
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE bidder_mobile_otps SET consumed_at=now() "
            "WHERE bidder_id=%s AND consumed_at IS NULL", (bidder_id,))
        cur.execute(
            "INSERT INTO bidder_mobile_otps (bidder_id, code_hash, expires_at) "
            "VALUES (%s,%s,%s)",
            (bidder_id, hash_otp(raw_code), expires_at),
        )
    return raw_code


class OtpOutcome:
    """Why an OTP check succeeded or failed -- a plain string reason instead
    of a bare bool, because "wrong code" ("please retype it"), "expired"
    ("request a new one") and "too many attempts" ("wait or request a new
    one") are different instructions to a bidder, not the same failure."""
    OK = "OK"
    NO_ACTIVE_OTP = "NO_ACTIVE_OTP"
    EXPIRED = "EXPIRED"
    TOO_MANY_ATTEMPTS = "TOO_MANY_ATTEMPTS"
    WRONG_CODE = "WRONG_CODE"


def verify_mobile_otp(conn, bidder_id: int, code: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, code_hash, expires_at, attempts FROM bidder_mobile_otps "
            "WHERE bidder_id=%s AND consumed_at IS NULL ORDER BY id DESC LIMIT 1",
            (bidder_id,))
        row = cur.fetchone()
        if not row:
            return OtpOutcome.NO_ACTIVE_OTP
        record_id, code_hash, expires_at, attempts = row
        if expires_at < datetime.now(timezone.utc):
            return OtpOutcome.EXPIRED
        if attempts >= MOBILE_OTP_MAX_ATTEMPTS:
            return OtpOutcome.TOO_MANY_ATTEMPTS
        if hash_otp(code) != code_hash:
            cur.execute(
                "UPDATE bidder_mobile_otps SET attempts=attempts+1 WHERE id=%s",
                (record_id,))
            return OtpOutcome.WRONG_CODE
        cur.execute(
            "UPDATE bidder_mobile_otps SET consumed_at=now() WHERE id=%s", (record_id,))
        cur.execute(
            "UPDATE bidder_accounts SET mobile_verified=true WHERE id=%s", (bidder_id,))
    return OtpOutcome.OK


# --- password reset ----------------------------------------------------------

def create_password_reset(conn, bidder_id: int) -> str:
    raw_token = generate_opaque_token()
    expires_at = datetime.now(timezone.utc) + PASSWORD_RESET_TTL
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE bidder_password_resets SET consumed_at=now() "
            "WHERE bidder_id=%s AND consumed_at IS NULL", (bidder_id,))
        cur.execute(
            "INSERT INTO bidder_password_resets (bidder_id, token_hash, expires_at) "
            "VALUES (%s,%s,%s)",
            (bidder_id, hash_opaque_token(raw_token), expires_at),
        )
    return raw_token


def consume_password_reset(conn, raw_token: str, new_password: str) -> BidderAccount | None:
    token_hash = hash_opaque_token(raw_token)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, bidder_id, expires_at, consumed_at FROM bidder_password_resets "
            "WHERE token_hash=%s", (token_hash,))
        row = cur.fetchone()
        if not row:
            return None
        record_id, bidder_id, expires_at, consumed_at = row
        if consumed_at is not None or expires_at < datetime.now(timezone.utc):
            return None
        cur.execute(
            "UPDATE bidder_password_resets SET consumed_at=now() WHERE id=%s",
            (record_id,))
        cur.execute(
            "UPDATE bidder_accounts SET password_hash=%s WHERE id=%s",
            (hash_password(new_password), bidder_id))
        cur.execute(f"SELECT {_COLUMNS} FROM bidder_accounts WHERE id=%s", (bidder_id,))
        account_row = cur.fetchone()
    return _row_to_account(account_row)
