# Next tasks — Suhani and Rishika, one each, zero file overlap

**Read this whole file before writing any code. Paste your own section — and
only your own section, plus the Hard Rules — into your own fresh Claude Code
session.** Your session has no memory of the conversation that produced this
document. Everything it needs to know is written down here.

Anubrat has already merged both of your prior work into `main`:
Suhani's CIN extraction (`extract/`) and a first Rishika-lane pass, Bid
Autopsy + Compliance Repair (`reporting/`), which Anubrat built directly since
nobody had started that lane yet. This document hands the next piece of each
of your own lanes back to each of you.

**These two tasks touch completely disjoint files.** Followed as written,
neither of you can produce a merge conflict with the other, or with Anubrat's
own work. That's not an accident — it's the point of this document.

---

## Hard rules — apply to both of you, no exceptions

1. **Start from latest `main`.** `git checkout main && git pull origin main`,
   then `git checkout -b feat/<yourname>-<topic>`. Never branch off anything
   else, never work on `main` directly.

2. **Only touch the files your section names.** Not "files near them," not
   "files that seemed related" — the exact list. If finishing your task truly
   seems to require touching a file outside that list, **stop and message
   Anubrat.** Don't touch it yourself, even to fix something that looks like a
   bug — flag it and let him make the call, the same way he's been leaving
   your two lanes alone rather than guessing at what you'd want.

3. **No mock, sample, fabricated, or guessed data — anywhere, ever, including
   tests.** This is the one non-negotiable principle the entire codebase is
   built around. A field that can't be read for real becomes `null` with a
   stated reason. A value the code isn't sure of is never invented to fill a
   gap. If you're tempted to hardcode a plausible-looking value "just to get
   something working," stop — that's exactly the failure mode this project
   exists to refuse. Test fixtures use clearly-synthetic values (see the
   existing `conftest_pdf.py` for the pattern) and say so in a comment; they
   never pretend to be real documents.

4. **No model, no OCR, no LLM/VLM call anywhere in `extract/` or `reporting/`
   without asking first.** Both of these stages are currently 100%
   deterministic — regex grammars with structural validation, or plain
   Python over already-computed data. That's deliberate (see
   `docs/satyapramana.md` section 5: "if you removed every model from this
   system, it must still produce correct verdicts"). If you think a task
   genuinely needs a model, stop and say so instead of wiring one in —
   picking an LLM/VLM provider is a decision Anubrat makes explicitly, the
   same way the Sandbox.co.in verification provider was picked, not something
   a coding session decides on its own.

5. **Every change ships with tests, and the full suite must stay green.**
   Currently: 198 tests in `services/orchestrator`, 182 in `services/core`.
   Run them before you start (confirm those numbers), and again before you
   open a PR (confirm your new tests are counted and nothing broke).

6. **Use a separate database for testing, not whatever `DATABASE_URL` you use
   for manual poking-around.** The test suite's fixture *drops and recreates
   every table* at the start of each run — if you point it at a database with
   real demo data in it, that data is gone.
   ```bash
   createdb satyapramana_test
   export DATABASE_URL=postgresql://localhost/satyapramana_test
   ```

7. **Never invent a new evidence path name, field name, or event payload key
   that isn't specified below.** These are load-bearing contracts other code
   already depends on. If your task seems to need a new one, use exactly the
   name given in your section — don't improvise a similar-looking
   alternative.

8. **Push your branch, open a PR against `main`, do not merge it yourself.**
   Anubrat reviews and merges (branch protection requires it). State in the
   PR description what changed and the exact command to verify it.

9. **If anything in your section is ambiguous or seems to contradict the
   existing code, stop and ask** rather than resolving it by guessing. A
   wrong assumption here is expensive to unwind later — this whole codebase's
   culture is "ask, don't guess," not a suggestion.

---

## SUHANI — PAN holder name/DOB extraction, and a cross-document identifier check

**Files you may touch:** `services/orchestrator/satyapramana_store/extract/*.py`,
`services/orchestrator/tests/test_extraction.py`,
`services/orchestrator/tests/conftest_pdf.py`. Nothing else. In particular:
**do not touch `app.py`** — both tasks below are designed so you never need
to; see the note at the end of each task for why.

### Context you need

This is `services/orchestrator/satyapramana_store/extract/` — deterministic
INGEST and the candidate half of EXTRACT, no model anywhere. It reads a PDF's
text layer (`layout.py`: `Page`, `Word`, exact bounding boxes), scans for
statutory identifiers by regex grammar (`grammars.py`), validates them
structurally, and records each one with its exact page and region
(`ingest.py`). You already know this file — you wrote the CIN grammar that's
merged into it now.

`FIELD_PATHS` in `ingest.py` maps a grammar field name to the evidence path
it becomes: `{"gstin": "bidder.gst.gstin", "pan_number": "bidder.pan.pan_number",
"udyam_number": "bidder.udyam.udyam_number", "cin": "bidder.entity.cin"}`.
Every `FIELD_EXTRACTED` event carries `path`, `value`, `page`, `region`,
`confidence` (always `1.0` here — a structural grammar match, not a model's
self-reported confidence), `basis`, `detail`.

### Task 1 (priority) — PAN holder name and date of birth

The live `PanStatusAdapter`
(`services/orchestrator/satyapramana_store/adapters/sandbox_co_in.py`) calls
Sandbox.co.in's real PAN verification endpoint, which requires the holder's
**name as printed on the card** and **date of birth**, not just the PAN
number. Right now extraction only captures the number, so this adapter
permanently refuses with `MALFORMED` — it's live and tested, but has never
fired for real. This is the single biggest thing blocking real PAN
verification.

**What to build:** extract the holder's name and date of birth from a PAN
document's text layer, deterministically — no OCR, no model. A PAN card has
a fixed, standardised layout issued by the Income Tax Department (printed
labels like "Name" / "Permanent Account Number" / "Date of Birth" with the
value on the next line or immediately after). Use `layout.py`'s existing
`Word`/`Page` primitives to find the value near its label — this is
structurally similar to what the *old, retired* `services/extraction`
scaffold did with a naive "next line below the label" heuristic (see
`CLAUDE.md`'s note calling that heuristic weak); do it more carefully this
time, and validate what you find structurally before accepting it:

- Date of birth must parse as a real calendar date. Sandbox.co.in requires
  the format `DD/MM/YYYY` specifically (see the adapter's `pan_date_of_birth`
  usage) — if what's on the card isn't cleanly convertible to that, record
  `EXTRACTION_FAILED` with the real reason rather than guessing a format.
- A name with no plausible letters, or a "next line" that's actually another
  label, is a failed extraction, not a low-confidence guess. Never emit a
  value you're not structurally sure of.

**New evidence paths (use these exact names):**
- `bidder.pan.holder_name`
- `bidder.pan.date_of_birth`

Add them to `FIELD_PATHS` the same way the existing four are declared, and
emit `FIELD_EXTRACTED` (page + region, same as every other field) or
`EXTRACTION_FAILED` for each, following the exact same pattern as every
existing field in `ingest.py`.

**Tests to write** (mirror the CIN tests you already wrote in
`test_extraction.py` — same shape, same rigor): a well-formed PAN document
extracts both fields with correct page/region; a document where the name or
DOB can't be found or doesn't validate produces `EXTRACTION_FAILED`, not a
guessed value; the values survive through to the provenance trail
(`GET /bidders/{id}/requirements/{rid}/provenance`) the same way your CIN
test proved for CIN.

**Why you don't need to touch `app.py`:** `app.py`'s `verify()` already
resolves whatever evidence paths exist into the capability's request subject
— once these two paths exist, Anubrat makes a two-line addition there to wire
them through to `PanStatusAdapter`. You don't need to touch it, and please
don't — just get the two paths extracting correctly and say so in your PR.

### Task 2 (if time allows, lower priority) — cross-document identifier check

`ingest.py` has `_identifier_cross_check()`: if a GSTIN and a PAN are both
found, it checks the PAN embedded in the GSTIN (characters 3–12) against the
PAN actually read — "identifier match beats semantic similarity" (see the
docstring). **The bug:** it only looks at `extracted`, the list from the
*single* `ingest_document()` call it's inside. If a bidder uploads their PAN
card and GST certificate as two separate files — the realistic case — this
check never fires at all, because each upload only sees its own document's
fields.

**What to build:** make the check see the bidder's *accumulated* evidence,
not just the current upload. When a new GSTIN or PAN is extracted, look up
whether the *other* identifier was already extracted from a *previous*
upload for this bidder, and run the same cross-check against that combined
picture.

**Constraint that keeps this off `app.py`:** query the `proj_evidence` table
directly with SQL (`conn` is already available inside `ingest_document()`) —
`SELECT value FROM proj_evidence WHERE bidder_id=%s AND path=%s AND
resolved=true` for `bidder.gst.gstin` / `bidder.pan.pan_number` — rather than
calling `rebuild_evidence()`, which needs a `Registry` object `ingest.py`
doesn't currently have and that would mean touching how `app.py` calls this
function. At the point `ingest_document()` runs, `proj_evidence` reflects
every *prior* upload's extracted facts (the current upload's own fields
aren't folded in yet — `app.py` calls `rebuild_evidence()` right after
`ingest_document()` returns) — which is exactly what you want: prior facts
from the projection, current facts from this call's own `extracted` list.

**Test to write:** upload a PAN document, then upload a GST document as a
*separate* `ingest_document()`/API call for the same bidder, and confirm the
cross-check now fires (an `ENTITY_RESOLVED` event, or whatever your
implementation emits — reuse the existing pattern) exactly as it would if
both were on one page.

### Definition of done, both tasks
```bash
cd services/orchestrator
export DATABASE_URL=postgresql://localhost/satyapramana_test
./venv/bin/python -m pytest tests/ -q          # must stay green, count goes up
```
PR title: state which task(s) are included. PR body: the exact new evidence
paths added (task 1) and/or a one-line description of the cross-document fix
(task 2).

---

## RISHIKA — the Compliance Dossier

**Files you may touch:** `services/orchestrator/satyapramana_store/reporting/dossier.py`
(new file), `services/orchestrator/tests/test_reporting.py`. Nothing else —
in particular, **do not touch `app.py`, `bid_autopsy.py`, or
`compliance_repair.py`.** Your function is designed to be pure and
self-contained precisely so it can't collide with any of those; Anubrat wires
the one new endpoint himself afterward.

### Context you need

`services/orchestrator/satyapramana_store/reporting/` is your lane
(`CONTRIBUTING.md`). It already has two modules, both deterministic, both
derived from already-computed data, no model involved:

- `bid_autopsy.py` — `autopsy(pack, verdict_rows) -> dict`: why a bid would
  fail right now.
- `compliance_repair.py` — `repair_plan(pack, verdict_rows, registry) -> dict`:
  the forward-looking inverse, one action per curable gap.

`docs/satyapramana.md` section 11 lists **Reporting** as its own module,
distinct from those two — a general compliance report/export, not a
diagnostic. That's what this task builds: a **Compliance Dossier**, the
single artifact an officer would actually print, attach to a decision file,
or hand to a supervisor. Combines a bidder's full picture — score, risk,
verdicts, the autopsy, the repair plan — into one document.

### What to build

A new file, `reporting/dossier.py`, with two pure functions:

```python
def build_dossier(bidder: dict, autopsy: dict, repair: dict) -> dict:
    """Combine the three already-computed views into one exportable artifact."""

def render_dossier_text(dossier: dict) -> str:
    """A plain-text rendering suitable for printing, emailing, or pasting into
    a decision file. Not HTML, not PDF -- plain text, headed sections,
    tabular-ish alignment where it helps (see the tone of docs/STATUS.md or
    CONTRIBUTING.md for the plain-text style this project already uses)."""
```

**Neither function touches a database, calls an API, or does I/O.** They
take plain dicts, return plain dicts/strings. This is why you don't need
`app.py`, `conn`, or a `Registry` — the three inputs are *exactly* what
these three real endpoints already return, so you can build and test this
entirely from fixtures shaped like their real responses, below.

**`bidder`** — exactly what `GET /bidders/{id}?tender_id=...` returns:
```json
{
  "bidder_id": "A", "tender_id": "T1",
  "verdicts": [{"requirement_id": "R1", "verdict_system": "FAIL",
                "reason_system": "AUTHORITY_CONTRADICTED",
                "verdict_effective": "FAIL", "reason_effective": "AUTHORITY_CONTRADICTED",
                "overridden_by": null, "override_justification": null,
                "rule_pack_version": "..."}],
  "metrics": {"compliance_score": 62.5, "verification_coverage": 40.0,
              "verification_coverage_mandatory": 50.0, "evidence_confidence": 71.2},
  "risk": {"level": "HIGH", "triggers": ["collusion_edge"], "function_version": "..."},
  "collusion": {"flagged": true, "cluster_id": "cluster_A_B", "members": ["A", "B"]}
}
```
Any of `metrics`' four values can be `null` (never a guessed `0` — an em
dash or "not determined" in the text rendering, never a number). `collusion`
can be `null` (no cluster).

**`autopsy`** — exactly what `GET /bidders/{id}/autopsy` returns (see
`bid_autopsy.py`'s `autopsy()` return shape directly if you want the
authoritative version):
```json
{
  "would_qualify": false,
  "blocking_requirements": [{"requirement_id": "R1", "text": "...",
                              "verdict": "FAIL", "reason_code": "AUTHORITY_CONTRADICTED",
                              "classification": "FATAL", "overridden_by": null}],
  "counterfactual": {"curable_requirement_ids": ["R2"],
                      "would_qualify_if_cured": false,
                      "still_blocking_after_cure": ["R1"]},
  "note": null
}
```
`would_qualify` can be `null` (not yet evaluated) — see `note` for why.
`counterfactual` can be `null` (nothing curable, or already qualifying).

**`repair`** — exactly what `GET /bidders/{id}/repair-plan` returns:
```json
{
  "actions": [{"requirement_id": "R2", "text": "...", "reason_code": "MANDATORY_DOCUMENT_ABSENT",
               "evidence_paths": ["bidder.gst.gstin"], "authority": "Goods and Services Tax Network",
               "actionable_by": "BIDDER",
               "action": "Upload a document providing bidder.gst.gstin."}],
  "note": null
}
```

### What the dossier should contain

Your call on exact structure, but it must include, at minimum: bidder and
tender identifiers, the three metrics (rendered honestly — `null` never
becomes `0`, exactly like every other renderer in this codebase), risk level
and triggers, collusion status, the full verdict list, the blocking
requirements with their FATAL/CURABLE classification, and the repair actions
grouped by who can act on them (`BIDDER` vs `SYSTEM` — never present a
`SYSTEM` gap as something the bidder needs to fix, same rule the repair plan
itself follows). `render_dossier_text()` should read like something a human
would actually want to print, not a JSON dump with different punctuation.

### Tests to write

Mirror the style already in `test_reporting.py` — plain dict fixtures (no
database), one test per meaningful case: a fully-qualifying bidder, a bidder
blocked by a mix of fatal and curable gaps, a bidder with `null` metrics
(never evaluated), a bidder with no collusion cluster. At least one test
should assert on `render_dossier_text()`'s actual output containing the
right facts (not just that it doesn't crash).

### Definition of done
```bash
cd services/orchestrator
export DATABASE_URL=postgresql://localhost/satyapramana_test
./venv/bin/python -m pytest tests/test_reporting.py -q   # your new tests, green
./venv/bin/python -m pytest tests/ -q                     # full suite, still green
```
PR title: "Add the Compliance Dossier". PR body: paste one example of
`render_dossier_text()`'s output on a realistic fixture, so Anubrat can see
the actual shape before wiring the endpoint.

---

## What happens after both PRs land

Anubrat adds, in `app.py` only (so this never touches your branches):
- The two-line subject-resolution addition for `pan_holder_name`/`pan_date_of_birth`.
- `GET /bidders/{id}/dossier`, calling `get_bidder()` + `autopsy()` +
  `repair_plan()` and passing their output straight into `build_dossier()`.

Both of you are done once your own PR is green and merged — you don't need
to wait for the other, and you don't need to touch `app.py` yourselves.
