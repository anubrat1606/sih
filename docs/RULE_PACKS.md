# Rule Packs — SIH26100 / SATYAPRAMĀṆA

Status: **proposed**. Depends on `VERDICT_ALGEBRA.md`. Adds new files; does not
modify the five frozen schemas in `/schemas`.

A rule pack is the declarative, versioned, content-addressed encoding of one
tender's compliance requirements. It is **data, not code**. There is no `if`
statement anywhere in the system that decides whether a bidder is compliant.

Machine-validated against `/schemas/rule_pack.schema.json`.

---

## 1. Why this exists

Three properties fall out of rules-as-data that are unobtainable from
rules-as-code, and each one is a question a judge or an auditor will actually ask:

| Question | Answer |
|---|---|
| *"What if the tender had said ₹5 crore instead of ₹3 crore?"* | Re-evaluate the same evidence against rule pack v2. No redeployment, no model re-run. |
| *"Which rule produced this rejection?"* | The verdict records `rule_pack_version`, which is a content hash. The exact bytes are recoverable. |
| *"Did you change the rules after seeing the bids?"* | Rule packs are content-addressed and their adoption is an event in the log with a timestamp. Amendment creates a new version; it never mutates history. |

---

## 2. Identity and versioning

```
rule_pack_id       cpcl.tender.2026.GEM-XXXXXX      (stable across versions)
semver             1.2.0
content_hash       sha256 of canonical JSON         (see §2.1)
rule_pack_version  cpcl.tender.2026.GEM-XXXXXX@1.2.0+a3f9c81b4e22
```

`rule_pack_version` is what every verdict records. It is the full triple, because
semver alone is forgeable by editing in place and a hash alone is unreadable.

### 2.1 Canonicalisation

The content hash is taken over the pack serialised as JSON with keys sorted
lexicographically, no insignificant whitespace, UTF-8, and `\n` line endings —
**excluding** the `content_hash` field itself. Two packs with the same hash are
byte-identical after canonicalisation. Authors may write YAML; the canonical form
for hashing is always JSON.

### 2.2 Amendment

A rule pack is immutable once adopted. Amending it means publishing a new
version and emitting a `RULE_PACK_ADOPTED` event. Verdicts already recorded keep
pointing at the old version and remain reproducible forever. A corrigendum to a
live tender is therefore modelled correctly and for free: two rule pack versions,
both citable, with the switchover timestamped.

---

## 3. Structure

```yaml
rule_pack_id: cpcl.tender.2026.GEM-XXXXXX
semver: 1.0.0
tender_reference:
  tender_id: GEM-XXXXXX
  source_document_sha256: <hash of the tender PDF as ingested>
  issuing_authority: Chennai Petroleum Corporation Limited

constants:                      # every tunable lives here, never in code
  partial_credit: 0.50
  w_mandatory: 1.00
  w_desirable: 0.30
  recency_floor: 0.50
  corroboration_step: 0.10
  coverage_floor_high: 50
  coverage_floor_medium: 80
  confidence_floor: 70
  freshness_days:
    GST_STATUS: 30
    PAN_STATUS: 90
    CIN_STATUS: 90
    UDYAM_STATUS: 180

requirements:
  - id: R4
    text: "Bidder shall hold valid GST registration and PAN, and demonstrate any 3 of 5 listed work orders."
    source: { page: 14, region: [72, 410, 523, 468] }
    obligation: mandatory
    operator: ALL_OF
    children: [ R4.1, R4.2, R4.3 ]

  - id: R4.1
    text: "Valid GST registration, active as on the bid submission date."
    source: { page: 14, region: [72, 470, 523, 494] }
    obligation: mandatory
    operator: LEAF
    predicate:
      op: active_on
      subject: { field: bidder.gst.status_history }
      at:      { context: bid_submission_date }
```

Every requirement carries `source: { page, region }` pointing into the **tender
document**. This is the other half of provenance: the bidder-side chain runs
verdict → evidence → extracted region in the *bid*, and this one runs verdict →
rule → quoted clause in the *tender*. Both halves are needed before an officer
can defend a rejection.

`operator` is one of `ALL_OF` · `ANY_OF` · `K_OF_N` · `NOT` · `LEAF`, per
`VERDICT_ALGEBRA.md` §2. `K_OF_N` additionally requires `k`.

`obligation` is `mandatory` or `desirable`. It drives the scoring weight, the
Tier C ceiling, and the risk function — all three read it, none of them redefine it.

---

## 4. The predicate language

Closed, small, total, and deterministic. There is no escape hatch, no expression
string, no embedded code. If a tender clause cannot be expressed here, that is a
finding to surface for human review — **not** a licence to add an operator ad hoc.

### 4.1 Operators

| Class | Operators |
|---|---|
| Comparison | `eq` `ne` `gt` `gte` `lt` `lte` |
| Set | `one_of` `not_one_of` |
| String | `matches` (anchored, RE2-safe, no backtracking) |
| Existence | `exists` |
| Temporal | `date_before` `date_after` `date_between` `active_on` |
| Logical | `not` `all` `any` |

### 4.2 Operands

| Kind | Form | Notes |
|---|---|---|
| Field | `{ field: bidder.gst.status }` | Path into the fused evidence projection |
| Literal | `{ literal: 30000000000 }` | Currency in **integer minor units** (paise); dates ISO-8601 |
| Context | `{ context: bid_submission_date }` | See §5 |
| Aggregate | `{ aggregate: mean, over: …, select: …, window: … }` | See §4.3 |

### 4.3 Aggregates

```yaml
predicate:
  op: gte
  left:
    aggregate: mean
    over: bidder.financials
    select: annual_turnover_minor
    window: { last_n: 3, order_by: fiscal_year_end, direction: desc }
  right:
    literal: 30000000000        # ₹3,00,00,000 in paise
```

`aggregate` is one of `sum` `mean` `min` `max` `count`. Arithmetic is exact:
integer minor units throughout, no floating point in any monetary path. A
turnover threshold decided by IEEE-754 rounding is not defensible.

If the `window` cannot be satisfied — three financial years requested, two
present — the aggregate is **undefined**, not computed over what is available.
The predicate yields `UNKNOWN`. Silently averaging two years against a
three-year threshold is exactly the kind of quiet substitution charter §3.1 bans.

### 4.4 Three-valued evaluation — the important part

**Predicates do not return booleans.** They return `PASS`, `FAIL`, or `UNKNOWN`.

```
resolve(operand):
    if the underlying evidence is absent, unextracted, or its
    verification failed  →  ⊥ (undefined), carrying the reason from
                            the evidence record itself

evaluate(predicate):
    if any operand resolves to ⊥  →  UNKNOWN, with the reason code
                                     propagated from that operand
    else                          →  PASS or FAIL by the operator
```

A missing field is never `false`. `exists` is the sole operator that legitimately
consumes absence and returns `FAIL` — and it may only do so when the evidence
record positively records "this document was not submitted," never when the
record is simply missing because a check never ran. Those are different facts and
the projection keeps them distinct.

**`PARTIAL` is never produced by a predicate.** It enters the system in exactly
two places: the Tier C clamp (`VERDICT_ALGEBRA.md` §3) and composition
(`VERDICT_ALGEBRA.md` §2). This is an invariant worth asserting in CI — it keeps
the leaf layer honest and means every `PARTIAL` on screen has a traceable cause.

### 4.5 Derived bindings

Each requirement's set of consumed evidence paths is **computed** by walking its
predicate tree, never hand-declared. Hand-declared bindings drift from the
predicate the moment someone edits one and not the other, and a drifted binding
produces a verdict whose provenance chain points at the wrong evidence — a §3.4
defect. The validator emits the derived set; CI asserts it round-trips.

These bindings are what the Verification Coverage metric counts and what
`<ProvenanceTrail>` walks.

---

## 5. Evaluation context — no wall clock, ever

```yaml
evaluation_context:
  as_of: 2026-09-10T00:00:00Z        # when this evaluation is deemed to occur
  bid_submission_date: 2026-09-22
  tender_id: GEM-XXXXXX
  bidder_id: B-0001
  rule_pack_version: cpcl.tender.2026.GEM-XXXXXX@1.0.0+a3f9c81b4e22
```

**No predicate may read the system clock.** Every temporal comparison resolves
against `context.as_of` or `context.bid_submission_date`. This is not
fastidiousness — it is the precondition for charter §3.9. A rule that calls
`date.today()` produces a different verdict tomorrow from the same evidence, which
makes replay-determinism untestable and time-travel impossible.

> **Live defect this catches:** `services/verification/main.py` currently compares
> `date_of_expiry` against `date.today()`. Under replay that check silently
> changes its answer. It must take `as_of` from the context.

Note also that `bid_submission_date` is the correct subject of nearly every
validity question. *"Was this GST registration active on the submission date"* is
a materially different — and more correct — question than *"is it active now,"*
and answering the second while claiming the first is a real evidentiary error.

---

## 6. Authoring pipeline

```
tender PDF ──▶ SEGMENT ──▶ requirement decomposition ──▶ human review ──▶ rule pack
              (VLM)         (LLM: proposes atomic          (mandatory)     (data)
                             requirements + operator
                             + candidate predicate)
```

The LLM **proposes** a draft rule pack. It is decomposing prose, classifying
obligation, and suggesting structure — all squarely inside the permitted column
of charter §5. It never adopts one.

Adoption is a human act, recorded as a `RULE_PACK_ADOPTED` event with the
reviewing officer's identity, the content hash, and a timestamp. Between proposal
and adoption sits a diff view: quoted tender clause on the left, generated
predicate on the right.

Every proposed requirement the decomposer is unsure of is emitted with
`review_required: true` and a stated ambiguity. Those block adoption. A rule pack
containing an unreviewed uncertain requirement cannot be adopted — this is
validated, not merely advised.

---

## 7. Validation

`validate_rule_pack()` is deterministic and gates adoption. It rejects a pack that:

1. fails `/schemas/rule_pack.schema.json`
2. contains a requirement id that is duplicated, or a child reference that does not resolve
3. contains a cycle in the requirement graph — the structure must be a tree
4. declares `K_OF_N` with `k < 1` or `k > len(children)`
5. declares `LEAF` without a predicate, or a non-`LEAF` without children
6. declares `NOT` with other than exactly one child
7. uses an operator or operand kind outside §4
8. references an evidence path with no producing stage or adapter
9. references a currency literal that is not an integer
10. contains any temporal operand other than `context.*`
11. contains `review_required: true` on any requirement
12. omits `source.page` on any requirement
13. has a `content_hash` disagreeing with its canonical form

Rules 8 and 10 are the two that matter most and are easiest to skip: 8 is what
prevents a requirement that can never be evaluated from silently becoming a
permanent `UNKNOWN`, and 10 is what makes determinism enforceable rather than
aspirational.

---

## 8. Worked example

The R4 tree from `VERDICT_ALGEBRA.md` §7, fully encoded. The requirement text is
**illustrative pending a real tender PDF** — it must be replaced with quoted
prose from an actual GeM document before any demo, and the `source` regions
filled from that document's real layout.

```yaml
requirements:
  - id: R4
    text: "Bidder shall hold valid GST registration and PAN, and demonstrate any 3 of 5 listed work orders."
    source: { page: 14, region: [72, 410, 523, 468] }
    obligation: mandatory
    operator: ALL_OF
    children: [R4.1, R4.2, R4.3]

  - id: R4.1
    text: "Valid GST registration, active as on the bid submission date."
    source: { page: 14, region: [72, 470, 523, 494] }
    obligation: mandatory
    operator: LEAF
    predicate:
      op: active_on
      subject: { field: bidder.gst.status_history }
      at: { context: bid_submission_date }

  - id: R4.2
    text: "Valid PAN issued in the name of the bidding entity."
    source: { page: 14, region: [72, 496, 523, 520] }
    obligation: mandatory
    operator: LEAF
    predicate:
      op: all
      of:
        - { op: eq, left: { field: bidder.pan.status }, right: { literal: VALID } }
        - { op: eq, left: { field: bidder.pan.holder_name_canonical },
                    right: { field: bidder.entity.legal_name_canonical } }

  - id: R4.3
    text: "Any three of the five listed categories of work order."
    source: { page: 15, region: [72, 120, 523, 340] }
    obligation: mandatory
    operator: K_OF_N
    k: 3
    children: [R4.3.WO1, R4.3.WO2, R4.3.WO3, R4.3.WO4, R4.3.WO5]

  - id: R4.3.WO1
    text: "Work order — category A, value not less than ₹1 crore, completed within the last 5 years."
    source: { page: 15, region: [90, 140, 523, 172] }
    obligation: mandatory
    operator: LEAF
    predicate:
      op: all
      of:
        - { op: exists, subject: { field: bidder.work_orders.cat_a } }
        - { op: gte, left: { field: bidder.work_orders.cat_a.value_minor },
                     right: { literal: 10000000000 } }
        - { op: date_after, left: { field: bidder.work_orders.cat_a.completion_date },
                            right: { context: bid_submission_date_minus_5y } }
```

Note `R4.2`: the second conjunct compares the PAN holder's name to the entity's
legal name, both **canonical** forms produced by NORMALIZE. This is where entity
resolution meets the rule engine, and it is deterministic — identifier and
canonical-string equality, never semantic similarity. If RESOLVE could not
produce a canonical name, the operand is ⊥ and R4.2 is `UNKNOWN`, not `FAIL`.
The bidder is not penalised for our inability to normalise their name.
