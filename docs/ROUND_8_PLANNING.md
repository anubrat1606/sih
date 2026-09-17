# Round 8 planning — not started, no tasks assigned yet

This is a design doc, not a `NEXT_TASKS` brief. Nothing here is scoped to
a person or scheduled yet — round 7 (Suhani: password reset, Rishika:
admin Audit & System page) finishes first. Written now so the moment
round 7 lands, round 8 can start from a real technical plan instead of a
standing start.

Two candidates, in priority order, both grounded in what the code
actually already supports — verified against `main`, not guessed.

---

## 1. Temporal Scrubber — view a bidder's state as of a past event

**Why this one first:** it's the most direct, visible proof of the
architecture's own central claim — "nothing is edited or deleted, the
whole history is always reconstructible" — turned into something a judge
can actually click through, not just read in `PRESENTATION.md`.

**What already exists:** `projections.py`'s `rebuild_projections(conn,
up_to_seq=None)` already accepts a sequence ceiling and folds the event
log only up to that point — this is not new capability, it's already
there, just never called with anything but `None` (confirmed: every one
of the 11 call sites in `app.py` calls it with no argument).

**The real design problem, found while verifying this plan:**
`rebuild_projections` truncates and rewrites the *shared* `proj_verdicts`
/ `proj_collusion` / `proj_tenders` tables — the ones every other
concurrent request reads for *current* state (this is exactly the table
PR #86 just fixed a race on). Calling it with a past `up_to_seq` the
naive way would briefly blow away live current state for every other
reader while it's rebuilt to the past, then rebuild it back — wrong, and
a reintroduction of the exact class of bug just fixed.

**The correct shape:** split *compute* from *persist*. The fold logic
inside `_rebuild_locked` (read events up to a ceiling, build the verdict/
collusion/tender dicts in Python) already doesn't need the database
tables to exist — it only needs them for the final `INSERT`. Extract that
fold into a pure function (e.g. `fold_projections_as_of(conn, up_to_seq)
-> dict` with no writes), and:
- The existing live path keeps writing to `proj_*` (performance, as now).
- A new read-only endpoint calls the pure fold function directly, with
  the caller's chosen `up_to_seq`, and never touches the shared tables.

**API shape (proposed, not final):**
- `GET /bidders/{bidder_id}/timeline?tender_id=...` — every event
  sequence number that changed something about this bidder (extraction,
  verification, evaluation, override, decision), each with its
  `occurred_at` and `event_type` — enough to draw a slider/timeline.
- `GET /bidders/{bidder_id}/as-of/{seq}?tender_id=...` — the same shape
  `GET /bidders/{bidder_id}` returns today, but folded only up to `seq`,
  via the pure function above.

**Frontend:** a "History" view on the bidder compliance page — a
timeline/slider over real checkpoints, re-rendering verdicts/risk/metrics
at the selected point. The strongest version of this visibly diffs
against current state ("this requirement read FAIL here, before the
override") — worth doing if time allows, not required for v1.

**Open questions to settle before work starts:**
- Does "as of" mean sequence number (exact, unambiguous) or wall-clock
  timestamp (more intuitive for a slider label, but needs a seq lookup
  either way)? Leaning sequence number for correctness, timestamp shown
  as the label.
- Scope to one bidder (smaller, matches the compliance page) or the whole
  tender (bigger, shows collusion-cluster history too)? Leaning
  bidder-scoped for v1 — collusion history is a real v2 candidate.

---

## 2. Financial statement extraction — MIN_TURNOVER / NET_WORTH

**Why second, not first:** real value, but capped value. There is no
government authority to verify a claimed turnover against — nothing like
GST_STATUS exists for this. So even a perfect extraction stays Tier C
(self-declared) evidence forever, which means a **mandatory** turnover
requirement can never reach a clean PASS — the same `SELF_DECLARED_CEILING`
rule that capped the real PAN result this session at PARTIAL applies here
by construction, always. Real progress (closes a currently-honest gap:
`requirement_types.py` says outright "no extraction path yet"), but it
trades "unusable" for "correctly capped," not for "verified."

**What's needed, concretely:**
- New evidence field paths — none exist yet (`MIN_TURNOVER`'s
  `candidate_fields` is empty in `requirement_types.py` today).
  Proposed: `bidder.financials.turnover`, `bidder.financials.net_worth`,
  each with the reporting period/financial year it applies to (a balance
  sheet reports multiple years side by side — the extractor has to record
  *which* column it read, not just a bare number).
- A genuinely different extraction shape from GSTIN/PAN. Those are regex
  over free text; this is table extraction — a label ("Revenue /
  Turnover", "Net Worth / Equity") in one cell, a number in the adjacent
  one. `pdfplumber`'s `page.extract_table()` is the right primitive, nd
  it's already a dependency (`read_pdf` in `layout.py` uses the same
  library) — no new dependency needed.
- Real unit handling: Indian financial statements report in rupees,
  lakhs (×100,000), or crore (×10,000,000) depending on the document, and
  the figure is meaningless without knowing which. The extractor has to
  read the stated unit (usually printed once, e.g. "All figures in INR
  lakhs") and normalize, or explicitly extract nothing rather than guess.
- Validation here isn't a check digit (there isn't one) — it's closer to
  "did this genuinely come from a label-adjacent cell in a real table,
  and is it a plausible non-negative number," recorded honestly as a
  weaker form of structural confidence than GSTIN/PAN get.

**A real v2 idea, not v1 scope:** Indian audited financial statements
carry a UDIN (Unique Document Identification Number) issued by ICAI,
which — unlike the turnover figure itself — *can* be checked against a
real registry (ICAI's UDIN portal). If that's ever wired up as a
capability, it would be the one path that lets a financial requirement
clear the self-declared ceiling for real. Worth a line in the backlog,
not worth designing now.

---

## Recommended sequencing

1. Round 7 finishes (Suhani, Rishika) — don't fork a new round on top of
   an open one.
2. Temporal Scrubber — the compute/persist split first (a real,
   self-contained backend refactor with its own tests), then the two
   endpoints, then the frontend timeline view.
3. Financial extraction — start with the table-extraction + unit-handling
   core (testable in isolation, same pattern as `extract/grammars.py`'s
   own test suite), then wire the two requirement types, then surface the
   self-declared-ceiling result honestly in the UI (this should look
   different from "not built yet" — it should read as "extracted, capped
   pending independent verification," a state the UI doesn't currently
   have a voice for).

Once round 7 is actually merged, this doc becomes the basis for a real
`NEXT_TASKS_8_*.md` with people and files assigned — not before.
