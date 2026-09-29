# STATUS — where the project is and what to do next

Last reviewed: 2026-09-28. Read `../CLAUDE.md` first for architecture and conventions,
then `CONTRIBUTING.md` for who owns what and how a change ships.

This file went stale for two weeks (rounds 7 through 10 all shipped between
the last review and this one) before being refreshed against the real,
live state below — checked against `gh pr list`, a real local test run,
and the actual deployed system's own API, not assumed from memory. If
you're reading this after another gap, the same three checks are how to
tell what's still true.

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

**696 backend tests passing** (514 `services/orchestrator` + 182
`services/core`), plus a clean `npm run build` on the frontend. Two PRs open
as of this review (#109, a performance change; #110, a documentation-only
research writeup) — `gh pr list --state open` is the ground truth for
whether they've landed by the time you read this. Every PR that landed this
project went through the same cycle: built with real tests, reviewed in an
isolated worktree, live-verified against a real running stack, then merged
— nothing here is asserted without having been run for real at least once.

**Rounds 7 through 10** (the gap this review closes) shipped, in order: a
full admin console (account directory, audit log, tender builder — round
7); the Temporal Scrubber (real event-sequence checkpoints, a pure
`fold_verdicts_as_of`/`fold_evidence_as_of` split that never risks the
live projection tables a concurrent officer's read depends on) and
deterministic financial-statement extraction for `MIN_TURNOVER`/`NET_WORTH`
(round 8); collusion made genuinely historical in the Temporal Scrubber,
self-declaration/undertaking capture (`DECLARATION`), and paise-to-rupee
currency formatting everywhere a financial figure renders (round 9); and,
after checking the actual official SIH26100 problem statement against what
was live and finding six unmet or partial points, a live `GST_RETURN_STATUS`
capability, a real DigiLocker bidder-consent flow (session → redirect →
status poll → document fetch, wired all the way into the bidder submission
UI, PS26100 point 8), five new self-declared requirement types covering
Make in India, Startup India, NSIC, OEM authorization, and blacklist/
debarment (points 5, 7, 9 — each with a real, checked reason no
verification API exists, not a placeholder), and a measured 77.6x
performance fix for the seven single-bidder read endpoints that were each
refolding every other bidder's verdicts in the deployment to answer a
question about one (round 10). See `docs/NEXT_TASKS_10_anubrat_rishika.md`
and `docs/NEXT_TASKS_10B_anubrat_rishika_sprint.md` for the real task
briefs, and `docs/ADAPTERS.md` section 11 for the current, honest
capability-by-capability state.

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

**Verification** — five live capabilities on one Sandbox.co.in account:
`PAN_STATUS`, `GST_STATUS`, `CIN_STATUS`, `GST_RETURN_STATUS` (round 10),
and `DIGILOCKER_DOCUMENT` (round 10, Aadhaar only so far — a real bidder-
consent redirect, not a lookup). Confirmed live against the real deployed
API as of this review (`GET /capabilities`, `live_count: 5`), not assumed.
`UDYAM_STATUS`, `EPFO_ESTABLISHMENT`, and `ESIC_ESTABLISHMENT` are
registered null adapters, each **confirmed** to have no lawful
programmatic source (Udyam: checked against Sandbox's own product catalog,
round 10; EPFO/ESIC: no source anywhere) — cut from scope for a real,
checked reason, not outstanding work. `ITR_FILING` is the same category:
Sandbox does have a real ITR-V API, but it requires the calling
organization itself to be a registered e-Return Intermediary with the
Income Tax Department — a legal/business registration, not a credential
this account can add. The Gemini key (`SATYAPRAMANA_GEMINI_API_KEY`) is
**not** configured on the live Render deployment as of this review — EXPLAIN
and Tender Intelligence both correctly degrade to `available: false` there
rather than fabricating anything, but nobody has actually seen either one
narrate a real dossier live yet.

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
- `GET /requirement-types` — a catalog, originally 15 types, now **20** as
  of round 10 (checked directly against the live catalog, not assumed):
  GST, PAN, CIN, Udyam, DigiLocker/Aadhaar, document-required, turnover,
  net worth, ITR, experience, similar work, OEM authorization, Startup
  India, NSIC, Make in India, blacklist/debarment, certification,
  EPFO/ESIC, declaration, technical. Each type's `evidence_backed` flag is
  computed **live** against the real capability registry and extraction
  field list — the same two sources rule 8 already validates a submitted
  pack against, so this can never silently drift from what adoption will
  actually accept. **13 of the 20** come back backed with a real evidence
  path today (GST/PAN/CIN/Udyam/DigiLocker-Aadhaar via extraction or a live
  capability; turnover/net worth via financial-statement extraction;
  declaration and the five round-10 self-declared types via round 9's
  attestation mechanism); the remaining 7 (ITR, experience, similar work,
  certification, EPFO/ESIC, plus the intentionally generic document-
  required and technical) honestly come back unbacked with a stated
  reason — nothing here fabricates an evidence path.
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

The first two need real-world input that no Claude Code session, working
alone, can supply — they were never really "buildable" tasks in the
scoping sense, and fabricating either would violate the one rule this
whole project refuses to break.

### 1. Real demo data exists now, but collusion has never fired on it

**Partially resolved, checked live as of this review, not assumed.** The
live deployment has 3 real tenders and 3 real bidders with real evaluated
verdicts — `BHEL-T7J1Z68239` (the real GeM tender from round 5) carries two
real bidders, `ANUBRAT-DAS` and `GST-BIDDER-01`, both currently `HIGH`
risk; `GST-VERIFY-TEST` carries one, `GSTIN-TEST-1`, `LOW` risk. This is
real progress since the last review — the pieces have genuinely been run
end to end against real data, not just individually.

What's still missing, precisely: none of the three real bidders share an
attribute with another, so `flagged_bidder_count` is honestly `0` — the
collusion detector has never fired on real data, only on synthetic test
fixtures. Closing this needs one more real, consenting bidder registered
on `BHEL-T7J1Z68239` (or a new tender) who genuinely shares a director
name, address, phone, or bank account with `ANUBRAT-DAS` or
`GST-BIDDER-01` — a real-world-input gap, same as before, just narrower
than it was.

### 2. Live credentials are shared for Sandbox.co.in, not yet for Gemini

**The Sandbox.co.in half is resolved**, confirmed live as of this review:
`SATYAPRAMANA_SANDBOX_API_KEY`/`_SECRET`/`_ENV=live` are all set on the
shared Render backend (`GET /capabilities` shows `live_count: 5` from the
public internet, not a local `.env`) — a shared Neon Postgres plus this
shared Render deployment means nobody needs their own Sandbox credentials
just to use the running app.

Still open: `SATYAPRAMANA_GEMINI_API_KEY` is not set on the live
deployment (checked directly against Render's env-var list, not assumed)
— correct, not a bug, since EXPLAIN and Tender Intelligence both honestly
degrade to `available: false` without it, rather than faking a narrative.
Worth deciding: does the team add one real shared key to Render's env vars
(same place the Sandbox credentials already live), or does this stay
per-developer for local work only?

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
refused adoption at the time (rule 8: no evidence path; rule 11:
`review_required`) — documented in the PR, not silently dropped. Updated
as of this review: turnover and net worth got a real, deterministic
evidence path in round 8 (`extract/financials.py`); declarations got real
capture in round 9 (`DECLARATION`). What's still genuinely unbacked today
— checked directly, not assumed — is `EXPERIENCE`, `SIMILAR_WORK`, and
`CERTIFICATION`: no extraction path or verification API exists for any of
the three, and unlike round 10's five new self-declared types, none of
these three have been given even a self-declared path yet. A real,
specific residual gap, narrower than it was, not closed.

### 3. Deployment — Docker declined (still the right call), but document storage is a real, recurring, currently-broken problem

Docker itself was declined (see "Architecture direction" above) in favor
of a Render Blueprint (`render.yaml`) running the orchestrator and
frontend as two free services against the shared Neon database — that
part is resolved and stays resolved, see `docs/DEPLOYMENT.md` for setup.

**Not resolved, and actively broken again as of this review, checked
live, not assumed:** uploaded document files live on the orchestrator's
local disk (`storage_ref` in `DOCUMENT_INGESTED`), and Render's free
tier gives that service an *ephemeral* filesystem — every redeploy wipes
it. `render.yaml` auto-deploys on every push to `main`, so **any** merge
— a doc fix, a CSS change, anything — silently deletes every previously
uploaded document, while the hash-chained event log keeps referencing
the now-missing file forever (the reference cannot be repaired unless a
byte-identical re-upload happens to land, which only works as a stopgap,
not a fix). Confirmed live right now: `GET /documents/{sha256}` 404s
with `"the event log references this document, but it is not on disk
here"` for both real bidders' documents — re-uploaded once already this
sprint, silently wiped again by at least three merges since.

This is not cosmetic. It means an officer's decision, once made off a
document, can permanently lose the ability to be independently
re-verified by clicking through to the original page — directly
undercutting the charter's own "provenance to the pixel" claim, the
single most load-bearing promise this product makes to a judge.

Real fix options, by effort (not yet decided as of this review):
1. **Object storage** (Cloudflare R2 or Backblaze B2, both have a real
   free tier) — swap the local-disk read/write path for an S3-compatible
   client; survives every redeploy permanently. Needs a new account and
   credentials, the same category of decision as the Gemini key.
2. **Render persistent disk** — less code, but a real recurring cost;
   the team has already declined paid infrastructure elsewhere (no
   Docker, no Next.js), so this would be a deliberate, stated exception,
   not a default.
3. **Re-upload right before any screenshot/demo, zero pushes in
   between** — not a fix, a timing workaround; what's unblocked every
   screenshot so far, and will keep recurring exactly this way until 1
   or 2 actually happens.

### 4. Everything else

No other gap is currently open beyond what's named above (real demo data
for collusion, the Gemini key, document storage, and
`EXPERIENCE`/`SIMILAR_WORK`/`CERTIFICATION`). If a new one turns up, it
goes here with the same rigor
as 1–3: what's missing, why, and what real-world input (if any) it needs
before it's buildable.

---

## How to verify this snapshot yourself

```bash
# core — no database needed
cd services/core && ./venv/bin/python -m pytest tests/ -q   # expect 182 passed

# orchestrator — needs PostgreSQL
cd services/orchestrator
export DATABASE_URL=postgresql://localhost/satyapramana_test
./venv/bin/python -m pytest tests/ -q                        # expect 514 passed
                                                              # (more once #109 merges)

# frontend
cd frontend && npm run build && npm run lint                 # both clean

# the live deployment itself — ground truth beats any file, this one included
curl -s https://sih26100-orchestrator.onrender.com/health
curl -s https://sih26100-orchestrator.onrender.com/capabilities \
  -H "Authorization: Bearer <a real token from /auth/login>" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['live_count'])"
                                                              # expect 5
```

`gh pr list --state merged` and `gh pr list --state open` are the ground
truth for what's actually landed versus what this file claims — trust those
over this document if they ever disagree, and update this file rather than
letting that gap grow. The live deployment is the ground truth for what a
judge or officer actually sees; a passing local test suite proves the code
is correct, not that the deployed system reflects it — check both.
