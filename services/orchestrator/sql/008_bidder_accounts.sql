-- Bidder self-service accounts. Deliberately a separate table and identity
-- space from `users` (005_users.sql, officer accounts) -- a bidder must
-- never be able to authenticate onto an officer route by any accidental
-- username/id collision. The real separation is enforced at the token
-- level too: every bidder JWT carries "typ": "bidder", which app.py's
-- officer-side current_user() dependency explicitly refuses, and the new
-- current_bidder() dependency explicitly requires -- see bidder_auth/.
--
-- Not part of the append-only `events` table for the same reason
-- 005_users.sql's officer accounts aren't: creating an account isn't
-- evidence about a bid's compliance. A bidder's real actions on a tender
-- (registering, uploading a document, running verification) already go
-- through the existing endpoints and are recorded on the event log under
-- their bidder_id -- this table only proves who is allowed to act as that
-- bidder_id from a browser session; it is not itself part of the
-- evidentiary record.
--
-- mobile, company_name and password_hash are nullable because a Google
-- sign-up arrives with only a verified email and a name -- everything else
-- is collected afterwards, the same way a real product completes a
-- Google-first profile rather than inventing placeholder values for fields
-- Google never provided.

CREATE TABLE IF NOT EXISTS bidder_accounts (
    id               bigserial   PRIMARY KEY,
    email            text        NOT NULL UNIQUE,
    password_hash    text,
    full_name        text        NOT NULL,
    mobile           text,        -- normalised 10-digit Indian mobile, no +91/0 prefix
    company_name     text,
    gstin            text,
    email_verified   boolean     NOT NULL DEFAULT false,
    mobile_verified  boolean     NOT NULL DEFAULT false,
    disabled         boolean     NOT NULL DEFAULT false,
    google_sub       text UNIQUE,  -- Google account subject id, if signed up/linked via Google
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- A real mobile number is unique per account once provided (mirrors the
-- "Duplicate email/mobile handling" requirement) -- but the column stays
-- nullable above, so the constraint is a partial index, not NOT NULL UNIQUE.
CREATE UNIQUE INDEX IF NOT EXISTS bidder_accounts_mobile_unique_idx
    ON bidder_accounts (mobile) WHERE mobile IS NOT NULL;

-- Email verification tokens: one-time, opaque, short-lived, stored hashed
-- (SHA-256 -- these are high-entropy random tokens, not low-entropy
-- passwords, so a slow KDF buys nothing; see bidder_auth/tokens.py) so a
-- leaked database backup can't be replayed as a valid verification link.
CREATE TABLE IF NOT EXISTS bidder_email_verifications (
    id            bigserial   PRIMARY KEY,
    bidder_id     bigint      NOT NULL REFERENCES bidder_accounts(id) ON DELETE CASCADE,
    token_hash    text        NOT NULL UNIQUE,
    expires_at    timestamptz NOT NULL,
    consumed_at   timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS bidder_email_verifications_bidder_idx
    ON bidder_email_verifications (bidder_id);

-- Mobile OTPs: 6-digit, short-lived, stored hashed, with an attempt counter
-- so a leaked hash or a guessed value can't be brute-forced indefinitely --
-- the expiry and attempt limit do the real work here, not the hash
-- algorithm choice.
CREATE TABLE IF NOT EXISTS bidder_mobile_otps (
    id            bigserial   PRIMARY KEY,
    bidder_id     bigint      NOT NULL REFERENCES bidder_accounts(id) ON DELETE CASCADE,
    code_hash     text        NOT NULL,
    expires_at    timestamptz NOT NULL,
    attempts      int         NOT NULL DEFAULT 0,
    consumed_at   timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS bidder_mobile_otps_bidder_idx
    ON bidder_mobile_otps (bidder_id);

-- Password reset tokens: same one-time, opaque, hashed shape as email
-- verification.
CREATE TABLE IF NOT EXISTS bidder_password_resets (
    id            bigserial   PRIMARY KEY,
    bidder_id     bigint      NOT NULL REFERENCES bidder_accounts(id) ON DELETE CASCADE,
    token_hash    text        NOT NULL UNIQUE,
    expires_at    timestamptz NOT NULL,
    consumed_at   timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS bidder_password_resets_bidder_idx
    ON bidder_password_resets (bidder_id);
