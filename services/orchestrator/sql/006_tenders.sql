-- Explicit tender metadata (satyapramana.md's Tender Management module).
-- Rebuildable cache folded from TENDER_CREATED events, same shape and same
-- rule as proj_verdicts/proj_collusion: DELETE-and-refold here is correct
-- because the event log, not this table, is the source of truth.
--
-- A tender's existence is still also inferrable from bidder_in_tender (a
-- bidder can register on a tender_id nobody explicitly created first, same
-- as before this migration) -- this table adds real metadata for the
-- tenders an officer *did* set up deliberately, it doesn't replace the old
-- implicit path.

CREATE TABLE IF NOT EXISTS proj_tenders (
    tender_id              text PRIMARY KEY,
    title                  text NOT NULL,
    issuing_authority      text NOT NULL,
    bid_submission_deadline date,
    description            text,
    created_by             text NOT NULL,
    built_from_seq         bigint NOT NULL
);
