# Next tasks, round 2 — Suhani and Rishika, one each, zero file overlap

**Read this whole file before writing any code. Paste your own section — and
only your own section, plus the Hard Rules — into your own fresh Claude Code
session.** Your session has no memory of the conversation that produced this
document. Everything it needs to know is written down here.

Round 1 (`docs/NEXT_TASKS_suhani_rishika.md`) is done and merged: Suhani's
PAN holder name/DOB extraction and cross-document identifier check, Rishika's
Compliance Dossier. Both PRs went in clean, on the first review, with zero
merge conflicts — because both stayed exactly inside the file scope given to
them. Do the same here.

Anubrat is taking the major remaining piece himself this round (the design
system — tokens and the evidence-native UI primitives, `docs/satyapramana.md`
section 2.3) directly in `frontend/`. **Neither of you touches `frontend/`
in this round** — that overlap is the one thing to avoid above everything
else, since it's actively being worked on right now.

---

## Hard rules — apply to both of you, no exceptions (same as round 1)

1. **Start from latest `main`.** `git checkout main && git pull origin main`,
   then `git checkout -b feat/<yourname>-<topic>`.

2. **Only touch the files your section names.** If finishing your task truly
   seems to require touching a file outside that list — **especially
   anything under `frontend/`, which is mid-work right now** — stop and
   message Anubrat rather than touching it yourself.

3. **No mock, sample, fabricated, or guessed data — anywhere, ever, including
   tests.** A field that can't be read for real becomes `null` with a stated
   reason. Test fixtures use clearly-synthetic values and say so in a
   comment; they never pretend to be real documents.

4. **No model, no OCR, no LLM/VLM call anywhere in `extract/` or `reporting/`
   without asking first.** Both stages are 100% deterministic on purpose. If
   a task seems to need a model, stop and say so instead of wiring one in.

5. **Every change ships with tests, and the full suite must stay green.**
   Currently: 235 tests in `services/orchestrator`, 182 in `services/core`.
   Confirm those numbers before you start, and again before you open a PR.

6. **Use a separate database for manual testing, never the one you run
   `pytest` against.** The test suite's fixture drops and recreates every
   table at the start of each run.
   ```bash
   createdb satyapramana_test
   export DATABASE_URL=postgresql://localhost/satyapramana_test
   ```

7. **Never invent a new evidence path, field name, or event payload key that
   isn't specified below** without a documented reason in your PR. These are
   load-bearing contracts other code depends on.

8. **Push your branch, open a PR against `main`, do not merge it yourself.**
   State in the PR description what changed and the exact command to verify
   it. CI (`.github/workflows/ci.yml`) runs automatically on your PR now —
   check it's green before flagging the PR as ready.

9. **If anything is ambiguous, stop and ask** rather than resolving it by
   guessing.

---

## SUHANI — document issue/expiry dates

**Files you may touch:** `services/orchestrator/satyapramana_store/extract/*.py`,
`services/orchestrator/tests/test_extraction.py`,
`services/orchestrator/tests/conftest_pdf.py`. Nothing else, and — this round
especially — **not `frontend/`.**

### Context

Your own feature proposal (`featureproposals.md` #4): `date_of_issue` /
`date_of_expiry` are not populated by extraction anywhere today. This is a
real gap, not just a missing view — `docs/STATUS.md` has flagged it since
before the architecture rebuild. Once these exist, a rule pack can express
"this document must not be expired" as an ordinary `date_before`/`date_after`
predicate (`satyapramana.predicates.evaluate` already supports both), the
same way GST's `active_on` check already works against
`bidder.gst.status_history`.

### What to build

Extend your label/value reader (`lines()`, `find_pan_holder_fields()` in
`ingest.py` — you already built the pattern, this is the same technique
applied to a second document layout) to locate a printed "Date of Issue" /
"Issued on" / "Valid until" / "Date of Expiry" label and the date beneath or
beside it, deterministically, no model. Structural validation before
acceptance, exactly like every other field: a real calendar date, and a
plausible range (an issue date in the future, or an expiry date before the
document's own issue date, is not a value to accept silently — record
`EXTRACTION_FAILED` with the real reason).

**Start with GST** (it already has a real consumer — `active_on` against
`bidder.gst.status_history` needs exactly this kind of date to be meaningful
for a bid-submission-date check) and extend to other document types only if
time allows. Your call on exact label text to match — GST certificates and
Udyam registrations don't use identical wording, so this may need more than
one label pattern per document type, the same way you handled "Name" vs
"Date of Birth" as two separate label lookups on the PAN card.

**Evidence paths:** follow the existing `bidder.<doctype>.<field>`
convention — e.g. `bidder.gst.date_of_issue` / `bidder.gst.date_of_expiry`.
Pick names consistent with that pattern for whichever document type(s) you
cover; state exactly which paths you added in your PR description so
Anubrat can wire anything that needs them.

### Tests to write

Mirror your own PAN holder-field tests: a well-formed document extracts the
date(s) with correct page/region; a missing label produces no candidate at
all (not a failure — the label simply isn't there); a found label with an
implausible value (not a real date, an issue date after an expiry date, etc.)
produces `EXTRACTION_FAILED` with the real reason, never a guess.

### Definition of done
```bash
cd services/orchestrator
export DATABASE_URL=postgresql://localhost/satyapramana_test
./venv/bin/python -m pytest tests/ -q          # must stay green, count goes up
```
PR title: "Extract document issue/expiry dates". PR body: the exact new
evidence paths, and which document type(s) they cover.

---

## RISHIKA — the Tender Compliance Report

**Files you may touch:** `services/orchestrator/satyapramana_store/reporting/tender_report.py`
(new file), `services/orchestrator/tests/test_reporting.py`. Nothing else —
same as round 1, **do not touch `app.py`, `bid_autopsy.py`,
`compliance_repair.py`, or `dossier.py`**, and not `frontend/` this round.
Anubrat wires the one new endpoint himself once your PR lands, same as last
time.

### Context

The Compliance Dossier (your round 1 work, merged) answers "what's the full
picture for *this one bidder*." Nothing yet answers the tender-wide question
an officer actually opens the dashboard to ask first: "of everyone who bid,
where do we stand overall?" That's this task — an aggregate report across
every bidder on a tender, not a diagnostic for one.

### What to build

One pure function:

```python
def tender_report(tender_id: str, bidders: list[dict]) -> dict:
    """`bidders` is exactly GET /tenders/{tender_id}/bidders's "bidders"
    list -- each element is exactly what GET /bidders/{id} returns (see the
    shape below). No database, no I/O, no recomputation of anything already
    computed -- this only aggregates."""
```

**`bidders[i]`** — exactly the same shape documented in round 1's brief
(`docs/NEXT_TASKS_suhani_rishika.md`, the `bidder` fixture under your
original dossier task) — `bidder_id`, `metrics` (any of the four can be
`null`), `risk` (`level` + `triggers`), `collusion` (can be `null`),
`verdicts`.

**What the report should contain**, at minimum:

- Total bidder count.
- Risk distribution: count of `LOW` / `MEDIUM` / `HIGH`.
- Collusion summary: how many distinct clusters, how many bidders flagged,
  which cluster each flagged bidder belongs to (don't recompute clustering —
  just group what's already in each bidder's `collusion` field).
- Compliance score summary: mean, min, max, computed **only over bidders
  whose `compliance_score` is not `null`** — and report separately *how
  many* bidders had a `null` score (nothing determinate yet), never let a
  `null` silently drop out of the denominator without saying so. This is the
  same honesty rule the dossier and every metric renderer in this codebase
  already follows for a single bidder; apply it here at the aggregate level.
- Same treatment for `verification_coverage` and `evidence_confidence`.

Your call on the exact key names and whether to add a
`render_tender_report_text()` companion the way `dossier.py` has
`render_dossier_text()` — consistent with that file's style is a reasonable
default, but not mandatory.

### Tests to write

Plain dict fixtures (no database) — mirror `test_reporting.py`'s existing
style. Cases worth covering: an empty tender (zero bidders — every count is
zero or the aggregate is honestly "no data", never a fabricated number); a
mix of `null` and real scores (confirm the mean excludes `null`s and the
"how many were null" count is correct); a tender with two separate collusion
clusters, one bidder unflagged; a tender where every bidder is `HIGH` risk.

### Definition of done
```bash
cd services/orchestrator
export DATABASE_URL=postgresql://localhost/satyapramana_test
./venv/bin/python -m pytest tests/test_reporting.py -q   # your new tests, green
./venv/bin/python -m pytest tests/ -q                     # full suite, still green
```
PR title: "Add the Tender Compliance Report". PR body: paste one example
output on a realistic multi-bidder fixture.

---

## What happens after both PRs land

Anubrat adds `GET /tenders/{tender_id}/report` in `app.py` — calls
`list_tender_bidders()`'s underlying data and `tender_report()`, nothing
more. Neither of you touches `app.py` yourselves, same as round 1.
