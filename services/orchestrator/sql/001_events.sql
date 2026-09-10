-- The evidentiary spine. docs/EVENTS.md.
--
-- Three defects found by executing an earlier draft against PostgreSQL 14 are
-- corrected here; do not "simplify" them back:
--   * hash columns are text, never char(n) -- char blank-pads, so the genesis
--     sentinel exports as 64 characters and an independent verifier reports a
--     broken chain while our own check passes
--   * TRUNCATE needs its own statement-level trigger; row-level triggers do
--     not fire on it, leaving the append-only log wipeable
--   * the chain is protected by UNIQUE(prev_hash), which makes a fork a
--     constraint violation rather than something only a lock prevents

CREATE TABLE IF NOT EXISTS events (
    seq            bigserial   PRIMARY KEY,
    event_id       uuid        NOT NULL UNIQUE,
    event_type     text        NOT NULL,
    occurred_at    timestamptz NOT NULL,
    actor_kind     text        NOT NULL CHECK (actor_kind IN ('HUMAN','AGENT','ADAPTER','SYSTEM')),
    actor_id       text        NOT NULL,
    correlation_id uuid        NOT NULL,
    causation_id   uuid        REFERENCES events(event_id),
    tender_id      text,
    bidder_id      text,
    payload        jsonb       NOT NULL,

    prev_hash      text        NOT NULL CHECK (prev_hash ~ '^[0-9a-f]{64}$'),
    hash           text        NOT NULL CHECK (hash      ~ '^[0-9a-f]{64}$'),

    -- A hash may be claimed as a predecessor exactly once. Two concurrent
    -- writers reading the same tip cannot both commit: the loser violates this
    -- constraint and fails loudly instead of silently forking the chain.
    UNIQUE (hash),
    UNIQUE (prev_hash)
);

CREATE INDEX IF NOT EXISTS events_tender_type_idx ON events (tender_id, event_type);
CREATE INDEX IF NOT EXISTS events_bidder_type_idx ON events (bidder_id, event_type);
CREATE INDEX IF NOT EXISTS events_causation_idx   ON events (causation_id);

-- Append-only, enforced by the database rather than by there being no update
-- route. Honest limitation: a superuser can drop these triggers. Database
-- controls raise the cost of tampering; the property that survives a
-- compromised database is the exported hash chain, verifiable without us.
CREATE OR REPLACE FUNCTION events_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'events is append-only (attempted %)', TG_OP;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS events_no_mutate ON events;
CREATE TRIGGER events_no_mutate
    BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION events_immutable();

DROP TRIGGER IF EXISTS events_no_truncate ON events;
CREATE TRIGGER events_no_truncate
    BEFORE TRUNCATE ON events
    FOR EACH STATEMENT EXECUTE FUNCTION events_immutable();

-- prev_hash must be the current tip. Under READ COMMITTED this statement sees
-- rows committed by a concurrent writer, so it catches the race as well.
CREATE OR REPLACE FUNCTION events_chain_check() RETURNS trigger AS $$
DECLARE tip text;
BEGIN
    SELECT hash INTO tip FROM events ORDER BY seq DESC LIMIT 1;
    tip := COALESCE(tip, repeat('0', 64));
    IF NEW.prev_hash <> tip THEN
        RAISE EXCEPTION 'chain fork: prev_hash % is not the current tip %',
              NEW.prev_hash, tip;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS events_chain ON events;
CREATE TRIGGER events_chain
    BEFORE INSERT ON events
    FOR EACH ROW EXECUTE FUNCTION events_chain_check();

CREATE TABLE IF NOT EXISTS bidder_in_tender (
    tender_id text NOT NULL,
    bidder_id text NOT NULL,
    PRIMARY KEY (tender_id, bidder_id)
);
