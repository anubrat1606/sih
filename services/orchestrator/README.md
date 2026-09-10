# services/orchestrator — persistence and the event log

The append-only, hash-chained event log and the projections folded from it.
Implements `docs/EVENTS.md`. Replaces the MongoDB layer in `/backend`, which
stays running until this has passed the same end-to-end path.

No ORM. The schema is small, the SQL *is* the specification, and an ORM here
would put a translation layer between the audit claim and what actually runs.

| Path | Contents |
|---|---|
| `sql/001_events.sql` | The `events` table, immutability triggers, the chain trigger |
| `sql/002_projections.sql` | Projection tables, `collusion_clusters()`, `provenance_trail()` |
| `satyapramana_store/events.py` | Canonical hashing, `append`, export, independent verification |
| `satyapramana_store/projections.py` | Rebuild, collusion, provenance |
| `satyapramana_store/adapters/` | The verification adapter interface, capability registry, failure taxonomy, redacting raw-response archive |
| `satyapramana_store/normalise.py` | Per-attribute normalisation for shared-attribute detection |
| `satyapramana_store/rulepacks.py` | Rule pack adoption, validated and gated |
| `satyapramana_store/evidence.py` | The evidence projection and the resolver the rule engine reads through |
| `satyapramana_store/decide.py` | The DECIDE stage -- deterministic, zero model involvement |
| `satyapramana_store/extract/` | INGEST and the deterministic half of EXTRACT: grammars with structural checks, page layout, bounding boxes |
| `satyapramana_store/app.py` | The FastAPI orchestrator |

## Run

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt -e ../core
createdb satyapramana_test
export DATABASE_URL=postgresql://localhost/satyapramana_test
./venv/bin/python -m pytest tests/ -q
```

The tests require a real PostgreSQL. Without `DATABASE_URL` they **skip** — they
never fall back to a stub. A green suite that silently ran against a fake would
be exactly the comfortable fiction this project refuses everywhere else.

## Four things found by running this, not by reviewing it

Each was a defect in a draft that read as correct:

1. **Row-level triggers do not fire on `TRUNCATE`.** `UPDATE` and `DELETE` were
   blocked while `TRUNCATE` quietly emptied the table. Fixed with a separate
   statement-level trigger.
2. **`char(64)` blank-pads.** `'genesis'` compared equal in SQL and `length()`
   said 7, but it exported as 64 characters. Our own check passed while an
   independent verifier saw a broken chain — the worst possible shape, since the
   whole claim is that a third party can verify without trusting us. Now `text`
   with a hex64 `CHECK`, genesis as 64 zeros.
3. **`timestamptz` reads back in the client session's timezone.** The same
   instant is `...T09:20:54+00:00` in UTC and `...T14:50:54+05:30` in
   `Asia/Kolkata`, so hash verification would have depended on the *auditor's*
   timezone. `canonical_ts()` renders UTC with microsecond precision at both
   hash time and export time.
4. **`autocommit=True` makes `pg_advisory_xact_lock` inert.** Each statement
   became its own transaction, releasing the lock before the insert, so every
   concurrent writer collided. The lock looked correct in review and only
   surfaced under load. `append()` now holds one explicit transaction across the
   tip read and the insert.

Correctness never rested on that lock. `UNIQUE(prev_hash)` means a hash can be
claimed as a predecessor exactly once, so a fork is a constraint violation
rather than something a lock merely discourages. The lock turns loud failure
into no failure when writers contend.

## Run the API

```bash
export DATABASE_URL=postgresql://localhost/satyapramana
export SATYAPRAMANA_MIGRATE_ON_START=1
./venv/bin/uvicorn satyapramana_store.app:app --port 4000
```

`GET /capabilities` is the endpoint to open first. It reports what this
deployment can and cannot verify. Today every row reads `AWAITING_CREDENTIALS`
or `UNAVAILABLE`, so every verification returns `UNKNOWN` with a
machine-readable reason and Verification Coverage is honestly 0%. That is
rendered rather than hidden.

`GET /bidders/{id}/requirements/{rid}/provenance` is the demo: one backward walk
along `causation_id` returning verdict, fused evidence, the verification with
its raw-response reference, the extraction with page and region, and the source
document.

## The closed loop

```
POST /tenders/T1/rule-pack     adopt (human act, validated, content-addressed)
POST /tenders/T1/bidders       register, linking shared attributes
POST /bidders/A/verify         run every capability -> UNKNOWN, with reasons
POST /bidders/A/evaluate       fold evidence, fuse, decide
GET  /bidders/A                three metrics, risk, collusion
GET  /bidders/A/requirements/R4.2/provenance
```

With no credentials configured, that last call returns:

```
0  REQUIREMENT_EVALUATED    UNKNOWN
1  EVIDENCE_FUSED           GAP
2  VERIFICATION_FAILED      UNKNOWN
3  VERIFICATION_REQUESTED   PAN_STATUS
```

Four hops, and every one of them true. The trail is shorter than it will be
because no document has been ingested yet -- extraction and the source document
are the two hops still missing, and they appear as soon as there is a real
document to read. Nothing is faked to fill them in.

The metrics read `compliance_score: null`, `verification_coverage: 0.0`, and the
risk is HIGH on "mandatory requirement unverified". That is the correct answer,
not a placeholder.

## Extraction without a model

For a PDF with a text layer the whole extraction path runs with **no model
involved**. Identifiers are located by grammar, validated structurally, and
recorded with the exact page and region their characters occupy:

```
0  REQUIREMENT_EVALUATED  PARTIAL
1  EVIDENCE_FUSED         CLAIM_ONLY
2  FIELD_EXTRACTED        33AAAAA0000A1Z9  page 1  region [111.7, 71.2, 211.4, 82.2]
3  DOCUMENT_INGESTED      documents/A/b7ac1d3a-fixture.pdf
```

That is the demo axiom working with zero AI in the path, and it is the charter's
tell-tale test made concrete.

**Boxes never come from a model.** Vision models are unreliable at emitting
coordinates, so the box comes from the text layer and a model's only job is to
say *which* span is the identifier. A page with no text layer records
`EXTRACTION_FAILED` with a stated reason -- never a guessed value.

**Structural validation runs before any authority is asked.** A GSTIN carries a
check digit, a state code, and its holder's PAN in characters 3-12. An OCR
misread of one character still matches the regex, so without these checks the
system would ask an authority about a business that does not exist and record
the `NOT_FOUND` as if it meant something. A structurally invalid candidate is an
extraction problem, and is recorded as one.

**The PAN embedded in a GSTIN is cross-checked against the PAN card.** If they
disagree the two documents are not about the same legal entity, and no amount of
name similarity changes that.

> The check-digit algorithm is implemented from the published specification and
> is property-tested, but it has **not** been checked against a real GSTIN.
> Doing that needs one real registration number. Until then, treat a check-digit
> failure as a reason to look rather than as proof.

## Plugging in a real authority

Implement `verify(request) -> Success | Failure`, declare a
`CapabilityManifest`, and call `registry.register(adapter)`. It replaces the
`UnconfiguredAdapter` for the same `adapter_id` and takes over the capabilities
its manifest declares. No rule, no projection and no screen changes -- that is
the whole point of the abstraction.

## Two behaviours that differ from the service this replaces

**Collusion registration is no longer all-or-nothing.** `/backend` only
registered a bidder in the collusion graph when `director_name`, `address`,
`phone` and `bank_account` were *all* present, so one missing field silently
disabled collusion detection for that bidder. Here a bidder links on whatever
subset is present.

**Attributes are normalised per type.** `/services/collusion` compared trimmed,
lowercased strings exactly, so `+91 98765 43210` and `9876543210` were different
phone numbers -- and people concealing a link rarely format their fields
identically. Phones reduce to their last ten digits, account numbers to
alphanumerics, names and addresses to collapsed punctuation-free lowercase. The
fingerprint is salted with the attribute name, so the same digits appearing as a
phone and as an account number do not collide.

The false-positive trade is deliberate: a shared attribute is a signal for an
officer to review, never a disqualification. A false positive costs one look; a
false negative costs a missed cartel.

## Invariants

- **Nothing changes compliance state without an event.** Projections are
  rebuilt, never patched; `DELETE` against `proj_*` is correct and is precisely
  why they are separate tables from `events`.
- **Only three event types may carry a `HUMAN` actor** — `RULE_PACK_ADOPTED`,
  `VERDICT_OVERRIDDEN`, `DECISION_RECORDED`. `append()` refuses the rest.
- **An override requires a justification.** `append()` refuses one without.
- **`verdict_system` is never overwritten by an override.** Both are kept, which
  is what makes "how often did officers overturn us, and in which direction"
  answerable later.
- **Shared attribute values never enter the log** — only a hash. Events are
  immutable, so PII minimisation has to happen at emission; there is no later
  redaction.
