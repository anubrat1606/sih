-- Adopted rule packs. docs/RULE_PACKS.md.
--
-- A rule pack is immutable once adopted. Amending it means publishing a new
-- version and emitting another RULE_PACK_ADOPTED event; verdicts already
-- recorded keep pointing at the old version and stay reproducible forever. A
-- corrigendum to a live tender is therefore modelled correctly and for free.

CREATE TABLE IF NOT EXISTS rule_packs (
    rule_pack_version text PRIMARY KEY,      -- id@semver+hash12
    rule_pack_id      text NOT NULL,
    semver            text NOT NULL,
    content_hash      text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    tender_id         text NOT NULL,
    body              jsonb NOT NULL,
    adopted_at        timestamptz NOT NULL,
    adopted_by        text NOT NULL,
    adoption_event    uuid NOT NULL REFERENCES events(event_id)
);

CREATE INDEX IF NOT EXISTS rule_packs_tender_idx
    ON rule_packs (tender_id, adopted_at DESC);

CREATE OR REPLACE FUNCTION rule_packs_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'rule_packs is append-only (attempted %); amend by adopting a new version', TG_OP;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS rule_packs_no_mutate ON rule_packs;
CREATE TRIGGER rule_packs_no_mutate
    BEFORE UPDATE OR DELETE ON rule_packs
    FOR EACH ROW EXECUTE FUNCTION rule_packs_immutable();

DROP TRIGGER IF EXISTS rule_packs_no_truncate ON rule_packs;
CREATE TRIGGER rule_packs_no_truncate
    BEFORE TRUNCATE ON rule_packs
    FOR EACH STATEMENT EXECUTE FUNCTION rule_packs_immutable();

-- Evidence as the decision stage sees it: one row per (bidder, path), folded
-- from extraction and verification events. A cache, like every projection.
CREATE TABLE IF NOT EXISTS proj_evidence (
    bidder_id         text NOT NULL,
    path              text NOT NULL,
    resolved          boolean NOT NULL,
    value             jsonb,
    -- Why it could not be resolved, taken from the evidence record itself and
    -- never guessed. This is what propagates into the leaf's reason code.
    unresolved_reason text,
    tier              text,
    channel           text,
    capability_id     text,
    observed_at       timestamptz,
    source_asserted_at date,
    source_event      uuid,
    built_from_seq    bigint NOT NULL,
    PRIMARY KEY (bidder_id, path)
);
