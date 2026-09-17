# Round 8 — Temporal Scrubber + financial extraction (Anubrat, Suhani, Rishika)

Replaces `docs/ROUND_8_PLANNING.md`'s design with real, assigned work.
Kevin's still off. Same rules as every round: stay inside your files,
nobody merges their own PR, real Postgres tests, real data or `UNKNOWN`.

**Dependency note, read this first:** Rishika's task needs Anubrat's two
new endpoints to exist for real testing. Anubrat is doing the backend
piece first, specifically to unblock this — same pattern as round 6's
A1/A2. Rishika can start against the documented contract below before
that lands, but final verification needs the real endpoint.

---

## Anubrat — Temporal Scrubber backend (do this first)

**What it is:** every event is permanent and ordered. This exposes that —
"show me this bidder's state as of event #412" — as two new read
endpoints.

**What I found while scoping this that changes the design:**
`rebuild_projections()` (verdicts/collusion/tenders) truncates *shared*
tables every other request reads for current state — already fixed one
race there (PR #86); a naive history endpoint would reintroduce that
class of bug. `rebuild_evidence()` is better-behaved (already scoped to
one `bidder_id`, already accepts `up_to_seq`) but still writes to
`proj_evidence` for that bidder, so two people looking at the same
bidder — one at "now," one at a past point — would still interfere.

**The fix, both cases:** split compute from persist. Extract the fold
logic (already exists, reads events, builds Python dicts) into functions
that return data without writing anything:
- `projections.py`: refactor `_rebuild_locked`'s fold logic into
  `fold_projections_as_of(conn, up_to_seq) -> dict` — same computation,
  no `DELETE`/`INSERT`. The existing `rebuild_projections()` keeps doing
  both (call the fold function, then persist) so the live path's
  performance is unchanged.
- `evidence.py`: same split for `rebuild_evidence` — a
  `fold_evidence_as_of(conn, bidder_id, registry, up_to_seq) ->
  dict[str, EvidenceRecord]` with no writes, called by both the existing
  `rebuild_evidence()` and the new endpoint below.

**New endpoints in `app.py`** (`require_role(Role.OFFICER)`, same as
every other bidder-read endpoint):
- `GET /bidders/{bidder_id}/timeline?tender_id=...` — every event
  sequence number that changed something about this bidder (`FIELD_
  EXTRACTED`, `VERIFICATION_OBSERVED`, `VERIFICATION_FAILED`,
  `REQUIREMENT_EVALUATED`, `VERDICT_OVERRIDDEN`, `DECISION_RECORDED`),
  each with `seq`, `event_type`, `occurred_at`. Enough for a frontend
  slider with real labeled points, not evenly-spaced fake ones.
  ```json
  { "checkpoints": [
      { "seq": 118, "event_type": "FIELD_EXTRACTED", "occurred_at": "2026-09-10T11:02:04Z" },
      { "seq": 145, "event_type": "VERIFICATION_OBSERVED", "occurred_at": "2026-09-10T11:02:41Z" }
  ] }
  ```
- `GET /bidders/{bidder_id}/as-of/{seq}?tender_id=...` — the same response
  shape `GET /bidders/{bidder_id}` returns today (metrics, risk,
  verdicts), computed via the two pure fold functions above instead of
  the live projections. Reject a `seq` past the log's current tip with a
  clear 422, not a silent clamp.

**Tests:** a bidder with a real history (extract → verify → evaluate →
override) whose `as-of` a seq before the override shows the pre-override
verdict, and `as-of` current tip matches `GET /bidders/{id}` exactly.
Concurrency test in the same style as PR #86's: fire real `as-of` calls
for a past seq while the live tables are being rebuilt for real, on the
same bidder — assert the live path's current values are untouched.

**File ownership:** `projections.py`, `evidence.py`, `app.py` (only the
two new endpoints), `tests/test_projections.py`, `tests/test_evidence.py`
or a new `tests/test_temporal.py` if that reads cleaner.

---

## Suhani — Financial statement extraction (MIN_TURNOVER / NET_WORTH)

**What it closes:** these two requirement types currently have zero
evidence path (`requirement_types.py`: `candidate_fields=()`, "no
extraction path yet"). This gives them one.

**The honest ceiling, said once here so it's not a surprise mid-build:**
there's no authority to verify a claimed turnover against — nothing like
GST_STATUS exists for this. A mandatory requirement built on this
evidence stays capped at PARTIAL (`SELF_DECLARED_CEILING`), same rule
that capped the real PAN result. You're building real extraction of a
number that was always going to read as self-declared, not building
toward a PASS. Worth surfacing that plainly in whatever UI text you write
for this — "extracted, not yet independently verifiable" is the honest
frame, not "not implemented."

**Backend** — `services/orchestrator/satyapramana_store/extract/`:
- New evidence paths in `ingest.py`'s `FIELD_PATHS`:
  `bidder.financials.turnover`, `bidder.financials.net_worth`, plus
  whatever you land on for recording *which* financial year a figure
  belongs to (a balance sheet reports 2+ years side by side — pick the
  most recent column, but record it, don't guess which one silently).
- New extraction module (e.g. `extract/financials.py`) using
  `pdfplumber.Page.extract_table()` — already a dependency via
  `layout.py`'s `read_pdf`, no new one needed. Locate a row whose label
  matches "Revenue / Turnover" (or close variants — check a couple of
  real balance sheet formats before locking the label list) and read the
  adjacent numeric cell, same "label found → read adjacent value, or
  record why not" shape as `_read_value_under_label` in `ingest.py` —
  don't invent a third pattern for this.
- Real unit handling: the statement states its unit once ("All figures in
  INR lakhs" or similar) — read that and normalize (1 lakh = 100,000,
  1 crore = 10,000,000), or extract nothing with a stated reason if the
  unit can't be determined. A number normalized against a guessed unit is
  worse than no number.
- `requirement_types.py`: fill in `MIN_TURNOVER`/`NET_WORTH`'s
  `candidate_fields` with the new paths once they're real.
- Tests: synthetic PDF fixtures in the `conftest_pdf.py` style (a labeled,
  clearly-fictional table, same convention as every other fixture there)
  covering: correct extraction, lakhs vs. crore vs. bare rupees,
  ambiguous/missing unit → honest failure, label not present on the page
  → honest absence (not a guess).

**Frontend:** wherever this deployment currently renders "review_required
— no evidence path" for an unbacked requirement type (check the admin
tender builder's requirement-type picker, `requirement_types.py`'s own
consumer), it should now offer MIN_TURNOVER/NET_WORTH as backed — and
once adopted and evaluated, the bidder compliance page's existing verdict
rendering already handles PARTIAL/`SELF_DECLARED_CEILING` generically (no
new component needed there), but check the reason-code copy reads clearly
for this specific case, not just technically correct.

**File ownership:** `extract/ingest.py` (FIELD_PATHS only),
`extract/financials.py` (new), `requirement_types.py`, `tests/
test_extraction.py` or a new `tests/test_financial_extraction.py`,
whatever admin-builder frontend file actually renders the type picker
(read it first, ask if it's not obvious which one).

---

## Rishika — Temporal Scrubber frontend

**Depends on Anubrat's two endpoints above.** Build against the
documented response shapes first if you're starting before they're
merged; do a real pass against the live endpoint before calling this
done.

**What it is:** a "History" tab on the bidder compliance page
(`pages/BidderCompliancePage.jsx` already has a `TABS` array and an
`activeTab` pattern — add `{ id: "history", label: "History" }` there,
same shape as the existing five tabs, not a new pattern).

**On the tab:**
- Fetch `GET /bidders/{id}/timeline` — render real checkpoints (not an
  evenly-spaced fake slider) as a horizontal timeline or a slider whose
  steps snap to actual event sequence numbers, each labeled with its
  `event_type` and a human-readable timestamp (`lib/audit.js`'s
  `formatTimestamp` is already the house pattern for this).
- Selecting a checkpoint calls `GET /bidders/{id}/as-of/{seq}` and
  re-renders the same verdict/metrics/risk display the Compliance tab
  already has — reuse `VerdictBadge`/`RiskBadge`/the metrics components
  from `ui/primitives.jsx`, don't rebuild them.
- The strongest version (do this if time allows, not required for a
  first merge): visually diff the selected checkpoint against *current*
  state — which requirements changed verdict, and to what — so the
  override case reads as "this flipped here," not just "here's a
  snapshot."

**File ownership:** `pages/BidderCompliancePage.jsx` (the new tab only —
don't touch the other five), `api.js` (two new function additions:
`getBidderTimeline`, `getBidderAsOf`), a new component file if the
timeline UI is big enough to warrant one (e.g.
`features/BidderHistoryTimeline.jsx`) rather than inlining it all in the
page file.

---

## Ground rules (unchanged)

- `export DATABASE_URL=postgresql://localhost/satyapramana_test` for
  backend tests.
- `npm run lint` / `npm run build` clean before any PR.
- Stay inside your file list; ask before going outside it.
- Nobody merges their own PR.
