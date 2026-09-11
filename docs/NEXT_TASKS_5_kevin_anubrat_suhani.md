# Next tasks, round 5 — verify, then go end-to-end for real

**Read this whole file before writing any code or touching the running app.
Paste only your own section, plus "Where this round sits," "Merge approval,"
"File ownership this round," and "Hard rules" into your own fresh Claude
Code session — it has no memory of this conversation, so everything it
needs is written down here.**

Read `STATUS.md` first (what's actually built, and what "Built this
session, NOT yet merged" means right now), then `docs/COMPLETION_PLAN.md`
(the fuller gap list this round closes out), then `CONTRIBUTING.md` (file
ownership and the branch/PR workflow — still in force, extended below for
this round's new areas).

## Where this round sits

Round 4 shipped the frontend interactivity pass. Since then, a Claude Code
session built the admin tender builder (tender metadata fields, tender PDF
upload, the requirement-type catalog, dry-run rule-pack validation, and the
frontend wiring for all of it) — see `STATUS.md`'s "Built this session, NOT
yet merged" section for the exact file list. **That work has not been run
against a live PostgreSQL and has not gone through review or a PR.** It was
only statically verified (imports cleanly, the new pure functions were
exercised directly, all tests collect with no errors, frontend build/lint
clean) because Docker wasn't available in that session's environment.

This round has one hard sequencing rule as a result: **the app itself is
not provably working yet.** Round 5's real goal — a genuine tender with a
real rule pack, real consented bidders, and the collusion case firing on
real (not fabricated) shared data — cannot start until that verification
happens. See Anubrat's section below; it's first for a reason, not because
his work matters more.

**Also worth knowing before you start:** the working copy this was built
against (`anubrat/sih-main/` on this machine) is a snapshot, not a git
clone — there's no `.git` here. The real repo is
`https://github.com/anubrat1606/sih.git` per `CONTRIBUTING.md`. Whoever
picks up Anubrat's verification task should diff this snapshot's changed
files against a real clone of `main`, apply them there, and go through the
real branch/PR flow — not commit directly from this folder.

## Merge approval — unchanged from round 4

**Nobody merges their own work, ever, under any circumstance.** Open your
PR against `main`, make sure CI is green, and stop. Anubrat reviews and
merges every PR — this round included his own; a second reviewer per
`CONTRIBUTING.md`'s existing rule still applies. A green CI run is a
necessary condition for review, not a substitute for it.

## File ownership this round

`CONTRIBUTING.md`'s table is still authoritative; this only fills in the
areas it left unassigned (`rulepacks/`, `data/` — previously held by
Paridhi, who isn't on this round) and confirms who's touching what so
nobody's branch conflicts with anybody else's:

| Path | Owner this round | Note |
|---|---|---|
| `services/orchestrator/satyapramana_store/{app,rulepacks,projections}.py`, `requirement_types.py` (new) | **Anubrat** | Already his under `CONTRIBUTING.md` ("ask before editing" / sole owner of top-level orchestrator `*.py`) — this round's job is reviewing and live-verifying the admin-builder changes already sitting in these files, not writing new ones |
| `services/orchestrator/satyapramana_store/extract/` (incl. `ingest.py`) | **Suhani** | Already hers, unchanged |
| `data/consented_bidders/` (new) | **Suhani** | Real, consented bidder documents/details — see her section |
| `rulepacks/*.json` (new files only — never `README.md` or `validate.py`) | **Kevin** | New to this codebase this round — scoped to new JSON files only, zero risk of touching anyone's source |
| New deployment files: `docker-compose.yml`, `services/*/Dockerfile`, `docs/DEPLOYMENT.md` (new) | **Anubrat** | Brand new paths, doesn't intersect anyone else's files |
| `docs/*.md` | Shared | Append to your own section only, exactly as `CONTRIBUTING.md` already says |

Nobody this round touches `frontend/` (existing pages), `services/core/`,
or `schemas/` — no task below needs it.

## Hard rules — same five as always

1. No mock, sample, or simulated data anywhere, including in anything that
   doubles as a demo. A check that can't be performed returns `UNKNOWN`
   with the real reason.
2. No model ever makes a final determination. AI proposes (Tender
   Intelligence, EXPLAIN); deterministic code decides.
3. Nothing changes state except by appending an event.
4. Every change ships with a test, and the suite stays green.
5. Secrets live in `.env`, never in a commit.

Two more, specific to this round:

6. **No fabricated tender requirement and no fabricated bidder.** Kevin's
   rule pack must come from a real, findable tender document. Suhani's
   bidders must be real people/businesses who consented — see her section
   for exactly what "consent" needs to mean here.
7. **The requirement-type catalog's `evidence_backed: false` types (minimum
   turnover, net worth, ITR, experience, similar work, OEM authorization,
   certification, EPFO/ESIC, declaration) stay `review_required: true` in
   any rule pack you build.** Don't invent an evidence path to make one of
   these adoptable — if a real tender needs one of these checks and it
   can't be evaluated today, that's an honest, flagged gap, not something
   to route around.

---

## Anubrat — verify, review, and give the other two something real to build on

**Goal:** turn "Built this session, NOT yet merged" into actually merged,
live-verified work, then make the whole system runnable with one command.

### Part 1 — live-verify and merge the admin tender builder

1. Get PostgreSQL running locally (`CONTRIBUTING.md`'s setup section still
   applies) — or get Docker working, whichever's faster on your machine.
2. Diff this session's changes against a real clone of `main`:
   `services/orchestrator/satyapramana_store/app.py`, `rulepacks.py`,
   `projections.py`, `requirement_types.py` (new), `sql/007_tender_metadata.sql`
   (new), `tests/test_admin_tender_builder.py` (new), the edits to
   `tests/test_api.py` and `tests/test_decide.py`, and the frontend changes
   to `RulePackBuilder.jsx`, `TenderIntelligence.jsx`,
   `pages/TendersPage.jsx`, `pages/TenderDashboardPage.jsx`, `api.js`.
   Apply them to your clone, on a branch.
3. Run `cd services/orchestrator && python -m pytest tests/ -q` for real.
   Fix anything that only surfaces against a live database — the migration
   (`007_tender_metadata.sql`) and the `projections.py` fold are the two
   places most likely to have a real bug hiding behind "it imports fine."
4. Sanity-check the one design call worth a second opinion: `rulepacks.py`'s
   `validate_only()` was factored out of `adopt()` so the new
   `/rule-pack/validate` endpoint and the real adoption path share one
   validation code path, never two. Confirm that's actually true by reading
   both call sites, not just trusting the docstring.
5. Run `npm run build && npm run lint` in `frontend/` — already clean as of
   this session, confirm it still is after any backend changes you make.
6. Open the PR, get it reviewed, merge it. Update `STATUS.md`: fold the
   "Built this session" section into "Built and merged" once it's real.

### Part 2 — deployment

`STATUS.md` gap 4: no `Dockerfile`, no `docker-compose.yml`, nothing.

1. A `Dockerfile` per service that needs one (`services/core` as a library
   dependency, not its own container; `services/orchestrator` +
   `frontend`'s build output are the two that actually need to run).
2. A `docker-compose.yml` wiring orchestrator + Postgres + the built
   frontend, so `docker compose up` is the whole story for anyone trying
   this without reading five READMEs first.
3. `docs/DEPLOYMENT.md`: what env vars are required vs. optional, and what
   degrades honestly (not silently) when a credential is missing.
4. Decide and document `STATUS.md` gap 2 (the demo-credentials question) —
   one shared demo machine, or per-developer `.env`. This is a team call,
   not a technical one; just make sure it's written down before Kevin and
   Suhani need real Sandbox.co.in / Gemini keys to run their parts for real.

**Done when:** the merged suite passes for real against Postgres, `docker
compose up` brings up a working system from nothing, and Kevin/Suhani both
have a running app to point their real tender/real bidders at.

---

## Kevin — a real tender, decomposed and adopted for real

**Goal:** close `STATUS.md` gap 3. One real, adopted rule pack, for one real
tender, built entirely through the admin builder Anubrat just verified —
never by hand-writing JSON from scratch, never by inventing a requirement
that isn't actually in the source document.

**Depends on:** Anubrat's Part 1 landing first — you need a real,
running, tested orchestrator to do any of this against.

1. Find a real, public tender PDF — GeM, CPCL, or any government
   e-procurement portal's public notices work; it doesn't need to be for
   your own organization, it needs to be real.
2. Create the tender (`POST /tenders` via the Tenders page) with its real
   title, issuing authority, department, category, and dates.
3. Upload the PDF via the tender's own page ("Upload tender PDF").
4. Run Tender Intelligence against it. For each proposal you agree with,
   click "Use this →" — it lands as a draft row in the builder, still
   flagged `review_required`, exactly as it should until you've checked it
   against the actual source page.
5. For each draft: pick a requirement type from the picker where one
   genuinely fits (this pre-fills a real, working check for GST/PAN/CIN/
   Udyam-shaped requirements). For anything the catalog marks as having no
   live evidence source — turnover, net worth, ITR, experience, past
   performance, OEM authorization, certifications, EPFO/ESIC, declarations
   — fill in what the tender actually requires as a note, leave
   `review_required` checked, and move on. That's the honest, correct
   outcome for those, not a bug to fix.
6. Click **Validate**. Fix whatever it flags. Validate again until clean
   (for the requirements you intend to actually adopt — the flagged ones
   stay flagged, and that's fine, `review_required` items simply can't be
   part of an adopted pack yet per rule 11).
7. Click **Adopt** as a SENIOR_OFFICER-or-higher account, with your real
   identity.
8. Save the exact JSON the builder submitted as `rulepacks/<rule_pack_id>.json`
   — this is your one committed deliverable, a new file, zero conflict
   with anyone else's work.

**Test:** none of your own to write — this is exercising Anubrat's
already-tested API for real, not adding new code. If you hit a bug in the
builder or the API while doing this, that's real, valuable signal: file it
precisely (what you did, what you expected, what happened) rather than
working around it, and hand it back to Anubrat.

**Done when:** `rulepacks/<id>.json` exists, is real, and
`GET /tenders/{your_tender_id}` plus `GET /tenders/{your_tender_id}/blockers`
show it actually adopted and live.

---

## Suhani — real consented bidders, pushed through the real pipeline

**Goal:** close `STATUS.md` gap 1, using your existing ownership of
`services/orchestrator/satyapramana_store/extract/` to also close the one
small technical item still open there.

**Depends on:** Anubrat's Part 1 landing first, same as Kevin — and ideally
Kevin's tender existing too, so your bidders register against a real
tender with a real rule pack rather than a bare tender ID.

### Part 1 — the byte-hashing audit (`COMPLETION_PLAN.md` §3.5)

A specific, narrow thing to confirm in your own directory: content hashing
for an *uploaded document* (a binary PDF or image) must hash raw bytes
directly, never route through a hasher built for JSON text canonicalization.
Read `store_document()` and `compute_document_hash`-equivalent code in
`extract/ingest.py` and confirm this is actually true today. If it already
is, this is a five-minute check, done. If it isn't, fix it — it's your file,
your call, no need to ask.

### Part 2 — real consented bidder data

1. Recruit at least three real, consenting people or businesses —
   teammates, family, willing volunteers. They need to understand their
   real PAN/GST/Udyam documents will be used in an internal team demo, and
   agree to that specifically (not a blanket "sure, whatever").
2. At least two of the three need to genuinely share one real attribute —
   director name, address, phone, or bank account — so the collusion case
   has something real to fire on. Don't construct this artificially; pick
   people/businesses where it's already true (e.g. two sole proprietorships
   run by the same person, or two firms at the same registered address).
3. Collect their documents into `data/consented_bidders/bidder_A/`,
   `bidder_B/`, `bidder_C/` per the existing `data/README.md` format.
   **Do not commit this to a public remote** — `data/` is already
   gitignored; keep it that way and share within the team through a
   private channel, exactly as `data/README.md` already says.
4. Register each as a bidder (ideally on Kevin's real tender, once it
   exists), upload their real documents, run verify.
5. If a rule pack is adopted on that tender, evaluate each bidder for real
   and confirm the collusion flag actually fires on the pair that shares
   an attribute — this is the first time anyone will have seen that happen
   against real data instead of a unit-test fixture.

**Test:** if the hashing audit needs a fix, it needs a test in
`extract/`'s existing test file, matching whatever pattern the file
already uses for that grammar/function. The bidder data itself isn't code
and needs no test — it's the input the rest of the system's existing tests
already cover.

**Done when:** three real bidders exist in the running system with real
uploaded documents, at least one collusion pair fires for real, and
`data/consented_bidders/` documents exactly who consented to what (a short
note per bidder is enough — this doubles as your own record that consent
was real, not assumed).

---

## After all three land

This is explicitly **not** anyone's task to start yet — it's what becomes
possible once Anubrat, Kevin, and Suhani's work all exist together on one
real tender: a genuine end-to-end run (`STATUS.md`/`COMPLETION_PLAN.md`
items 24 and 26), and only then the demo script / presentation polish
(item 27). Whoever picks that up next should open a new `NEXT_TASKS_6`
file rather than improvising it — same discipline, same reason it's worked
every round so far.
