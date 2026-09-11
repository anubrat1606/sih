# Next tasks, round 3 — Suhani and Rishika, one each, zero file overlap

**Read this whole file before writing any code. Paste your own section — and
only your own section, plus the Hard Rules — into your own fresh Claude Code
session.** Your session has no memory of the conversation that produced this
document. Everything it needs to know is written down here.

Rounds 1 and 2 are done and merged, both clean, zero merge conflicts. Round
2 also turned up a real bug — a live end-to-end test of Rishika's Tender
Report against a date-based rule pack surfaced that date predicates never
actually worked against extracted dates (no NORMALIZE stage existed to
bridge extraction's correct raw `DD/MM/YYYY` values to the predicate
evaluator's correct ISO-8601 expectation). Anubrat fixed it in `evidence.py`
— nothing either of you built was wrong; the bridge between two correct
pieces was just missing. Mentioned here so you know why `_normalize` now
exists.

Paridhi's two items (a real tender PDF decomposed into a rule pack; real
consented bidder data) stay with Anubrat only — they need real-world input
neither of your sessions can supply, and were never really buildable tasks
in the first place. Anubrat is also continuing the design system and the
Evidence Graph screen. **Neither of you touches `frontend/`, `rulepacks/`,
or `data/` this round**, same boundary as round 2.

---

## Hard rules — apply to both of you, no exceptions (same as rounds 1-2)

1. **Start from latest `main`.** `git checkout main && git pull origin main`,
   then `git checkout -b feat/<yourname>-<topic>`.

2. **Only touch the files your section names.** If finishing your task truly
   seems to require touching a file outside that list, stop and message
   Anubrat rather than touching it yourself.

3. **No mock, sample, fabricated, or guessed data — anywhere, ever, including
   tests.** A field that can't be read for real becomes `null` with a stated
   reason. Test fixtures use clearly-synthetic values and say so in a
   comment.

4. **No model, no OCR, no LLM/VLM call anywhere in `extract/` or `reporting/`
   without asking first.** Both stages are 100% deterministic on purpose.

5. **Every change ships with tests, and the full suite must stay green.**
   Currently: **268 tests** in `services/orchestrator`, **182** in
   `services/core`. Confirm those numbers before you start, and again before
   you open a PR.

6. **Use a separate database for manual testing, never the one you run
   `pytest` against** — its fixture drops and recreates every table on each
   run.
   ```bash
   createdb satyapramana_test
   export DATABASE_URL=postgresql://localhost/satyapramana_test
   ```

7. **Never invent a new evidence path, field name, or event payload key
   without checking it doesn't already exist.** Grep for the path string
   across `services/orchestrator/satyapramana_store/` before you commit to a
   name — see Suhani's task below for exactly why this matters this round.

8. **Push your branch, open a PR against `main`, do not merge it yourself.**
   CI (`.github/workflows/ci.yml`) runs automatically — check it's green.

9. **If anything is ambiguous, stop and ask.**

---

## SUHANI — the bidder's claimed business name (GST certificate)

**Files you may touch:** `services/orchestrator/satyapramana_store/extract/*.py`,
`services/orchestrator/tests/test_extraction.py`,
`services/orchestrator/tests/conftest_pdf.py`. Nothing else.

### Context

Every field you've extracted so far becomes the one and only fact the rule
engine sees for that path. Nothing today captures what a bidder's *own
document claims* their legal name is, and compares it against what the
*authority* says — which is exactly `docs/satyapramana.md` section 2.2's FUSE
stage: "Reconcile bidder-claimed evidence against authority-returned
evidence. Produce agreement / conflict / gap for each field." The only place
that happens today is the identifier cross-check you already built (PAN vs
the PAN embedded in a GSTIN) — nothing does it for a business's *name*.

**The live `GST_STATUS` adapter already writes to `bidder.gst.legal_name`**
(`adapters/sandbox_co_in.py`, from Sandbox.co.in's real `lgnm` field) — that
path is the *authority's* answer, already live. **Do not extract into that
same path.** `evidence.py`'s fold is "later event wins" — if your extraction
writes there too, whichever ran more recently (usually verification, since
it happens after upload) silently overwrites the other, and a bidder's own
document evidence disappears from the log's read model with no error, no
warning, nothing. This is exactly the landmine rule 7 above is about.

### What to build

Read the business name a GST certificate prints for itself — likely labelled
"Legal Name" or "Trade Name" (a real certificate may have both; check what's
plausible and use your judgement on which to capture, or both under
different paths). Same label/value technique you've now built twice
(`lines()`, a label lookup, the value on the line beneath, structural
validation before acceptance — here, "structurally plausible business name
text" is the bar, not a specific grammar, similar to how you validated a
person's printed name on the PAN card).

**Evidence path:** `bidder.gst.claimed_legal_name` (or `claimed_trade_name`
if you capture that too) — `claimed_` is the meaningful part of the name,
distinguishing it unmistakably from the verification-sourced
`bidder.gst.legal_name`. Grep for whatever you land on before you commit to
it, per rule 7.

This field needs no verification adapter and no rule pack wired to consume
it yet — it's evidence for a future FUSE-stage comparison, not something
that needs to work end-to-end today. Your PR doesn't need `app.py` at all.

### Tests to write

Mirror your existing pattern: a well-formed certificate extracts the claimed
name with correct page/region; a missing label produces nothing; a blank or
label-as-value line produces `EXTRACTION_FAILED`, never a guess. Worth one
test that registers a bidder, extracts a claimed name, and confirms
`bidder.gst.legal_name` (the verification path) is untouched by it — proving
the two paths really are independent.

### Definition of done
```bash
cd services/orchestrator
export DATABASE_URL=postgresql://localhost/satyapramana_test
./venv/bin/python -m pytest tests/ -q          # must stay green, count goes up
```
PR title: "Extract the bidder's claimed GST business name". PR body: the
exact new path name(s).

---

## RISHIKA — CSV export, and (if time allows) a tender-wide blocker summary

**Files you may touch:** `services/orchestrator/satyapramana_store/reporting/csv_export.py`
(new file), `services/orchestrator/satyapramana_store/reporting/blocker_summary.py`
(new file, secondary task), `services/orchestrator/tests/test_reporting.py`.
Nothing else — not `app.py`, not any of your existing `reporting/` files.
Anubrat wires the new endpoint(s) himself once your PR lands.

### Task 1 (priority) — CSV export

### Context

Your Tender Compliance Report answers the aggregate question on-screen. An
officer wants to actually take that list somewhere — into a spreadsheet, an
email, a physical file. Nothing produces that today.

### What to build

```python
def bidders_to_csv(bidders: list[dict]) -> str:
    """`bidders` is exactly GET /tenders/{tender_id}/bidders's "bidders" list
    (the same shape your dossier and tender_report both already consume).
    Returns CSV text, not a file -- the caller decides what to do with it."""
```

Standard library only (`csv` + `io.StringIO`) — no new dependency. Columns:
at minimum `bidder_id`, `risk_level`, `compliance_score`,
`verification_coverage`, `evidence_confidence`, `collusion_flagged`,
`collusion_cluster_id`. A `null` metric renders as an empty cell, **never**
as a fabricated `0` or the string `"null"` — same honesty rule every other
renderer in this codebase follows. Your call on exact column naming/order;
keep it obvious enough that opening the file in a spreadsheet needs no
explanation.

### Tests to write

A multi-bidder fixture with a mix of null and real metrics, parsed back with
`csv.DictReader` to confirm the actual values (not just that it doesn't
crash) — including that a null metric round-trips as an empty string, not
`"None"` or `"0"`. An empty bidder list still produces a valid CSV (header
row only).

### Task 2 (secondary, only if task 1 is done and tested) — tender-wide blocker summary

Each bidder's Bid Autopsy already says which requirements block *them*.
Nothing aggregates that across a tender to answer "which requirement is
blocking the most bidders" — useful for an officer deciding whether a
requirement needs relaxing, or which document type to chase bidders for.

```python
def blocker_summary(autopsies: list[dict]) -> list[dict]:
    """`autopsies` is a list of GET /bidders/{id}/autopsy's real response
    shape (see round 1's brief for the exact fields, or read
    reporting/bid_autopsy.py's autopsy() return directly). Returns one row
    per requirement_id that blocks at least one bidder, sorted by how many
    bidders it blocks (most first), each row naming the requirement, how
    many bidders it blocks, and the classification(s) seen for it."""
```

An `autopsy` where `would_qualify` is `None` (never evaluated) or `True`
(nothing blocking) contributes nothing to the summary — don't let a
not-yet-evaluated bidder register as "blocked by nothing," which would
understate real blockers; just skip bidders that aren't in a determinate
blocked state.

### Definition of done
```bash
cd services/orchestrator
export DATABASE_URL=postgresql://localhost/satyapramana_test
./venv/bin/python -m pytest tests/test_reporting.py -q   # your new tests, green
./venv/bin/python -m pytest tests/ -q                     # full suite, still green
```
PR title: "Add CSV export" (or "...and the tender blocker summary" if you
get to task 2). PR body: a sample CSV output, and if included, one example
blocker-summary output on a multi-bidder fixture.

---

## What happens after both PRs land

Anubrat adds, in `app.py` only:
- `GET /tenders/{tender_id}/report/csv` (or similar) for Rishika's export.
- `GET /tenders/{tender_id}/blockers` if task 2 is included.
- Nothing for Suhani's task — it needs no endpoint of its own yet.

Neither of you touches `app.py` yourselves, same as rounds 1 and 2.
