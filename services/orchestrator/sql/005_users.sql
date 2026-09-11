-- Officer accounts. Deliberately NOT part of the append-only `events` table:
-- a login isn't evidence about a bidder's compliance, and folding it in would
-- dilute the event log's one real job. This is an ordinary, mutable table --
-- a password can be reset, an account can be disabled -- with its own
-- security surface, not the evidentiary spine docs/EVENTS.md describes.
--
-- Every action an authenticated officer takes still records their real
-- identity on the domain event log via `actor=Actor("HUMAN", user.username)`
-- (see app.py) -- auth doesn't weaken that, it makes it trustworthy: nobody
-- can claim to be an officer they aren't just by typing a name into a form.

CREATE TABLE IF NOT EXISTS users (
    id            bigserial   PRIMARY KEY,
    username      text        NOT NULL UNIQUE,
    password_hash text        NOT NULL,
    display_name  text        NOT NULL,
    role          text        NOT NULL CHECK (role IN ('OFFICER','SENIOR_OFFICER','ADMIN')),
    disabled      boolean     NOT NULL DEFAULT false,
    created_at    timestamptz NOT NULL DEFAULT now()
);
