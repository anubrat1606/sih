# Outstanding work — compiled 2026-09-11

Compiled by Suhani from the actual PR/merge history (`gh pr list --state merged`)
and a live checkout, because `docs/STATUS.md` has not been rewritten since
before round 4 and no longer reflects what's actually on `main`. This is a
snapshot, not a replacement for STATUS.md — whoever next updates STATUS.md
should fold this in and can delete this file once that happens.

At the time of writing: **zero open PRs**, **547 backend tests passing**
(365 `services/orchestrator` + 182 `services/core`), all four rounds of
`NEXT_TASKS_*_suhani_rishika.md` done and merged, round 4's Phase 7
integration merged.

## What's built and merged (for context, not action)

- Core verdict engine, deterministic, fully tested.
- Extraction: GSTIN / PAN / UDYAM / CIN, PAN holder name + DOB, GST
  issue/expiry dates, GST claimed business name (`bidder.gst.claimed_*`,
  deliberately separate from the verification-sourced
  `bidder.gst.legal_name`).
- Verification: live for PAN/GST/CIN via Sandbox.co.in (needs a real key to
  actually fire — see gap 2 below).
- Auth: real login, `scrypt` password hashing, JWT sessions, three roles
  (OFFICER / SENIOR_OFFICER / ADMIN) — backend and frontend UI both merged.
- Reporting: Bid Autopsy, Compliance Repair, Compliance Dossier, Tender
  Compliance Report, CSV export, blocker summary.
- Frontend design system (tokens, dual theme), Evidence Graph, PDF lightbox
  with zoom/pan, Mission Control dashboard, admin UI.
- Round 4 UI polish: toasts, loading skeletons, inline field validation,
  confirmation dialog, empty states, search/filter bar, chart primitives,
  audit timeline, report actions — all wired into every real page.
- Tender management: explicit "create tender" flow, a guided rule-pack
  builder (replaces the old raw-JSON textarea), Tender Intelligence
  (Gemini *proposes* a draft rule pack from a tender PDF; an officer must
  review and adopt it before it's ever live — same propose-not-decide
  boundary EXPLAIN already follows).

## Outstanding — in rough priority order

### 1. No real demo data
`data/consented_bidders/` does not exist in this checkout. Nobody has
pushed a real, consented document through the live pipeline end to end.
This has been priority 3 since round 2 and is still the single biggest gap
between "the pieces all individually work" and "we can actually demo it."
Need: real people/businesses who've consented, at least three bidders on
one tender, two of them genuinely sharing an attribute (for the collusion
case). See `data/README.md`.

### 2. No live credentials configured on this machine
`services/orchestrator/.env` does not exist here. Sandbox.co.in
(verification) and Gemini (EXPLAIN, Tender Intelligence) both need real
keys to actually fire — without them everything correctly degrades to
honest `UNKNOWN` / unavailable, which is the right behaviour, but it means
nothing has been exercised live from *this* checkout. (STATUS.md mentions
a key pair configured locally on Anubrat's own machine — worth confirming
that's still current and whether it's meant to be shared or per-developer.)

### 3. No real tender-derived rule pack
`rulepacks/` only has the round-2 scaffold (`README.md`, `validate.py`) —
no rule pack built from an actual GeM tender PDF yet. Tender Intelligence
(Gemini-proposed drafts) exists now and should make this faster once
gap 2 is resolved, but someone still has to run it against a real tender
and have an officer review/adopt the result.

### 4. EPFO / Udyam verification
Confirmed cut from scope in round 2 (no lawful programmatic source for
EPFO/ESIC; Sandbox.co.in's full API catalogue has no Udyam endpoint) — not
outstanding work, listed here only so it isn't mistaken for an oversight.

### 5. `docs/STATUS.md` is stale
Still describes a pre-auth, pre-design-system, pre-round-4 state. Worth a
dedicated rewrite pass once gaps 1–3 move, rather than patching it
incrementally — a lot has changed underneath it since it was last touched.

## Not covered here

Anything Suhani or Rishika could pick up themselves stays in a normal
`NEXT_TASKS_N_suhani_rishika.md`-style task doc, as it has every round so
far. This file exists because gaps 1–3 above need real-world input
(consented data, real credentials, a real tender PDF) that neither
session can supply on its own.
