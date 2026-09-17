# Round 9 planning — not started, no tasks assigned yet

Design doc, not a `NEXT_TASKS` brief, same as `ROUND_8_PLANNING.md` was
before it became one. Round 8 (Temporal Scrubber + financial extraction)
is fully merged and live; nothing here is scheduled until you say so.

Three candidates, each verified against the actual current code, not
guessed.

---

## 1. Close the collusion gap the Temporal Scrubber left open

**Why this one first:** round 8's `as-of` endpoint ships with a stated,
honest limitation — the `collusion_note` field says plainly that
collusion status is current, not historical, because `collusion_clusters()`
has no time dimension. This closes that gap for real, finishing what round
8 started rather than opening new territory.

**Verified while scoping this:** it's fully buildable. Two things the
current SQL function lacks a seq bound on both turn out to already be
recorded as real events, not just live table state:
- Edges: `SHARED_ATTRIBUTE_OBSERVED` events already have `seq` — just add
  `AND seq <= p_seq` to `collusion_clusters()`'s `edge` CTE.
- Membership: `bidder_in_tender` (the table the function currently reads
  for tender membership) has **no timestamp or seq column at all** — it
  can only say who's registered *now*. But `BIDDER_REGISTERED` (`app.py`,
  the same endpoint that inserts into `bidder_in_tender`) is a real event
  with its own `seq`, recorded every time a bidder is registered. Read
  membership from that instead of the table, filtered by the same
  ceiling, and the whole function becomes genuinely seq-bounded.

**The change:** a new SQL function `collusion_clusters_as_of(p_tender,
p_seq)` in `sql/002_projections.sql`, identical to `collusion_clusters`
except both source queries gain the seq filter above. `app.py`'s
`bidder_as_of` endpoint calls it instead of the live one, and the
`collusion_note` either goes away entirely or changes to state plainly
that collusion *is* now computed as of the checkpoint — whichever reads
more honestly once it's real. `active_pack_as_of`'s existing pattern
(join to `events` for a real seq, in `rulepacks.py`) is the template to
follow — same shape, one more table.

**Tests:** two bidders who share an attribute *after* a checkpoint must
show unflagged at that checkpoint and flagged today; a bidder registered
*after* a checkpoint must not appear in that checkpoint's cluster at all
(the real reason `bidder_in_tender` alone isn't enough). Same concurrency
pattern as the round-8 backend PR — real live rebuilds alongside real
as-of reads, asserting neither corrupts the other.

---

## 2. Self-declaration / undertaking capture (closes `DECLARATION`)

**What it is:** the one remaining unbacked requirement type that isn't
actually an extraction problem. `requirement_types.py` lists it as "no
self-attestation capture mechanism exists yet" — but a self-declaration
was never going to come from a document extractor, because an undertaking
*is* the self-declaration; there's nothing to independently verify it
against, by definition, not by current limitation. That makes this the
cleanest of the seven remaining unbacked types to close: unlike
`MIN_TURNOVER`, this one's evidence tier is honestly self-declared
forever, and that's the whole story, not a caveat.

**The real feature:** a bidder (in their own portal — round 6 already
built this side, self-service submission flow) or an officer on the
bidder's behalf formally records an attestation: "I/we declare that
[requirement text]," tied to who recorded it and when. A new event type,
e.g. `DECLARATION_RECORDED` (`bidder_id`, `tender_id`, `requirement_id`
or the declaration's own text, `declared_by`, `declared_at`), feeding a
new evidence path (`bidder.declarations.<requirement_id>` or similar —
worth deciding the exact path shape before building, since it's one
declaration per requirement, not one global fact like a PAN number).

**Where it fits:** the bidder portal's submission flow
(`SubmitDocumentsPage.jsx`, round 6/Suhani's work) is the natural home —
a declaration a bidder ticks and signs alongside their document uploads,
not a separate disconnected flow. `HUMAN_EVENT_TYPES` in `events.py`
would need this new type added (it's the frozen set of event types a
`HUMAN` actor is allowed to produce — check that file before assuming
it's just a wiring change).

**Tests:** the predicate resolves (`exists`, matching the type's
`suggested_ops`) against a real recorded declaration; an unrecorded one
resolves honestly to missing, not a guess; the audit trail shows exactly
who attested and when, same as every other human-attributed action.

---

## 3. Financial figures are unreadable everywhere they're shown

**What's wrong, concretely:** round 8's `MIN_TURNOVER`/`NET_WORTH`
correctly normalize to INR paise internally (so a rule pack's `gte`
compares like with like) — but nothing on the frontend converts that back
for a human. Checked directly: no file under `frontend/src` formats a
paise value at all. Today an officer looking at a bidder's evidence sees
a raw integer like `4500000000000000` with no currency formatting,
wherever a financial value is shown — the Evidence tab's raw value
column, Bid Autopsy, Compliance Repair, the CSV report export, and now
the Temporal Scrubber's History tab.

**The fix:** one shared formatter (e.g. `lib/currency.js`,
`formatPaiseAsRupees(value)`) that converts paise back to a real Indian
number format — ₹ symbol, lakh/crore grouping (`Intl.NumberFormat` with
`"en-IN"` gets the grouping right; the ₹ prefix and paise conversion need
writing by hand). Wired into every place a `bidder.financials.*` value
currently renders as a bare number — smaller in code, but genuinely
touches several files, so worth its own slot rather than a rider on
another task.

**Worth deciding first, not assumed:** should the formatter also show the
figure in its *original* stated unit ("₹45,00,00,000 — stated as 45,000
lakh") alongside the normalized rupee figure, so an officer can sanity-
check the extraction against what the document actually printed? That's
a real provenance question, not just a display one — worth a look at
whether the original unit/magnitude is even still available on the
evidence record (`extract/financials.py`'s `Candidate.detail` string has
it in prose, e.g. `"'45,00,00,000' read as ... lakh"` — parseable, but
worth deciding if it should be its own structured field instead of text
to parse).

---

## One thing worth researching before committing to it, not part of this round's committed scope

**ITR filing status** — `requirement_types.py` currently treats this the
same as every other "no capability yet" type, but unlike EPFO/ESIC (which
`docs/STATUS.md` confirms has no lawful source *anywhere*, permanently),
nobody has actually checked whether Sandbox.co.in or a similar aggregator
offers a real ITR-filing-status product the way it does for PAN/GST/CIN.
Worth a real look before round 10's planning, not a guess either way here.

---

## Recommended sequencing

1. Collusion `as-of` — smallest, most self-contained, directly finishes
   round 8's own stated gap.
2. Self-declaration capture — a real new feature, but no extraction
   complexity; the event-log/evidence-path pattern is now well-worn
   (four rounds of precedent to follow).
3. Currency formatting — do last specifically because it should reflect
   whatever the declaration path's own evidence shape turns out needing
   too, if step 2 surfaces a similar "how do we show self-declared
   evidence honestly" question.

Once you say go, this becomes `NEXT_TASKS_9_*.md` with people and files
assigned — not before.
