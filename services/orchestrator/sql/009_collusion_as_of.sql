-- Round 9: the Temporal Scrubber's one honest gap from round 8, closed.
-- `collusion_clusters` has no time dimension -- it reads `bidder_in_tender`
-- (current membership only, no seq column at all) and every
-- SHARED_ATTRIBUTE_OBSERVED event ever recorded, regardless of ceiling.
--
-- Both halves turn out to be real, seq-bearing events already:
--   * SHARED_ATTRIBUTE_OBSERVED already carries `seq` -- just bound it.
--   * BIDDER_REGISTERED (app.py's register_bidder, the same handler that
--     inserts into bidder_in_tender) is a real event with its own seq,
--     so tender membership as of a past point is reconstructible from
--     events instead of the live table.
--
-- Safe to compose independently: a SHARED_ATTRIBUTE_OBSERVED event is only
-- ever appended at the NEW bidder's own registration, comparing against
-- bidders who already registered earlier (app.py's _link_shared_attributes)
-- -- so its seq is always strictly greater than both referenced bidders'
-- BIDDER_REGISTERED seq. Any p_seq that admits an edge therefore already
-- admits both its endpoints' registrations; no extra join is needed to
-- keep an edge from reaching past a bidder who "shouldn't exist yet".
CREATE OR REPLACE FUNCTION collusion_clusters_as_of(p_tender text, p_seq bigint)
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
          AND seq <= p_seq
    ),
    undirected AS (SELECT a, b FROM edge UNION SELECT b, a FROM edge),
    registered AS (
        SELECT DISTINCT bidder_id
        FROM events
        WHERE event_type = 'BIDDER_REGISTERED'
          AND tender_id  = p_tender
          AND seq <= p_seq
    ),
    reach(root, node) AS (
        SELECT r.bidder_id, r.bidder_id FROM registered r
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
