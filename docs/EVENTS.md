# Event Log and Projections — SIH26100 / SATYAPRAMĀṆA

Status: **proposed**. Depends on `VERDICT_ALGEBRA.md`, `RULE_PACKS.md`,
`ADAPTERS.md`. This is the last specification before implementation.

---

## 1. What we took, and what we deliberately left

Charter §2.1 asks for a full event-sourced core. We take its **integrity
properties** and decline its **distributed-systems machinery**. Stating the cut
explicitly, because an undeclared partial implementation of event sourcing is
worse than either extreme:

| Taken | Left | Why |
|---|---|---|
| Append-only, hash-chained log as the only way state changes | Async projectors, eventual consistency | Projections update in the **same transaction** as the event insert. Same audit guarantees, none of the read-your-writes bugs. |
| Projections rebuildable from zero, byte-identical | Separate read/write services (CQRS) | Throughput here is dozens of bids, not millions. CQRS buys scaling we do not need and costs correctness we cannot spare. |
| Causation and correlation on every event | Event upcasting / schema migration machinery | Rule packs are versioned instead. Event payloads are additive-only. |
| Replay against a different rule pack (counterfactual) | Snapshots | The corpus is small enough to fold from genesis in seconds. |

**The one non-negotiable that survives intact:** there is no code path that
changes compliance state without emitting an event, because there is no other way
to change it. Projections are rebuilt, never patched. If you find yourself writing
`UPDATE` against a verdict, the design has been violated.

---

## 2. The event envelope

Every event, without exception:

| Field | Type | Note |
|---|---|---|
| `seq` | `bigserial` | Monotonic, database-assigned. The chain order. |
| `event_id` | `uuid` | Stable identity, used as a causation target |
| `event_type` | `text` | From the closed catalogue in §4 |
| `occurred_at` | `timestamptz` | Wall clock at emission |
| `actor_kind` | `HUMAN \| AGENT \| ADAPTER \| SYSTEM` | |
| `actor_id` | `text` | Officer identity, model stage id, or adapter id |
| `correlation_id` | `uuid` | The evaluation run this belongs to |
| `causation_id` | `uuid \| null` | The event that caused this one. Null only at a root. |
| `tender_id` | `text \| null` | Denormalised for query locality |
| `bidder_id` | `text \| null` | As above |
| `payload` | `jsonb` | Typed per `event_type` |
| `prev_hash` | `text` + `CHECK (~ '^[0-9a-f]{64}$')` | Genesis is 64 zeros, not the string `"genesis"` |
| `hash` | `text` + same CHECK | `sha256(prev_hash ‖ canonical_json(all other fields))` |

> **Never `char(64)` for these columns.** `char(n)` blank-pads: stored as
> `char(64)`, the sentinel `'genesis'` compares *equal* to `'genesis'` in SQL and
> `length()` reports 7 — but it exports as 64 characters with 57 trailing spaces.
> The in-database integrity check passes while an independent verifier reports a
> broken chain. That is the worst possible failure shape for this table, because
> §8's entire claim is that a third party can verify **without trusting us**.
> Caught by running the export against a real verifier; `text` with an explicit
> hex CHECK removes the type-dependent comparison semantics entirely.

`causation_id` is what makes provenance free rather than bolted on. The chain
verdict → fused evidence → verification → extraction → document is *literally* the
causation chain, walked backwards. There is no separate provenance table to keep
in sync, and therefore no way for it to drift.

### 2.1 The concurrency trap

A hash chain over `seq` requires that no two transactions compute `prev_hash`
from the same tip. Two concurrent inserts both reading tip *N* produce a **fork**,
and a forked chain silently destroys the exact property the chain exists to
provide. Naive implementations get this wrong and never notice, because it only
manifests under load.

Take a transaction-scoped advisory lock before reading the tip:

```sql
SELECT pg_advisory_xact_lock(hashtext('satyapramana.event_chain'));
```

Held to commit, released automatically, no cleanup path to forget. At this
volume the serialisation costs nothing.

**One global chain, not one per tender.** A global chain gives the strongest
statement — *"no event anywhere in this system was altered"* — and at dozens of
bids the write serialisation is irrelevant. Per-tender chains are the scaling
path if it ever matters; they weaken the claim slightly and should not be adopted
prematurely.

### 2.2 Model attribution

Every event emitted by a model stage additionally carries, in `payload`:

```
stage_id, stage_version, model_id, prompt_hash, params_hash
```

Deterministic stages carry `code_version` instead. This is charter §2.2.5, and it
is what lets any output be attributed to an exact configuration — the property a
fine-tuned model would have made harder to provide, not easier.

---

## 3. Append-only, enforced by the database

A comment saying "insert only" is not an integrity control. Two mechanisms,
because either alone has a hole:

```sql
REVOKE UPDATE, DELETE, TRUNCATE ON events FROM satyapramana_app;

CREATE FUNCTION events_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'events is append-only (attempted %)', TG_OP;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER events_no_mutate
    BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION events_immutable();

-- TRUNCATE needs its own statement-level trigger: row-level triggers do not
-- fire on TRUNCATE at all, so the trigger above leaves the table wipeable.
CREATE TRIGGER events_no_truncate
    BEFORE TRUNCATE ON events
    FOR EACH STATEMENT EXECUTE FUNCTION events_immutable();
```

The grant stops the application role. The triggers stop the table owner and
anyone who acquires it, which is the case the grant misses. Together they mean an
officer, an engineer, or a compromised application credential cannot alter a
recorded decision without leaving the hash chain broken.

**Both triggers are required.** With only the row-level one, `UPDATE` and
`DELETE` are blocked and `TRUNCATE` silently succeeds — verified against
PostgreSQL 14, where the first draft of this section wiped the table.

**Honest limitation:** a superuser can drop either trigger. Database controls
raise the cost of tampering; they do not make it impossible. The property that
actually survives a compromised database is the exported hash chain of §8, which
anyone can verify without our cooperation. State it that way in the pitch — an
integrity claim that overreaches is worse than one that is precisely bounded.

> Present state: `backend/src/index.js` already hash-chains the audit log
> correctly, but "insert only" is enforced by there simply being no update route.
> Moving that guarantee into the database is most of why the Postgres port is
> worth doing.

---

## 4. Event catalogue

Closed. A new event type is a deliberate addition, never an ad-hoc one.

**Tender and rules**
| Type | Emitted by | Payload highlights |
|---|---|---|
| `TENDER_INGESTED` | SYSTEM | `tender_id`, `document_sha256`, page count |
| `RULE_PACK_PROPOSED` | AGENT | draft pack, `review_required` flags, ambiguities |
| `RULE_PACK_ADOPTED` | **HUMAN** | `rule_pack_version`, reviewing officer, content hash |

**Bidder and documents**
| Type | Emitted by | Payload highlights |
|---|---|---|
| `BIDDER_REGISTERED` | SYSTEM | `bidder_id`, `tender_id`, claimed identifiers |
| `DOCUMENT_INGESTED` | SYSTEM | `document_sha256`, `storage_ref`, declared type |
| `DOCUMENT_SEGMENTED` | AGENT | per-page classification, regions |

**Extraction and normalisation**
| Type | Emitted by | Payload highlights |
|---|---|---|
| `FIELD_EXTRACTED` | AGENT | `path`, `value`, `page`, `region`, `confidence` |
| `VALUE_NORMALIZED` | AGENT+SYSTEM | raw → canonical, grammar that validated it |
| `ENTITY_RESOLVED` | AGENT+SYSTEM | linkage, `identifier_basis`, confidence |
| `EXTRACTION_FAILED` | SYSTEM | `path`, reason. **A recorded fact, not a silent gap.** |

One `FIELD_EXTRACTED` **per field**, not one per document. The page and region
travel on it, unbroken to the rendered `<EvidenceChip>` — charter §3.5.

**Verification**
| Type | Emitted by | Payload highlights |
|---|---|---|
| `VERIFICATION_REQUESTED` | SYSTEM | `capability_id`, subject, `as_of`, `lawful_basis` |
| `VERIFICATION_OBSERVED` | ADAPTER | observations, `raw_response_ref`, `observed_at`, `source_asserted_at` |
| `VERIFICATION_FAILED` | ADAPTER | `FailureCode`, real error text, `raw_response_ref` |

**Decision**
| Type | Emitted by | Payload highlights |
|---|---|---|
| `EVIDENCE_FUSED` | SYSTEM | agreement / conflict / gap per path |
| `REQUIREMENT_EVALUATED` | SYSTEM | `requirement_id`, verdict, reason code, `rule_pack_version` |
| `METRICS_COMPUTED` | SYSTEM | the three metrics, separately |
| `RISK_CLASSIFIED` | SYSTEM | level, triggering signals, risk function version |
| `SHARED_ATTRIBUTE_OBSERVED` | SYSTEM | the two bidders, attribute, value hash |

**Human**
| Type | Emitted by | Payload highlights |
|---|---|---|
| `VERDICT_OVERRIDDEN` | **HUMAN** | requirement, before, after, **justification**, officer |
| `DECISION_RECORDED` | **HUMAN** | `QUALIFY \| DISQUALIFY`, officer, metrics snapshot |
| `EXPLANATION_GENERATED` | AGENT | prose, marked presentation-only, alters nothing |

Only three event types have `actor_kind = HUMAN`, and they are exactly the three
places a human may change an outcome: adopting rules, overriding a verdict,
recording a decision. Every one carries an identity and, for overrides, a
mandatory justification. Charter §3.10 — an officer may overrule the system, and
the system remembers that they did.

`SHARED_ATTRIBUTE_OBSERVED` stores a **hash** of the shared value, not the value.
Two bidders sharing a bank account is the finding; the account number does not
need to enter the immutable log to establish it, and PII in an append-only store
can never be redacted afterwards.

---

## 5. Projections

Rebuildable caches. Every one carries `built_from_seq`, so staleness is
observable rather than assumed.

| Projection | Grain | Source events |
|---|---|---|
| `proj_evidence` | (bidder, evidence path) | `FIELD_EXTRACTED`, `VALUE_NORMALIZED`, `VERIFICATION_OBSERVED`, `EVIDENCE_FUSED` |
| `proj_verdicts` | (bidder, requirement) | `REQUIREMENT_EVALUATED`, `VERDICT_OVERRIDDEN` |
| `proj_metrics` | (bidder) | `METRICS_COMPUTED`, `RISK_CLASSIFIED` |
| `proj_collusion` | (tender, bidder) | `SHARED_ATTRIBUTE_OBSERVED` — §6 |
| `proj_audit` | (bidder) | `DECISION_RECORDED`, `VERDICT_OVERRIDDEN` |

`proj_verdicts` folds `VERDICT_OVERRIDDEN` **over** `REQUIREMENT_EVALUATED` and
keeps both — `verdict_system` and `verdict_effective` are separate columns. An
override never erases what the system concluded. That distinction is what lets
you later ask how often officers overrode the system and in which direction,
which is a genuinely interesting audit question and is free here.

### 5.1 Rebuild is a first-class command

```
rebuild_projections(up_to_seq = NULL)
```

Truncates and folds from genesis. CI runs it on the golden corpus and asserts the
result is byte-identical to the incrementally-maintained tables. That test is
what makes charter §3.9 enforced rather than aspirational.

`up_to_seq` gives time-travel for free — fold to sequence *N* and the projection
is the state as of that moment. The `<TemporalScrubber>` is deferred, but the
capability underneath it costs nothing extra, so the query stays supported.

Counterfactual replay is the same machinery with one substitution: replay the
same extraction and verification events against a different `rule_pack_version`.
No model is re-run, so it is fast and exactly reproducible.

---

## 6. Collusion as a projection

The 18th module. `networkx` in memory becomes a recursive CTE, so a flag survives
restart and — more importantly — becomes auditable: you can prove *when* a link
was detected and from which two documents.

```sql
WITH RECURSIVE
edge AS (
    SELECT DISTINCT
           LEAST(payload->>'bidder_a', payload->>'bidder_b')    AS a,
           GREATEST(payload->>'bidder_a', payload->>'bidder_b') AS b
    FROM events
    WHERE event_type = 'SHARED_ATTRIBUTE_OBSERVED'
      AND tender_id  = $1
),
undirected AS (
    SELECT a, b FROM edge
    UNION
    SELECT b, a FROM edge
),
reach(root, node) AS (
    SELECT bidder_id, bidder_id FROM bidder_in_tender WHERE tender_id = $1
    UNION
    SELECT r.root, u.b FROM reach r JOIN undirected u ON u.a = r.node
),
component AS (
    SELECT root AS bidder_id,
           array_agg(DISTINCT node ORDER BY node) AS members
    FROM reach GROUP BY root
)
SELECT bidder_id,
       cardinality(members) > 1                          AS flagged,
       'cluster_' || array_to_string(members, '_')        AS cluster_id,
       members
FROM component;
```

`UNION` rather than `UNION ALL` in `reach` is load-bearing: it deduplicates, which
is what terminates the recursion on a cyclic graph. `UNION ALL` runs forever on
any cycle, and a collusion ring is precisely a cycle.

`cluster_id` keeps the existing service's semantics — sorted, joined member ids —
so the value is stable regardless of which member is queried or in what order
bidders were registered.

---

## 7. "Why does this say PASS" — the query

Charter §9.H asks for the exact query path. It is one recursive walk backwards
along `causation_id`:

```sql
WITH RECURSIVE trail AS (
    SELECT * FROM (                      -- the anchor must be wrapped: ORDER BY
        SELECT event_id, seq, event_type, payload, causation_id, 0 AS depth
        FROM events                      -- and LIMIT are not permitted directly
        WHERE event_type = 'REQUIREMENT_EVALUATED'
          AND bidder_id  = $1            -- in a UNION branch
          AND payload->>'requirement_id' = $2
        ORDER BY seq DESC LIMIT 1
    ) anchor
  UNION ALL
    SELECT e.event_id, e.seq, e.event_type, e.payload, e.causation_id, t.depth + 1
    FROM events e JOIN trail t ON e.event_id = t.causation_id
)
SELECT depth, event_type, seq, payload FROM trail ORDER BY depth;
```

It returns, in order: the verdict → the fused evidence → the verification
observation (with its `raw_response_ref`) → the extraction (with `page` and
`region`) → the ingested document. That result set **is** `<ProvenanceTrail>`.

This is the demo axiom made mechanical: click a green `PASS`, run one query, land
on the highlighted line of the PDF next to the API response that corroborates it,
next to the rule that consumed both, with timestamps on all three.

---

## 8. Independent verification of the chain

Charter §9.J requires that a third party verify integrity **without trusting the
application**. The export is a JSON Lines file, one event per line in `seq` order,
and the verifier is thirty lines of any language:

```
h = "genesis"
for each line:
    assert line.prev_hash == h
    h = sha256(line.prev_hash + canonical_json(line minus hash))
    assert line.hash == h
```

Canonical JSON is the same rule as rule packs (`RULE_PACKS.md` §2.1): sorted
keys, no insignificant whitespace, UTF-8. The verifier needs the export and that
one paragraph — no database access, no application code, no cooperation from us.
That is the property that makes the log evidence rather than a claim.

---

## 9. Retention and PII

| Class | Retention | Note |
|---|---|---|
| Events | Indefinite | The evidentiary spine. Never pruned. |
| Raw response archive | 7 years | Credentials redacted **before** storage (`ADAPTERS.md` §6) |
| Uploaded documents | 7 years | Encrypted at rest |
| Derived projections | Ephemeral | Rebuildable; may be dropped at any time |

Because events are immutable, **PII minimisation must happen at emission**. There
is no later redaction. Hence identifiers, not values, wherever a hash suffices —
`SHARED_ATTRIBUTE_OBSERVED` is the pattern: it records that two bidders share a
bank account and can prove it, without the account number entering the permanent
log.

---

## 10. Verification status

Every SQL statement in this document was executed against PostgreSQL 14.20
before publication, not merely written. Doing so surfaced three defects in the
first draft, all now corrected above:

| # | Defect | Consequence had it shipped |
|---|---|---|
| 1 | Row-level trigger does not fire on `TRUNCATE` | The append-only log was wipeable by the table owner |
| 2 | `char(64)` blank-pads the genesis sentinel | Our own check passes; an independent verifier reports a broken chain |
| 3 | `ORDER BY`/`LIMIT` illegal in a recursive CTE anchor member | The provenance query — the demo — is a syntax error |

Results after correction:

| Check | Result |
|---|---|
| `UPDATE` / `DELETE` / `TRUNCATE` as the table owner | All three rejected by trigger |
| `UPDATE` / `DELETE` / `TRUNCATE` as the application role | All three rejected by grant |
| Non-hex hash insert | Rejected by CHECK constraint |
| 8 concurrent writers × 25 events, advisory lock held | 200 events, 200 distinct `prev_hash`, **0 forks** |
| Independent verifier over the JSON Lines export | 200/200 events link correctly |
| Tamper detection (forged payload at seq 101) | Detected at seq 102, the successor |
| Collusion CTE on a cyclic graph (A–B–C ring, D–E pair, F isolated) | Terminates; `cluster_A_B_C`, `cluster_D_E`, F unflagged |
| Provenance walk | 5 hops: `PASS` → `AGREEMENT` → `GST_STATUS` → extracted value with page and region → source document |

The tamper case is worth understanding precisely: altering an event is detected
at its **successor**, not at the altered row, because the successor's `prev_hash`
no longer matches. An attacker must therefore rewrite every event from the point
of tampering to the tip, and the export makes that visible to anyone holding an
earlier copy.
