# Round 10 planning — not started, no tasks assigned yet

Design doc, not a `NEXT_TASKS` brief, same as rounds 8 and 9's planning
docs were before they became one. Round 9 (collusion history, self-
declaration capture, currency formatting) is fully merged and live.

This round closes out the one open research question from round 9's own
plan, researches one more candidate that came up inconclusive, and
proposes what actually turned out to be the strongest real item: a
performance problem that's been quietly growing since round 8.

---

## 1. ITR filing status — researched, closed, not buildable here

Round 9's plan flagged this as worth checking before committing either
way. Checked now, for real, not guessed:

**Sandbox.co.in — the same aggregator this deployment already has live
credentials with for PAN/GST/CIN — does have a real ITR-V API** (fetches
a taxpayer's ITR acknowledgment for a given period, JSON/PDF/XML). That
sounded at first like the same kind of win financial extraction was.

**It isn't, for a real, specific reason**: that API is part of Sandbox's
ERI (e-Return Intermediary) product family. Using it requires the
*calling organization* to be a registered ERI with the Income Tax
Department itself — a Class II/III Digital Signature Certificate, an
infrastructure due-diligence certificate from a certified expert, and a
formal application that goes through the Department's own technical and
security evaluation. That's a business/legal registration process, not
an API key -- fundamentally different from how PAN_STATUS/GST_STATUS/
CIN_STATUS came online (an aggregator subscription, nothing more).

**Conclusion: same category as EPFO/ESIC** -- not "no capability yet,"
but confirmed out of reach for this deployment, for a real and specific
reason. `requirement_types.py`'s ITR note currently says the generic "no
ITR extraction or capability exists yet" -- the same placeholder text
every genuinely-unresearched type has. It should say the real thing,
matching the precision `EPFO_ESIC`'s own note already has. This is a
small, honest, one-string fix -- worth doing regardless of what else this
round includes, not really its own task.

---

## 2. BIS / ISO certification -- researched, genuinely inconclusive

Checked as a possible real win for `CERTIFICATION`, since a BIS licence
or ISO certificate has a real number, an issuing body, and validity
dates -- the same shape GST/PAN/CIN have.

**What's real**: BIS does run a public verification register (no login,
no permission needed from the licence holder) -- the same public-
accessibility spirit GST/PAN have. Separately, IAF's CertSearch is a
real global database aggregating ISO certificates from accreditation
bodies, reportedly with API access.

**What's not confirmed**: whether BIS's public register is reachable via
a real API or only a browser form (very possibly CAPTCHA-walled, the
same dead end GST/EPFO's *official* portals turned out to be --
charter's own words: "scraping the CAPTCHA-walled portals is not the
fallback... absence of an API is an UNAVAILABLE capability, not an
invitation"). And CertSearch would mean onboarding an entirely new
vendor relationship, not extending the existing Sandbox.co.in account --
a real cost this search couldn't weigh without an actual account.

**Not committing to this either way.** Flagged for real research (an
actual trial account, actual API docs, not search-result summaries)
before a future round decides. Building `CERTIFICATION`/
`OEM_AUTHORIZATION` extraction stays out of round 10's committed scope.

---

## 3. Performance: single-bidder reads pay a whole-deployment cost

**The real, concrete item this round actually has.** Flagged in passing
back when the projection-rebuild race was fixed (PR #86); checked now
whether it's still true and how much it actually costs.

`rebuild_projections()` truncates and refolds `proj_verdicts` for
*every bidder on every tender in the whole deployment*, every time it's
called with no `up_to_seq` -- by design, for the tender/deployment-wide
reads that genuinely need everyone (`GET /dashboard`, a tender's full
bidder list, the review queue). But grep confirms it's also the *only*
path 7 of its 11 call sites use, and those seven only ever need **one**
bidder's own data: `GET /bidders/{id}`, evaluate, override, autopsy,
repair plan, evidence graph, and the bidder's own result view. Every one
of those currently pays the cost of refolding the entire deployment's
verdicts to answer a question about a single bidder -- a cost that has
been growing every round since (financial extraction, declaration
events, Temporal Scrubber checkpoints all added real, permanent event
volume, and none of it is scoped away for a single-bidder read).

**The fix already has its building block**: round 9's
`fold_verdicts_as_of(conn, up_to_seq, bidder_id=...)` already computes
exactly one bidder's verdicts, purely, from events -- built for the
Temporal Scrubber, but the shape is identical to what a scoped live
rebuild needs. The plan:
- A new `rebuild_projections_for_bidder(conn, bidder_id)` in
  `projections.py`: same advisory-lock-and-transaction discipline
  `rebuild_projections` already has (still real, still needed -- two
  concurrent writes to the same bidder's rows is the same race PR #86
  fixed, just narrower), but `DELETE FROM proj_verdicts WHERE
  bidder_id=%s` and fold only that bidder's events, via
  `fold_verdicts_as_of(conn, tip, bidder_id=bidder_id)` reused directly
  rather than a second implementation.
- The seven single-bidder call sites switch to it. `dashboard`,
  `list_tender_bidders`, `review_queue` (and `create_tender`, cheap and
  rare either way) keep the full rebuild -- they're not the problem.
- `proj_collusion` isn't part of this -- `collusion_clusters()` is
  already a single SQL function call per tender, not a Python refold, and
  cheap regardless of deployment size.

**What to measure, not assume**: before calling this done, time a real
`GET /bidders/{id}` on the live deployment before and after, on a
bidder with genuine history (ANUBRAT-DAS's real data, already on the
live system, is a real fixture for this -- 23 checkpoints and growing).
"Faster" should be a real number, not a plausible-sounding claim.

---

## Recommended sequencing

1. The ITR note fix -- small enough to just do, whenever, not really a
   scheduling question.
2. Performance -- the one committed, well-scoped item, building directly
   on round 9's own `fold_verdicts_as_of` rather than a second
   mechanism.
3. BIS/ISO stays a flagged research question for a future round, not
   scheduled here.

Once you say go, this becomes `NEXT_TASKS_10_*.md` -- not before.
