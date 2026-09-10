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
