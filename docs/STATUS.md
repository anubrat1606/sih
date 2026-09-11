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

Three amendments approved since, all still in force:
- **Auth was explicitly out of scope for the prototype through round 4.**
  Reversed after round 4 shipped, building toward a real officer-usable
  product rather than only a panel demo — see "Built and merged" below.
- **Tender Management** ("declined infrastructure cost" in the original
  scoping) was reconsidered for the same reason and built — see below.
- **Decided 2026-09-12: no Docker.** Round 5's task list proposed a
  `Dockerfile` per service plus a `docker-compose.yml`. Declined —
  unneeded infrastructure cost for a hackathon prototype, same reasoning as
  the Next.js decline above. If a later round genuinely needs a
  one-command reproducible environment, revisit then; nobody should build
  this speculatively in the meantime.

## Database access — decided 2026-09-12

Not everyone can get a local PostgreSQL running (no admin rights, an
unfamiliar OS, a locked-down sandbox — this is exactly what blocked Kevin
from live-verifying PR #56 before opening it). Rather than Docker, the
team uses **one shared Neon Postgres project** (neon.tech, free tier,
standard Postgres wire protocol) as the simplest fix that needs no local
install and works from any machine:

- Ask Anubrat for the connection string — shared over a private channel,
  **never committed** — and paste it as `DATABASE_URL` in your own
  `services/orchestrator/.env`, keeping its `?sslmode=require` suffix.
- A local Postgres still works exactly as before for anyone who has one;
  the shared project is only for whoever doesn't. Nothing about how the
  app runs changes either way — see `CONTRIBUTING.md`'s Setup section.
- Free-tier Neon auto-suspends after inactivity; the first request after
  a while just takes a couple of seconds to wake it back up. Not a bug.
- This resolves the *database* half of gap 2 below. The Sandbox.co.in /
  Gemini credentials half is still an open, separate decision.

---

## Built and merged, as of this review

**Zero open PRs. 563 backend tests passing** (381 `services/orchestrator` +
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

**The admin tender builder** ([PR #56](https://github.com/anubrat1606/sih/pull/56),
built by Kevin — `docs/COMPLETION_PLAN.md` item 2, checklist items 10–17).
Live-verified for real before merge: 381/381 orchestrator tests passing
against a real PostgreSQL (not just statically imported), the tender
document upload actor-kind bug fixed and confirmed live end to end, dry-run
validate confirmed to append no event on either a rejected or an accepted
pack.
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

**Partially resolved 2026-09-12.** The *database* half of this is
resolved — see "Database access" above and `docs/DEPLOYMENT.md`: a shared
Neon Postgres plus a shared Render deployment means nobody needs a local
Postgres or their own `.env` just to use the running app.

Still open: real Sandbox.co.in and Gemini keys live only on whichever
machine (or Render service) configured them, never in the repo — correct,
not a bug, since without a key the dependent feature honestly degrades to
`UNKNOWN`/unavailable rather than faking a result. Worth deciding once
real demo data exists: does the team share one real key pair (entered
once into the Render service's env vars, per `docs/DEPLOYMENT.md`), or
does each developer need their own for local work?

[PR #59](https://github.com/anubrat1606/sih/pull/59), merged: Kevin ran a
real GeM tender (BHEL, Enquiry No. T7J1Z68239, "Supply of Metallic
Expansion Joints," sourced live from GeM's public catalog document store)
through the full live admin builder flow and adopted a real rule pack —
`rulepacks/bhel.t7j1z68239.metallic-expansion-joints.json` — 3 requirements
(GST, PAN, Udyam), all evidence-backed. Independently re-verified before
merge, not just trusted: the source PDF's SHA-256 was recomputed from a
fresh download and matched exactly; the pack's `content_hash` was
recomputed from the committed file and matched the live
`RULE_PACK_ADOPTED` event exactly; every quoted requirement text was
checked against the actual PDF page and matched verbatim.

5 more real requirements from the same tender (turnover, experience,
certification, two declarations) were drafted, validated, and correctly
refused adoption (rule 8: no evidence path; rule 11: `review_required`) —
documented in the PR, not silently dropped. That residual gap (no evidence
path for turnover/experience/certification/declarations anywhere in this
system) is real and still open, but it's a capability gap now, not a
"nobody has tried this with real data yet" gap.

### 4. Deployment — resolved 2026-09-12, no Docker

Docker was declined (see "Architecture direction" above) in favor of a
Render Blueprint (`render.yaml`) running the orchestrator and frontend as
two free services against the shared Neon database — see
`docs/DEPLOYMENT.md` for the one-time setup and its one honest limitation
(uploaded document files don't survive a redeploy on Render's free tier;
the event log itself always does).

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
./venv/bin/python -m pytest tests/ -q                        # expect 381 passed

# frontend
cd frontend && npm run build && npm run lint                 # both clean
```

`gh pr list --state merged` and `gh pr list --state open` are the ground
truth for what's actually landed versus what this file claims — trust those
over this document if they ever disagree, and update this file rather than
letting that gap grow.
