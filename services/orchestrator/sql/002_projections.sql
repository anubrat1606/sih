-- Rebuildable caches. Dropping and refolding these from genesis must produce
-- byte-identical output; a CI test asserts it. docs/EVENTS.md section 5.

CREATE TABLE IF NOT EXISTS proj_verdicts (
    bidder_id        text NOT NULL,
    tender_id        text NOT NULL,
    requirement_id   text NOT NULL,
    -- Both are kept. An override never erases what the system concluded, which
    -- is what makes "how often did officers overturn us, and in which
    -- direction" answerable later.
    verdict_system   text NOT NULL,
    reason_system    text NOT NULL,
    verdict_effective text NOT NULL,
    reason_effective  text NOT NULL,
    overridden_by    text,
    override_justification text,
    rule_pack_version text NOT NULL,
    causation_event  uuid NOT NULL,
    built_from_seq   bigint NOT NULL,
    PRIMARY KEY (bidder_id, requirement_id)
);

CREATE TABLE IF NOT EXISTS proj_collusion (
    tender_id      text NOT NULL,
    bidder_id      text NOT NULL,
    flagged        boolean NOT NULL,
    cluster_id     text NOT NULL,
    members        text[] NOT NULL,
    built_from_seq bigint NOT NULL,
    PRIMARY KEY (tender_id, bidder_id)
);

-- Connected components over shared-attribute edges. UNION (not UNION ALL) in
-- `reach` is load-bearing: it deduplicates, which is what terminates the
-- recursion on a cyclic graph -- and a collusion ring is precisely a cycle.
CREATE OR REPLACE FUNCTION collusion_clusters(p_tender text)
RETURNS TABLE (bidder_id text, flagged boolean, cluster_id text, members text[])
AS $$
    WITH RECURSIVE
    edge AS (
        SELECT DISTINCT
               LEAST(payload->>'bidder_a', payload->>'bidder_b')    AS a,
               GREATEST(payload->>'bidder_a', payload->>'bidder_b') AS b
        FROM events
        WHERE event_type = 'SHARED_ATTRIBUTE_OBSERVED'
          AND tender_id  = p_tender
    ),
    undirected AS (SELECT a, b FROM edge UNION SELECT b, a FROM edge),
    reach(root, node) AS (
        SELECT b.bidder_id, b.bidder_id
          FROM bidder_in_tender b WHERE b.tender_id = p_tender
        UNION
        SELECT r.root, u.b FROM reach r JOIN undirected u ON u.a = r.node
    ),
    component AS (
        SELECT root, array_agg(DISTINCT node ORDER BY node) AS members
        FROM reach GROUP BY root
    )
    SELECT c.root,
           cardinality(c.members) > 1,
           'cluster_' || array_to_string(c.members, '_'),
           c.members
    FROM component c;
$$ LANGUAGE sql STABLE;

-- "Why does this say PASS." One backward walk along causation_id. The anchor
-- must be wrapped: ORDER BY and LIMIT are not permitted directly in a
-- recursive CTE's UNION branch.
CREATE OR REPLACE FUNCTION provenance_trail(p_bidder text, p_requirement text)
RETURNS TABLE (depth int, event_type text, seq bigint, occurred_at timestamptz, payload jsonb)
AS $$
    WITH RECURSIVE trail AS (
        SELECT * FROM (
            SELECT e.event_id, e.seq, e.event_type, e.occurred_at, e.payload,
                   e.causation_id, 0 AS depth
            FROM events e
            WHERE e.event_type = 'REQUIREMENT_EVALUATED'
              AND e.bidder_id  = p_bidder
              AND e.payload->>'requirement_id' = p_requirement
            ORDER BY e.seq DESC LIMIT 1
        ) anchor
      UNION ALL
        SELECT e.event_id, e.seq, e.event_type, e.occurred_at, e.payload,
               e.causation_id, t.depth + 1
        FROM events e JOIN trail t ON e.event_id = t.causation_id
    )
    SELECT t.depth, t.event_type, t.seq, t.occurred_at, t.payload
    FROM trail t ORDER BY t.depth;
$$ LANGUAGE sql STABLE;
