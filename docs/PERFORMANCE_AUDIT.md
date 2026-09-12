# Backend performance audit — 2026-09-12

## Where this came from

Kevin forwarded a performance-optimization task over WhatsApp, attributed to
him. Before acting on it, it was checked against the real codebase (the same
verification this project applies to anything arriving outside the normal
branch/PR process) and it described a stack this project doesn't have:
**SQLAlchemy** (this project has no ORM at all -- `db.py`'s own top comment
explains why: "an ORM here would put a layer between the audit claim and
what runs") and **Next.js** (the frontend is React + Vite; a Next.js
migration was explicitly declined earlier this round, see `STATUS.md`'s
Architecture direction section). That original document was not saved here,
since it would misdescribe the real architecture for anyone reading this
later.

The underlying ask -- profile before modifying, fix the real bottleneck,
change nothing about existing behavior -- was legitimate and worth doing.
This file is that audit, done against the real stack: FastAPI, raw
`psycopg` (no ORM), PostgreSQL (Neon), React + Vite.

## Root causes found, in order of impact

### 1. Every request opened a brand-new database connection

`app.py`'s `db()` dependency called `connect()` -- a fresh
`psycopg.connect()` -- and closed it at the end of every single request,
across all 34 route handlers that touch the database. No pooling existed
anywhere (`psycopg_pool` wasn't even a dependency). Opening a Postgres
connection is a real, measurable cost (TCP + TLS + auth negotiation), paid
on every request, made worse by the database being remote (Neon), not
local.

**Fix:** `db.py` now owns a `psycopg_pool.ConnectionPool`, opened once at
app startup (`open_pool()` in `app.py`'s `lifespan`) and closed at shutdown.
The `db()` dependency checks a connection out of the pool per request and
returns it (not closes it) when the request ends. Every route's own code is
unchanged -- they all receive the same kind of connection object as before,
just pooled instead of freshly opened.

**Measured** (local Postgres, 50 requests -- a remote Neon connection would
show a much larger absolute gap, since network + TLS round-trip time is
the dominant cost being eliminated):
- Before: 3.15ms/request (open + query + close each time)
- After: 0.13ms/request (checkout + query + return)
- **23.4x**

### 2. Two upload endpoints blocked the entire server during every upload

`POST /bidders/{id}/documents` and `POST /tenders/{id}/documents` were
declared `async def` so they could `await file.read()`, but then called
blocking, synchronous work inside that same async function: database
queries and, for the bidder endpoint, CPU-bound PDF parsing (`pdfplumber`).
FastAPI only offloads a route to a worker thread automatically when the
route itself is a plain `def`, not `async def` -- so all of that blocking
work ran directly on the shared event loop, freezing every other concurrent
request on the same server for its duration.

**Fix:** both routes are now plain `def` (FastAPI runs a sync route in its
own worker thread automatically), and `await file.read()` became
`file.file.read()` -- the synchronous equivalent, same bytes, correct now
that the whole function runs off the event loop.

**Measured** (uploading the real 71-page BHEL tender PDF used elsewhere in
this project, while hammering `GET /health` concurrently on the same
single-process server):
- Before: worst `/health` response during the upload took **7397ms** (the
  whole server hung for the entire parse+DB duration)
- After: worst response was **139ms**
- The remaining ~50-140ms (vs. ~1ms when idle) is expected -- CPU-bound
  PDF parsing in a worker thread still contends for the GIL with the main
  thread; that's a fundamentally different, much smaller problem than the
  server going fully unresponsive.

### 3. `GET /dashboard` and `GET /tenders/{id}/bidders` re-ran a full event-log rebuild once per bidder (and, on the dashboard, once per tender)

`rebuild_projections()` is expensive by design: it deletes and re-folds
`proj_verdicts`, `proj_collusion`, and `proj_tenders` from the *entire*
`events` table, for *every* tenant, not just one. `get_bidder()` called it
on every single invocation, and `list_tender_bidders()` called `get_bidder()`
once per bidder in a loop -- so a tender with N bidders re-ran a full
system-wide projection rebuild N times for one page load. The dashboard
compounded this further: it calls the bidder list once per tender in the
whole system, so with M tenders it ran a full rebuild M times over, on top
of whatever each tender's own bidder count added.

The same pattern also duplicated `active_pack()` and `collusion_clusters()`
calls once per bidder, even though both are scoped to the tender, not the
bidder, and are therefore identical for every bidder on it.

**Fix:** the per-bidder computation was split out of `get_bidder()` into
`_bidder_snapshot()`, which takes the tender's active pack and collusion
clusters as arguments instead of re-fetching them. `list_tender_bidders()`
(and its non-rebuilding variant `_list_tender_bidders()`, used by the
dashboard) now fetches the pack and clusters exactly once per request and
passes them to every bidder's snapshot. The dashboard calls
`rebuild_projections()` exactly once at the top of the request, then uses
the non-rebuilding variant per tender. The same split was applied to
`bidder_autopsy()` / `_bidder_autopsy_result()` for `tender_blockers()`'s
loop. No response shape changed anywhere -- this only removes redundant
recomputation of the same answer.

**Measured** (local Postgres):
- `GET /tenders/{id}/bidders`, 15 bidders: 52.4ms -> 11.7ms avg (**4.5x**)
- `GET /dashboard`, 5 tenders x 5 bidders (25 total): 88.6ms -> 15.9ms avg
  (**5.6x**)
- Both gaps widen as the system's total event-log history grows over time,
  since the eliminated work scaled with *all* history ever recorded, not
  just the tenant being viewed.

## Files changed

- `services/orchestrator/satyapramana_store/db.py` -- added the connection
  pool (`open_pool`/`close_pool`/`get_pool`), kept `connect()` for one-off,
  non-request work (startup migration, the test suite's own fixtures).
- `services/orchestrator/satyapramana_store/app.py` -- `lifespan` opens/closes
  the pool; `db()` checks out/returns a pooled connection; the two upload
  routes are sync `def` instead of `async def`; `get_bidder`,
  `list_tender_bidders`, `bidder_autopsy`, `tender_blockers`, and
  `dashboard` were restructured to compute tender-scoped data once per
  request instead of once per bidder (or once per tender, for the
  dashboard) -- see the inline comments at each site for the specific
  reasoning.
- `services/orchestrator/requirements.txt` -- added `psycopg_pool>=3.2`.

No SQL migration, no schema change, no new infrastructure (no Redis,
Celery, Kafka, or a second database), no frontend change, and no response
shape changed for any endpoint.

## Not changed

- **Indexes** -- none added. Every slow path found was redundant
  application-level work (opening connections, blocking the event loop,
  re-running a full rebuild), not a missing index; adding one without a
  query pattern that needs it would be exactly the "add indexes blindly"
  this audit was told not to do.
- **Pagination** -- `list_tenders` and `list_tender_bidders` return
  everything unpaginated. Left alone: with the N+1/rebuild fix above, the
  actual cost of returning more rows is now proportional to the real work
  (one query per bidder for that bidder's own verdicts), not a multiplier
  on the most expensive operation in the system. Worth revisiting if a
  tenant ever has hundreds of bidders, not before.
- **`ProjectionResolver`'s own internal queries** (used once per bidder
  inside `_bidder_snapshot`) -- not profiled in this pass. It's genuinely
  per-bidder work (each bidder's own evidence), unlike the tender-scoped
  calls this audit removed from the loop, so it wasn't the same class of
  bug -- flagged here in case it's worth a closer look later, not fixed now.

## Tests

`services/orchestrator`: **381 passed**. `services/core`: **182 passed**.
Both runs are against a real PostgreSQL (`satyapramana_test`), same as
every other change in this project -- the tests bypass the `db()`
dependency entirely via `app.dependency_overrides`, so they don't exercise
the pool directly, which is why every fix above was also measured
separately against a real running instance rather than trusted from test
results alone.

## Remaining bottlenecks not addressed here

- Bundle size on the frontend (964kB, now 845kB after the PR #64 redesign)
  -- a separate, frontend-side concern, out of scope for this backend-only
  pass.
- Neon's free-tier auto-suspend after inactivity means the first request
  after idle time will still be slow (a cold compute start), independent
  of anything in this codebase -- an infrastructure characteristic, not a
  bug.
