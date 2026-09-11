# STATUS — where the project is and what to do next

Last reviewed: 2026-09-12. Read `../CLAUDE.md` first for architecture and conventions,
then `CONTRIBUTING.md` for who owns what and how a change ships.

## Architecture direction — decided 2026-09-10, still in force

The team has a second, more ambitious spec (`satyapramana.md`, the architecture
charter). It is **not** compatible with the prompts file that originally built
this repo: it locks the stack to FastAPI / PostgreSQL and forbids MongoDB and
graph databases.

Adopted position: **charter integrity, prototype infrastructure.** Take the
charter's evidentiary properties (four-state verdicts, evidence tiers, three
orthogonal metrics, rule packs as data, honest `UNAVAILABLE`); decline unneeded
infrastructure cost (a Next.js migration was explicitly declined — Vite stays).
The Node/Express + Mongo backend was retired; the audit log is a real,
append-only, hash-chained PostgreSQL table. Collusion detection stays in
scope: edges become events, clusters are a PostgreSQL recursive-CTE
projection, so a flag survives a restart and can be audited.

Two amendments approved since, both still in force:
- **Auth was explicitly out of scope for the prototype through round 4.**
  Reversed after round 4 shipped, building toward a real officer-usable
  product rather than only a panel demo — see "Built and merged" below.
- **Tender Management** ("declined infrastructure cost" in the original
  scoping) was reconsidered for the same reason and built — see below.

---

## Built and merged, as of this review

**Zero open PRs. 547 backend tests passing** (365 `services/orchestrator` +
182 `services/core`), plus a clean `npm run build` / `npm run lint` on the
frontend. Every PR that landed this project went through the same cycle:
built with real tests, reviewed in an isolated worktree, live-verified
against a real running stack, then merged — nothing here is asserted without
having been run for real at least once.

**Core domain layer** — the four-state verdict algebra (`PASS` / `FAIL` /
`PARTIAL` / `UNKNOWN`), the three orthogonal metrics (never blended), risk
classification, the predicate evaluator, rule-pack validation. Pure,
deterministic, framework-free, frozen.

**Document pipeline** — deterministic extraction (no OCR, no model) for
GSTIN / PAN / UDYAM / CIN, PAN holder name + date of birth, GST issue/expiry
dates, and the GST certificate's *claimed* business name
(`bidder.gst.claimed_legal_name` / `claimed_trade_name`, deliberately kept
separate from the verification-sourced `bidder.gst.legal_name` so one can
never silently overwrite the other). Every extracted field carries its real
page and pixel region through to the rendered UI.

**Verification** — live for `PAN_STATUS`, `GST_STATUS`, `CIN_STATUS` via
Sandbox.co.in, gated entirely by `SATYAPRAMANA_SANDBOX_API_KEY`/`_SECRET` in
`services/orchestrator/.env` (gitignored, per-developer — see gap 2 below).
`UDYAM_STATUS` stays `AWAITING_CREDENTIALS` (confirmed: no Udyam endpoint
exists anywhere on Sandbox.co.in's platform); EPFO/ESIC are registered null
adapters with no lawful programmatic source anywhere — both are **confirmed
cut from scope**, not outstanding work.

**Auth** — real login, `hashlib.scrypt` password hashing (stdlib, no new
dependency), signed JWT sessions, three roles totally ordered
(`OFFICER` < `SENIOR_OFFICER` < `ADMIN`). Every write endpoint derives the
acting officer's identity from the authenticated session, never a
client-supplied string. No self-signup — the first `ADMIN` bootstraps from
env vars at startup; every account after that is created by an admin.
Frontend: a real login screen, protected routes, role-gated UI (a junior
officer sees an explanation instead of a form that would 403 anyway).

**Tender Management** — `POST /tenders` (title, issuing authority, bid
deadline, description), backed by a real `TENDER_CREATED` event and a
`proj_tenders` projection. Additive: a tender can still come into existence
implicitly the moment a bidder registers on a new tender ID, exactly as
before; a tender that was never explicitly created just returns honest null
metadata rather than a guess.

**The AI-assisted stages, both provider-agnostic (Gemini) and both strictly
bounded** — the model proposes, a human decides, and neither has a code path
into a verdict or an adopted rule pack that skips a person:
- **EXPLAIN** — narrates an already-final dossier into officer-readable
  prose. Unavailable with no key configured degrades to `available: false`,
  never a fabricated narrative.
- **Tender Intelligence** — reads a tender PDF's real text and proposes
  candidate requirements (text, page, an obligation guess, an optional
  suggested evidence path) for an officer to hand-review and re-enter
  through the rule pack builder. Same honest-unavailable degrade.

**Reporting** — Bid Autopsy (why a bid would fail today, with a real
counterfactual), Compliance Repair (a specific, executable action per
curable gap), the Compliance Dossier, the Tender Compliance Report, CSV
export, and a tender-wide blocker summary.

**Frontend** — design tokens and dual theme (light default, dark
first-class), the seven evidence-native primitives from charter section 2.3,
the Evidence Graph (the signature screen — a deterministic three-column DAG,
not a force-directed layout, with real pan/zoom), a PDF viewer that's a real
lightbox with page navigation, a Mission Control dashboard, an admin
officer-accounts screen, a guided rule-pack builder (replacing the old
raw-JSON textarea, with an advanced-JSON escape hatch for anything the
guided form doesn't cover), and a full round-4 interactivity pass — toast
confirmations, loading skeletons, search/filter, confirmation dialogs before
Disqualify/Override, empty states, a real audit timeline, and CSV/blocker
report actions — all wired into the real pages, not sitting unused.

---

## Built this session, NOT yet merged — needs live verification first

**→ [PR #56](https://github.com/anubrat1606/sih/pull/56) — branch
`feat/kevin-admin-tender-builder`, open against `main`, built by Kevin.**
See `docs/NEXT_TASKS_5_kevin_anubrat_suhani.md` for the full attributed
list and Anubrat's review task.

Per this file's own rule below ("nothing here is asserted without having
been run for real at least once"), the following is deliberately kept out
of "Built and merged" above: it was implemented and statically verified
(the FastAPI app imports cleanly with every new route registered, the new
Pydantic models/pure functions were exercised directly and produced correct
output, all 381 orchestrator tests — old and new — collect with zero
errors, `npm run build`/`npm run lint` are clean), but the new orchestrator
tests have **not** been run against a real PostgreSQL — Docker was not
available in that session's environment. Whoever verifies this (see
`NEXT_TASKS_5_kevin_anubrat_suhani.md`, Anubrat's lane) should run
`cd services/orchestrator && python -m pytest tests/ -q` for real, fix
anything that only shows up under a live database, and then — and only
then — fold this section into "Built and merged" above.

**The admin tender builder** (docs/COMPLETION_PLAN.md item 2, and the
checklist items 10–17 it maps to):
- Tender metadata extended: `department`, `category`, `issue_date`
  (migration `sql/007_tender_metadata.sql`, additive, old tenders read back
  as honest `NULL`).
- `POST /tenders/{tender_id}/documents` — upload the tender's own source
  PDF (separate from a bidder's compliance documents), no identifier
  extraction run against it (a tender notice isn't an ID document).
- `GET /requirement-types` — a catalog of 15 requirement types (GST, PAN,
  CIN, Udyam, document-required, turnover, net worth, ITR, experience,
  similar work, OEM authorization, certification, EPFO/ESIC, declaration,
  technical). Each type's `evidence_backed` flag is computed **live**
  against the real capability registry and extraction field list — the
  same two sources rule 8 already validates a submitted pack against, so
  this can never silently drift from what adoption will actually accept.
  Four types (GST/PAN/CIN/Udyam) come back backed with real field paths;
  the other eleven honestly come back unbacked with a stated reason —
  nothing here fabricates an evidence path.
- `POST /tenders/{tender_id}/rule-pack/validate` — dry-run validation
  (`rulepacks.validate_only()`), same rule-8-through-13 check adoption
  gates on, appends no event and writes no row.
- Frontend: tender creation form gets department/category/issue_date +
  PDF upload; the guided rule-pack builder gets a requirement-type picker
  (pre-fills a working predicate for backed types, auto-sets
  `review_required` with an honest note for unbacked ones — schema rule 11
  already refuses to adopt anything still flagged), a Validate button
  separate from Adopt, and unit/period/notes fields; Tender Intelligence
  proposals get a "Use this →" button that adds a still-`review_required`
  draft row into the builder — it still never adopts anything itself.
- Tests: `tests/test_admin_tender_builder.py` (13 tests) plus extensions to
  `test_api.py` and a new `test_decide.py` test proving adopting a new rule
  pack version never mutates an earlier version's stored body or an
  already-recorded verdict's `rule_pack_version` reference.

---

## Outstanding — in priority order

The first three need real-world input that no Claude Code session, working
alone, can supply — they were never really "buildable" tasks in the
scoping sense, and fabricating any of them would violate the one rule this
whole project refuses to break.

### 1. No real demo data

`data/consented_bidders/` does not exist yet. Nobody has pushed a real,
consented document through the live pipeline end to end. This has been the
single biggest gap between "the pieces all individually work" and "we can
actually demo it" since round 2. Need: real people/businesses who have
consented to appear in the demo, at least three bidders on one tender, two
of them genuinely sharing an attribute (director name, address, phone, or
bank account) for the collusion case to fire on real data. See
`data/README.md`.

### 2. Live credentials are per-developer, not shared

`services/orchestrator/.env` is gitignored by design — real Sandbox.co.in
and Gemini keys live only on whichever machine configured them, never in the
repo. This is correct, not a bug: without a key, every dependent feature
degrades to an honest `UNKNOWN`/unavailable state, which is itself part of
the pitch. Worth deciding, once real demo data exists: does the panel demo
run from one specific machine with keys already configured, or does whoever
demos it need their own `.env` set up beforehand?

### 3. No rule pack built from a real tender

`rulepacks/` still only has the round-2 scaffold (`README.md`,
`validate.py`) — no rule pack decomposed from an actual GeM tender PDF. The
tooling to do this is now in place (tender PDF upload, Tender Intelligence,
the requirement-type catalog, guided builder, dry-run validate) — see
"Built this session" above — but it needs, in order: (a) that work verified
against a live database, (b) a real tender PDF, (c) an officer to actually
run the workflow and adopt the result. Still not buildable end-to-end by a
Claude Code session alone.

### 4. No deployment configuration exists

Confirmed directly (not merely undocumented): no `Dockerfile`, no
`docker-compose.yml`, no hosting config anywhere in this repo. Auth/security
is done; getting the five services + Postgres + frontend running with one
command, or hosted somewhere reachable, is not.

### 5. Everything else

No other gap is currently open. If a new one turns up, it goes here with
the same rigor as 1–4: what's missing, why, and what real-world input (if
any) it needs before it's buildable.

---

## How to verify this snapshot yourself

```bash
# core — no database needed
cd services/core && ./venv/bin/python -m pytest tests/ -q   # expect 182 passed

# orchestrator — needs PostgreSQL
cd services/orchestrator
export DATABASE_URL=postgresql://localhost/satyapramana_test
./venv/bin/python -m pytest tests/ -q                        # expect 365 passed

# frontend
cd frontend && npm run build && npm run lint                 # both clean
```

`gh pr list --state merged` and `gh pr list --state open` are the ground
truth for what's actually landed versus what this file claims — trust those
over this document if they ever disagree, and update this file rather than
letting that gap grow.
