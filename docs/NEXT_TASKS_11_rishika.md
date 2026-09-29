# Next tasks — Rishika, round 11

Read `docs/STATUS.md` first if it's been a while — refresh it against
`gh pr list --state merged` if anything here looks stale. Round 10D (the 3
token fixes + the real screenshot, PR #121) and round 10's follow-up
(EXPERIENCE/SIMILAR_WORK/CERTIFICATION self-declared types, PR #122; a real
deprecated-Gemini-model bug found and fixed live, PR #124) are all merged as
of this doc. Pull `main` before starting either task below.

---

## Task 1 — the honest caveats never reach the officer

Found while reviewing your PR #121: `frontend/src/features/RequirementBuilder.jsx`'s
`RequirementRow` component only shows a requirement type's `note` when
`evidence_backed` is `false` (the `UnavailableNote` block, ~line 198-203).
`applyType()` (~line 113-127) clears `note` to `""` the moment an officer
picks any `evidence_backed: true` type — including the self-declared ones
that carry a real, deliberately-written evidentiary caveat:

- `BLACKLIST_DEBARMENT` — "near-zero anti-fraud value" (a debarred bidder
  self-attesting they aren't debarred proves nothing)
- `EXPERIENCE`, `SIMILAR_WORK`, `CERTIFICATION` (new in PR #122) — "weaker
  evidence than the register-backed self-declared types," since these three
  could in principle be evidenced by a document (a completion certificate,
  a cert number) an officer could review directly

Check `services/orchestrator/satyapramana_store/requirement_types.py` for
the exact wording of each. Right now none of it is visible anywhere in the
builder once the type is selected — an officer marking one of these
mandatory sees the same UI as picking `PAN` or `GST`, no signal that the
evidentiary strength is genuinely different.

Your call on treatment — a milder inline note than `UnavailableNote` (these
types ARE adoptable, unlike the truly unbacked ones) vs. something new
entirely. Don't touch `applyType()`'s clearing of the officer's own
free-text `note` field (a separate, editable annotation) — this is about
surfacing the catalog's own `type.note` somewhere visible when a
backed-but-caveated type is picked.

## Task 2 — live-verify EXPLAIN and Tender Intelligence for the first time ever

The Gemini key went onto the live deployment for real today (previously
unset — both features only ever showed `available: false`). First live call
already caught one real bug (a deprecated model id, fixed in PR #124,
merged) — but as of this doc, **neither EXPLAIN nor Tender Intelligence has
been seen rendering a real result in the actual browser UI**, only via a
raw API call. Same discipline as your round 10D screenshot task: confirm
live, don't assume.

1. **EXPLAIN** — `frontend/src/pages/BidderCompliancePage.jsx` and
   `ReportsPage.jsx` both have a real trigger. Open `ANUBRAT-DAS` on
   `BHEL-T7J1Z68239` (a real bidder/tender already in the system) and pull
   up its narrative. Confirm it renders correctly — loading state, the
   actual prose, any formatting — and that every fact in it matches the
   bidder's real verdicts (the system prompt forbids the model inventing or
   altering any fact; worth actually checking one narrative against the
   underlying data once, not just trusting the prose reads plausibly).
2. **Tender Intelligence** — trigger a real decomposition from
   `TenderDetailPage.jsx` against a tender with a real uploaded PDF (BHEL's
   own tender document is already in the system). Confirm the proposed
   requirements render in the UI and that `RequirementBuilder.jsx`'s
   "Use this →" button genuinely adds a still-`review_required` draft row,
   same as documented.
3. If Gemini returns a transient `503` (seen once already — "high demand,"
   not a real problem), just retry; if you see anything else, that's a real
   finding, write it up the way the storage bug was written up.

Screenshots of both working for real go in the PPT — this is a capability
the team has built and shipped but never actually watched work end to end
until now.

---

Same as always: real tests where there's backend logic to test, real
build/lint for the frontend, live-verify before claiming done, push when
green.
