-- Raw response archive. docs/ADAPTERS.md section 6.
--
-- "When a response is later disputed, the parsed interpretation is not
-- evidence. The raw payload is."
--
-- Immutable for the same reason `events` is, and archived on failure as well as
-- success: a 500 body is the evidence that the authority was down, and it is
-- what answers "why is this UNKNOWN" eighteen months later.

CREATE TABLE IF NOT EXISTS raw_responses (
    content_sha256   text        PRIMARY KEY CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    adapter_id       text        NOT NULL,
    adapter_version  text        NOT NULL,
    capability_id    text        NOT NULL,
    observed_at      timestamptz NOT NULL,

    request_method   text        NOT NULL,
    request_url      text        NOT NULL,   -- credentials stripped from the query
    request_headers  jsonb       NOT NULL,   -- secrets replaced with [REDACTED]
    request_body     text,                   -- secrets replaced with [REDACTED]

    response_status  integer,
    response_headers jsonb,
    response_body    text,                   -- verbatim, undecoded, unformatted

    lawful_basis     text        NOT NULL,
    consent_reference text,
    requested_by     text        NOT NULL,
    purpose          text        NOT NULL
);

CREATE INDEX IF NOT EXISTS raw_responses_capability_idx
    ON raw_responses (capability_id, observed_at DESC);

CREATE OR REPLACE FUNCTION raw_responses_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'raw_responses is append-only (attempted %)', TG_OP;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS raw_responses_no_mutate ON raw_responses;
CREATE TRIGGER raw_responses_no_mutate
    BEFORE UPDATE OR DELETE ON raw_responses
    FOR EACH ROW EXECUTE FUNCTION raw_responses_immutable();

DROP TRIGGER IF EXISTS raw_responses_no_truncate ON raw_responses;
CREATE TRIGGER raw_responses_no_truncate
    BEFORE TRUNCATE ON raw_responses
    FOR EACH STATEMENT EXECUTE FUNCTION raw_responses_immutable();
