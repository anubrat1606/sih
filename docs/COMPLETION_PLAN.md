# Completion plan — what's left before this is demo-ready

Last reviewed: 2026-09-12, cross-checked against the live code (not just
`STATUS.md`'s claims) — `services/orchestrator/satyapramana_store/extract/grammars.py`
was read directly to confirm GSTIN/PAN/CIN structural validation is real and
live, `.github/workflows/ci.yml` was read to confirm what CI actually runs,
and `data/`, `rulepacks/` were confirmed empty by design, not by accident.
Read `STATUS.md` first — this file expands its "Outstanding" section into
concrete next actions and maps it against the fuller feature checklist below.

**Update, same day:** the admin tender builder (item 2 below, and checklist
items 10–17) has since been implemented — see `STATUS.md`'s "Built this
session, NOT yet merged" section. It is **not** re-scoped as a remaining
gap below; §3.2 below is updated to reflect that the tooling now exists,
and the actual work of running it for real is assigned out in
`NEXT_TASKS_5_kevin_anubrat_suhani.md`.

---

## 1 · Snapshot — what's already built and verified

Not re-litigated here in detail; see `STATUS.md` for the full list. In brief,
all of the following are built, merged, and covered by the 547 passing tests
(182 `services/core` + 365 `services/orchestrator`) plus a clean frontend
build/lint:

- Core domain layer — verdict algebra, three metrics, risk classification,
  predicate evaluator, rule-pack validation
- Document pipeline — deterministic GSTIN/PAN/UDYAM/CIN extraction with real
  page/pixel evidence, GSTIN check-digit + state-code + PAN-embedded
  cross-check, PAN holder name/DOB, GST dates, claimed business name
- Live verification — PAN/GST/CIN via Sandbox.co.in (`adapters/sandbox_co_in.py`)
- Auth — JWT sessions, three roles, admin bootstrap
- Tender management — `POST /tenders`, real event + projection
- AI-assisted EXPLAIN and Tender Intelligence (Gemini, honest-unavailable degrade)
- Reporting — Bid Autopsy, Compliance Repair, Compliance Dossier, Tender
  Compliance Report, CSV export, blocker summary
- Frontend — dual theme, evidence-native primitives, Evidence Graph, PDF
  lightbox viewer, Mission Control dashboard, admin screen, guided rule-pack
  builder, round-4 interactivity pass (toasts, skeletons, search/filter,
  confirmations, audit timeline)
- CI — `services/core` tests, `services/orchestrator` tests against a real
  Postgres service container, `frontend` build + lint, on every PR to `main`

## 2 · Checklist cross-reference

Mapping your feature checklist against what's actually in the code (not
just claimed):

| # | Item | Status |
|---|---|---|
| 10 | GST Document Intelligence (upload → extract → page evidence → validate) | **Done** |
| 11 | Tender document intelligence | **Done** (Tender Intelligence, human-reviewed) |
| 12 | Bidder/document intelligence | **Done** |
| 13 | Entity Resolution | **Partial** — PAN-embedded-in-GSTIN cross-check exists; confirm it also covers the collusion-relevant signals (shared director/address/phone/bank account) — see §3.1 |
| 14 | Evidence Fusion | **Done** — `FUSE` stage per `docs/ADAPTERS.md` |
| 15 | Compliance Rule Engine integration | **Done** |
| 16 | Temporal Compliance (validity/expiry/as-of) | **Done** — recency factor + freshness_days in metrics/capability manifest |
| 17 | Full Compliance Dashboard | **Done** |
| 18 | Risk Engine + Compliance Score | **Done** |
| 19 | Bid Autopsy | **Done** |
| 20 | Compliance Repair | **Done** |
| 21 | Evidence Graph | **Done** |
| 22 | Audit Trail UI | **Done** |
| 23 | Reporting | **Done** |
| 24 | End-to-end integration | **Partial** — pieces are individually live-verified; no real bidder has been pushed through the *entire* pipeline start to finish yet — blocked on §3.1 |
| 25 | Security + deployment | **Partial** — security (auth) done; **deployment is not started** — no Dockerfile/compose/hosting config anywhere in the repo — see §3.4 |
| 26 | Realistic testing, multiple tender/bidder cases | **Not started** — blocked on real consented data — see §3.1 |
| 27 | SIH demo/polish | **Blocked** on 26 — premature to invest further until real data exists to demo against |

---

## 3 · Real, unstarted gaps — in priority order

### 3.1 — No real demo data (blocks 13 fully, 24, 26, 27)

`data/consented_bidders/` is empty by design (`data/README.md`) — nobody has
pushed a real, consented document through the live pipeline end to end yet.
This is the single biggest gap between "the pieces individually work" and
"we can actually demo it," and it is **not an engineering task**.

**Action:**
- Recruit at least 3 real, consenting people/businesses (teammates, family,
  willing volunteers) willing to have their real PAN/GST/UDYAM documents used
  in an internal demo.
- At least two of the three must genuinely share one attribute — director
  name, address, phone, or bank account — so collusion detection has a real
  case to fire on, not a fabricated one (the project's own non-negotiable
  rule: no synthetic bidder data, ever).
- Push all of them through the live pipeline once, for real. This *is* item
  26's "realistic testing" — there's no separate testing phase to design,
  just running the real thing with real (consented) input.
- **Owner:** whoever can source real, consenting documents fastest — start
  this now, in parallel with everything else below; it has the longest lead
  time of anything on this list.

### 3.2 — No rule pack from a real tender (blocks 15's real use, and the demo narrative)

`rulepacks/` is an intentionally empty scaffold (`rulepacks/README.md`) — no
rule pack has been decomposed from an actual tender yet. **The tooling for
this is now built** (tender PDF upload, Tender Intelligence, the
requirement-type catalog, the guided builder's type picker, and a Validate
step separate from Adopt) — this is now purely a matter of someone actually
running it against a real tender, assigned to Kevin in
`NEXT_TASKS_5_kevin_anubrat_suhani.md`.

**Action:**
1. Find a real, public GeM/CPCL tender PDF (doesn't need to be your own —
   public tenders are downloadable).
2. Upload it via the tender's own page ("Upload tender PDF").
3. Run it through Tender Intelligence to get candidate requirements, use
   "Use this →" to pull each one into the builder as a draft.
4. For each draft, pick a requirement type where one fits (pre-fills a real
   evidence path) or fill in the check by hand; anything the catalog can't
   back honestly gets `review_required` automatically — resolve or
   knowingly leave it flagged.
5. Click **Validate** to check without committing; fix any violations.
6. Click **Adopt** (SENIOR_OFFICER+) to publish for real, with a real
   `officer_id`.

This can start **immediately and independently** of §3.1 — the tender side
needs no bidder data. It does need the admin-builder work verified against
a live database first (Anubrat's lane in the same file) — the tooling is
written but not yet run for real anywhere.

### 3.3 — Demo credentials not decided

`services/orchestrator/.env` is gitignored by design — real Sandbox.co.in and
Gemini keys live only on whichever machine configured them.

**Action:** Decide, as a team, before demo day (not during it): does the
panel demo run from one pre-configured machine, or does everyone bring their
own `.env`? A 10-minute decision now avoids a last-minute scramble — but it
gates the *live* parts of §3.1 and §3.2 (verification calls, Tender
Intelligence), so decide this first.

### 3.4 — Deployment — genuinely missing

Confirmed directly: no `Dockerfile`, no `docker-compose.yml`, no hosting
config anywhere in this repo. Auth/security (item 25's first half) is done;
deployment (its second half) hasn't been started at all.

**Action:**
- Minimum viable: a `docker-compose.yml` wiring `services/core` (as a
  dependency of orchestrator, not a standalone container), `services/orchestrator`
  + Postgres, and the built frontend, so the whole system comes up with one
  `docker compose up`.
- **Before investing here, clarify which SIH round/format this is for** — if
  judging is in-person on a laptop, a one-command local compose setup may be
  all that's needed; if it needs a reachable URL, this becomes more urgent
  and larger in scope (real hosting, HTTPS, etc.).

### 3.5 — Byte-hashing audit (5-minute check, not a code port)

A specific gotcha worth confirming rather than assuming: content hashing for
an *uploaded document* (a binary PDF/image) must hash raw bytes directly,
never route through a text-only hasher built for JSON canonicalization.
Confirm `services/orchestrator/satyapramana_store/extract/ingest.py` (or
wherever document content hashing happens) does this correctly for binary
uploads. If it already does, this item just gets checked off.

### 3.6 — Polish pass

Genuinely blocked on §3.1 and §3.2 existing first — further UI polish without
real data to demo against is premature. `STATUS.md` already lists the round-4
interactivity pass (toasts, skeletons, confirmations, empty states) as done;
what's left here is presentation flow once there's something real to present.

---

## 4 · Suggested order of work

```
now ─────────────────────────────────────────────────────────────────► demo
 │
 ├─ 3.1 Source real consented bidder data  (longest lead time — start first)
 ├─ 3.2 Find + decompose a real tender      (independent of 3.1, start now too)
 ├─ 3.3 Decide demo-machine/credentials     (quick team decision, do early)
 ├─ 3.5 Byte-hashing audit                  (5 minutes, do whenever)
 ├─ 3.4 docker-compose (if the format needs it — confirm first)
 │
 └─ once 3.1 + 3.2 land:
     24  Run the real end-to-end pass (this IS the integration test)
     26  This *is* 24, using real consented data
     27  Demo script / presentation polish
```

## 5 · Open questions for the team

- Which SIH round is this for, and does it require a hosted/reachable demo
  or a local one? (Decides how much §3.4 matters.)
- Who is sourcing the real consented bidder data, and by when?
- Who is finding and decomposing the real tender PDF?
- One shared demo machine, or per-developer `.env` setup for the panel?
