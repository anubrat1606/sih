# Next tasks, round 5 — verify, then go end-to-end for real

**Status: 2 of 3 lanes done. Only Suhani's is left.** Read this whole file
before touching the running app — the one thing still outstanding
(real consented bidders, item below) is genuinely the last piece before
this round's actual goal (a real tender, a real rule pack, real bidders,
collusion firing on real shared data) is reachable.

Read `STATUS.md` first (what's actually built and merged, as of now — not
"this session," everything below is real and on `main`), then
`docs/COMPLETION_PLAN.md`, then `CONTRIBUTING.md` (file ownership and the
branch/PR workflow — still in force).

## Where this round sits

**The app is live. No local setup needed for anyone anymore** — that
changed mid-round (see "What changed since this file was first written"
below). Open it directly:

- Frontend: https://sih26100-frontend.onrender.com
- Backend: https://sih26100-orchestrator.onrender.com (interactive docs at `/docs`)
- Shared login: ask Anubrat for the current bootstrap admin credentials if
  you don't have them — role `ADMIN`, satisfies every role gate in the app.
- It's a **shared Neon database** — everyone's changes land in the same
  place and are visible to the whole team. Nothing you do here is
  sandboxed to just you.

**Done, merged, on `main`:**
- **[PR #56](https://github.com/anubrat1606/sih/pull/56)** — Kevin's admin
  tender builder, live-verified by Anubrat against real Postgres, merged.
- **[PR #57](https://github.com/anubrat1606/sih/pull/57)** — decided: no
  Docker, one shared Neon Postgres instead.
- **[PR #58](https://github.com/anubrat1606/sih/pull/58)** — Render
  Blueprint (`render.yaml`); the app above is that deployment.
- **[PR #59](https://github.com/anubrat1606/sih/pull/59)** — Kevin's first
  real, adopted rule pack (`rulepacks/bhel.t7j1z68239.metallic-expansion-joints.json`),
  built and adopted **against the live deployment above**, not locally.

**Still open:** Suhani's lane only — real consented bidders, registered
against Kevin's real tender (`BHEL-T7J1Z68239`), pushed through the real
pipeline. See her section below; nothing else in this file is still
pending.

## What changed since this file was first written

Two decisions landed mid-round that supersede what this file originally
told Anubrat and Suhani to do — noted here so nobody follows stale
instructions later in this same file:

1. **No Docker, ever, for this round.** The original "Anubrat — Part 2"
   task below asked for a `Dockerfile` per service and a
   `docker-compose.yml`. That was explicitly declined (`STATUS.md`,
   "Architecture direction," 2026-09-12) as unneeded infrastructure cost.
   What actually shipped instead: a shared Neon Postgres project +
   a Render Blueprint deploying the real app to the two URLs above. Same
   underlying problem ("not everyone can get a database/container running
   locally") solved a different, cheaper way.
2. **Nobody needs `services/orchestrator/.env` anymore either**, unless
   they're actually changing backend code and want to run it locally for
   that. Working against the live deployment (as Kevin did for PR #59) is
   now the default path for exercising the real system — see
   `docs/DEPLOYMENT.md`.

## Merge approval — unchanged from round 4

**Nobody merges their own work, ever, under any circumstance.** Open your
PR against `main`, make sure CI is green, and stop. Anubrat reviews and
merges every PR — a second reviewer per `CONTRIBUTING.md`'s existing rule
still applies. A green CI run is a necessary condition for review, not a
substitute for it.

## File ownership this round

`CONTRIBUTING.md`'s table is still authoritative; this only fills in the
areas it left unassigned:

| Path | Owner this round | Note |
|---|---|---|
| `services/orchestrator/satyapramana_store/extract/` (incl. `ingest.py`) | **Suhani** | Already hers, unchanged — her byte-hashing audit task lives here |
| `data/consented_bidders/` (new) | **Suhani** | Real, consented bidder documents/details — see her section. Gitignored; never committed |
| `rulepacks/*.json` | **Kevin** | Done — `bhel.t7j1z68239.metallic-expansion-joints.json` merged in PR #59 |
| `render.yaml`, `docs/DEPLOYMENT.md` | **Anubrat** | Done — merged in PR #58 |
| `docs/*.md` | Shared | Append to your own section only, exactly as `CONTRIBUTING.md` already says |

Nobody this round touches `frontend/`, `services/core/`, or `schemas/`.

## Hard rules — same five as always

1. No mock, sample, or simulated data anywhere, including in anything that
   doubles as a demo. A check that can't be performed returns `UNKNOWN`
   with the real reason.
2. No model ever makes a final determination. AI proposes (Tender
   Intelligence, EXPLAIN); deterministic code decides.
3. Nothing changes state except by appending an event.
4. Every change ships with a test, and the suite stays green.
5. Secrets live in `.env` (or the Render dashboard's env vars), never in a
   commit.

Two more, specific to this round:

6. **No fabricated tender requirement and no fabricated bidder.** Kevin's
   rule pack came from a real, findable tender document (cited in PR #59).
   Suhani's bidders must be real people/businesses who consented — see her
   section for exactly what "consent" needs to mean here.
7. **The requirement-type catalog's `evidence_backed: false` types stay
   `review_required: true`.** Already demonstrated in PR #59: 5 of the 8
   real requirements in Kevin's tender (turnover, experience, certification,
   two declarations) were deliberately left un-adopted because no evidence
   path exists for them yet — that's the correct outcome, not something to
   route around, and it applies the same way to anything Suhani finds.

---

## Anubrat — done

Both parts of this lane are merged. Recorded here for the record, not as
an open task:

- **PR #56** reviewed and live-verified against real Postgres, merged.
- **PR #57 + #58** — decided against Docker, shipped a shared Neon
  database and a live Render deployment instead. `docs/DEPLOYMENT.md` has
  the full picture, including the one known limitation worth remembering:
  uploaded document files (not the event log — that's safe in Neon) don't
  survive a Render redeploy on the free tier. If Suhani's document uploads
  disappear after a redeploy mid-round, that's why, not a bug to chase.

Nothing further expected from this lane this round.

---

## Kevin — done

`STATUS.md` gap 3 is closed. **[PR #59](https://github.com/anubrat1606/sih/pull/59)**,
merged: a real tender (BHEL, Enquiry No. T7J1Z68239, "Supply of Metallic
Expansion Joints," sourced live from GeM's public catalog store) created
and its rule pack adopted **against the live deployment**, not locally.

- 3 requirements adopted (GST active, PAN present, Udyam for MSE bidders)
   — all evidence-backed, all verified `Validate`-clean before `Adopt`.
- 5 more real requirements from the same tender (turnover, experience,
  certification, an insolvency declaration, the Integrity Pact) were
  drafted, validated separately, and correctly refused adoption — rule 8
  (no evidence path) and rule 11 (`review_required`) both fired exactly as
  designed. Full validation output is in the PR description.
- `rulepacks/bhel.t7j1z68239.metallic-expansion-joints.json` is the exact
  JSON the live API validated and adopted.
- Verified live: `GET /tenders/BHEL-T7J1Z68239` and
  `GET /tenders/BHEL-T7J1Z68239/blockers` both confirmed.

Nothing further expected from this lane this round.

---

## Suhani — the only thing left this round

**Goal:** close `STATUS.md` gap 1, using your existing ownership of
`services/orchestrator/satyapramana_store/extract/` to also close the one
small technical item still open there. This is now the **only** thing
standing between where the round is and its actual goal (a real
end-to-end run with collusion firing on real data).

**No longer blocked on anything.** The app is live (see "Where this round
sits" above) — no local Postgres, no `.env`, no setup. Open
https://sih26100-frontend.onrender.com, log in, and start.

### Part 1 — the byte-hashing audit (`COMPLETION_PLAN.md` §3.5)

A specific, narrow thing to confirm in your own directory: content hashing
for an *uploaded document* (a binary PDF or image) must hash raw bytes
directly, never route through a hasher built for JSON text canonicalization.
Read `store_document()` and the content-hash code in `extract/ingest.py`
and confirm this is actually true today. If it already is, this is a
five-minute check, done. If it isn't, fix it — it's your file, your call,
no need to ask.

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
4. Register each as a bidder **on Kevin's real tender, `BHEL-T7J1Z68239`**
   (it already exists with an adopted rule pack — use it rather than a
   bare new tender ID, so evaluation has something real to run against),
   upload their real documents through the tender's bidder document
   upload, run verify.
5. Evaluate each bidder for real and confirm the collusion flag actually
   fires on the pair that shares an attribute — this is the first time
   anyone will have seen that happen against real data instead of a
   unit-test fixture. Note: with only GST/PAN/Udyam adopted on this tender
   (see Kevin's section), expect those three to resolve for real (PAN_STATUS/
   GST_STATUS are genuinely `LIVE` on this deployment — check
   `GET /capabilities`) while the five `review_required` requirements
   simply aren't part of what gets evaluated yet. That's correct, not a
   gap in your work.
6. One thing to watch for, inherited from the deployment (not something to
   fix yourself): Render's free tier doesn't persist uploaded document
   files across a redeploy (`docs/DEPLOYMENT.md`). If a document you
   uploaded stops being retrievable partway through, that's why — re-upload
   rather than chase it as a bug.

**Test:** if the hashing audit needs a fix, it needs a test in
`extract/`'s existing test file, matching whatever pattern the file
already uses for that grammar/function. The bidder data itself isn't code
and needs no test — it's the input the rest of the system's existing tests
already cover.

**Done when:** three real bidders exist in the running system (visible to
the whole team, since the database is shared) with real uploaded
documents, at least one collusion pair fires for real, and
`data/consented_bidders/` documents exactly who consented to what (a short
note per bidder is enough — this doubles as your own record that consent
was real, not assumed).

---

## After Suhani lands

Once her lane closes, this round's actual goal is reachable for the first
time: a genuine end-to-end run on one real tender with real bidders
(`STATUS.md`/`docs/COMPLETION_PLAN.md` items 24 and 26), and only then the
demo script / presentation polish (item 27). Whoever picks that up next
should open a new `NEXT_TASKS_6` file rather than improvising it — same
discipline, same reason it's worked every round so far.
