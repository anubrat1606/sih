# Verdict Algebra — SIH26100 / SATYAPRAMĀṆA

Status: **proposed**, pending approval of the v2 schema change (supersedes the
`PASS | FAIL | MISMATCH | UNVERIFIED` status enum in `/schemas/verification_result.schema.json`).

This is the semantic centre of the product. Schema, adapters, scoring, UI and
reports are all downstream of it. It is deliberately written as a specification,
not as code, so it can be reviewed before anything depends on it.

---

## 1. States

| State | Meaning | Never means |
|---|---|---|
| `PASS` | Requirement satisfied, corroborated by evidence of stated sufficiency | "Bidder claimed it and nothing contradicted them" |
| `FAIL` | Requirement demonstrably not satisfied, with **positive evidence of the failure** | "We couldn't check" |
| `PARTIAL` | Satisfied on some sub-conditions, unsatisfied or unverifiable on others | A polite `FAIL` |
| `UNKNOWN` | Insufficient or unavailable evidence to determine | `FAIL`, or `PASS` |

`UNKNOWN` is not a failure state. No display, filter, export or metric may
collapse it into `FAIL`.

The old `MISMATCH` status is not a fifth state. A mismatch is a `FAIL` carrying
reason code `IDENTIFIER_MISMATCH` — the distinction lives in the reason code,
where reports and appeals can machine-read it.

---

## 2. Composition — one function, not three

Requirements form a tree. Interior nodes compose their children under one of
three operators. **All three are the same function.**

Let a node have children with verdict counts:

- `p` = count of `PASS`
- `f` = count of `FAIL`
- `r` = count of `PARTIAL`
- `u` = count of `UNKNOWN`
- `n` = p + f + r + u
- `k` = threshold (see below)

```
compose(children, k):
    if p >= k:            return PASS      # enough are proven satisfied
    if p + r + u < k:     return FAIL      # too many proven failures; k is unreachable
    if p > 0 or r > 0:    return PARTIAL   # some ground gained, remainder unresolved
    return UNKNOWN                          # the entire gap is unverified
```

The second line is the important one: `p + r + u` is the **best attainable
count** if every unresolved child later resolved in the bidder's favour. If even
that optimum falls short of `k`, the requirement is demonstrably unreachable,
which is the definition of `FAIL`.

The three operators are threshold choices, not separate logic:

| Operator | k | Meaning |
|---|---|---|
| `ALL_OF` (conjunctive) | `k = n` | every child required |
| `ANY_OF` (disjunctive) | `k = 1` | one child suffices |
| `K_OF_N` | `k` declared in the rule pack | "any 3 of 5 work orders" |

### 2.1 Derived table — `ALL_OF` (k = n)

| ∧ | PASS | FAIL | PARTIAL | UNKNOWN |
|---|---|---|---|---|
| **PASS** | PASS | FAIL | PARTIAL | PARTIAL |
| **FAIL** | FAIL | FAIL | FAIL | FAIL |
| **PARTIAL** | PARTIAL | FAIL | PARTIAL | PARTIAL |
| **UNKNOWN** | PARTIAL | FAIL | PARTIAL | UNKNOWN |

Note `PASS ∧ UNKNOWN = PARTIAL`, not `UNKNOWN`. Real ground was gained on one
conjunct; the officer needs to see that it was partially established rather than
wholly undetermined. Note also that `FAIL` is absorbing: one proven-failed
mandatory conjunct settles the conjunction regardless of what else is unknown.

### 2.2 Derived table — `ANY_OF` (k = 1)

| ∨ | PASS | FAIL | PARTIAL | UNKNOWN |
|---|---|---|---|---|
| **PASS** | PASS | PASS | PASS | PASS |
| **FAIL** | PASS | FAIL | PARTIAL | UNKNOWN |
| **PARTIAL** | PASS | PARTIAL | PARTIAL | PARTIAL |
| **UNKNOWN** | PASS | UNKNOWN | PARTIAL | UNKNOWN |

Note `FAIL ∨ UNKNOWN = UNKNOWN`, not `FAIL` — the unknown disjunct might still
have satisfied the requirement, so nothing is proven.

### 2.3 Negation

For requirements phrased in the negative ("must not appear on a debarment list"):

| v | `NOT v` |
|---|---|
| PASS | FAIL |
| FAIL | PASS |
| PARTIAL | PARTIAL |
| UNKNOWN | UNKNOWN |

`NOT` is an involution: `NOT(NOT v) = v` for all four states. `UNKNOWN` must not
negate to `PASS` — not being able to find someone on a debarment list is not
evidence of absence from it, and treating it as such is precisely the failure
mode §3.3 of the charter exists to prevent.

### 2.4 Properties (these are the CI tests)

`compose` is **commutative**, **associative** and **idempotent** in its children,
so folding a child list left, right, or in any permutation yields the same
verdict. This is what makes §3.9 determinism testable rather than aspirational:
verdicts cannot depend on document upload order, adapter response order, or
map iteration order.

Assert in CI, exhaustively over all 4^n child combinations for n ≤ 4:

1. `compose` is order-independent
2. `ALL_OF` and `ANY_OF` agree with the pairwise tables above
3. `compose(children, k=n) == fold(∧, children)` and `compose(children, k=1) == fold(∨, children)`
4. No input combination produces a state outside the four
5. `NOT(NOT v) == v`

---

## 3. The Tier C ceiling

From charter §6, and this is the sharpest anti-fraud property in the system:

> **A mandatory requirement resting solely on Tier C (self-declared) evidence can
> never reach `PASS`. Its ceiling is `PARTIAL`.**

Applied as a **clamp at the leaf**, before composition — so it propagates upward
through the fold automatically and needs no special handling at interior nodes:

```
leaf_verdict(requirement, evidence):
    v = evaluate(requirement, evidence)
    if v == PASS
       and requirement.mandatory
       and all(e.tier == C for e in evidence.supporting):
        return PARTIAL with reason SELF_DECLARED_CEILING
    return v
```

"Solely" is load-bearing: a self-declaration corroborated by any Tier A or Tier B
item is not clamped. The clamp fires only when the bidder's own word is the
entire basis for a mandatory requirement.

### Evidence tiers

| Tier | Definition | Confidence factor |
|---|---|---|
| **A** | Authority-verifiable — independently confirmed against a government source | 1.00 |
| **B** | Issuer-attested — bank, OEM, auditor, certification body; identifiable but not queryable at v1 | 0.70 |
| **C** | Self-declared — asserted by the bidder alone | 0.40 |

### Channel

Tier is *what* the source is; channel is *how* it was reached. An aggregator's
answer is not the authority's own answer, and the distinction must be recorded:

| Channel | Factor |
|---|---|
| `DIRECT` — the authority's own API | 1.00 |
| `AGGREGATOR` — a licensed intermediary relaying it | 0.85 |

This is an addition to the charter, justified: at v1 almost all Tier A
verification will run through aggregators, and a system that renders an
aggregator response identically to a direct one is overstating its own evidence.

---

## 4. Reason codes

Every verdict carries a machine-readable reason code alongside its prose.
Reports, filters, analytics and appeals consume the code; only humans read prose.

**PASS** — `AUTHORITY_CONFIRMED` · `CORROBORATED_MULTI_SOURCE` · `THRESHOLD_MET`

**FAIL** — `AUTHORITY_CONTRADICTED` · `IDENTIFIER_MISMATCH` · `THRESHOLD_NOT_MET` ·
`DOCUMENT_EXPIRED` · `MANDATORY_DOCUMENT_ABSENT` · `REGISTRATION_INACTIVE` ·
`SUBREQUIREMENT_UNREACHABLE`

**PARTIAL** — `SELF_DECLARED_CEILING` · `SUBSET_SATISFIED` · `CORROBORATION_INCOMPLETE` ·
`STALE_VERIFICATION`

**UNKNOWN** — `AUTHORITY_UNAVAILABLE` · `AUTHORITY_RATE_LIMITED` · `AUTHORITY_NOT_FOUND` ·
`AUTHORITY_AMBIGUOUS` · `AUTHORITY_MALFORMED` · `AUTHORITY_UNAUTHORIZED` ·
`AS_OF_UNSUPPORTED` · `NO_ADAPTER_FOR_FIELD` · `EXTRACTION_FAILED` · `ENTITY_UNRESOLVED`

The six `AUTHORITY_*` codes are exactly the adapter failure taxonomy of charter
§7. **None of them may map to `PASS`.** The mapping is total and it is one-way:
every adapter failure becomes `UNKNOWN` at the leaf, never `FAIL` — a source
being down is not evidence against the bidder.

The single exception is documented in `ADAPTERS.md` §5.1: a capability whose
register is complete and authoritative for its identifier space may declare
`not_found_is_negative`, turning `NOT_FOUND` into `FAIL` with
`AUTHORITY_CONTRADICTED`. It defaults to false, requires a written
justification in the manifest, and is never inferred.

---

## 5. The three metrics

Orthogonal by construction. Computed independently. **Never averaged, never
blended into a badge.** A bid at 100 / 40 / 60 is a materially different
procurement risk from one at 100 / 95 / 95, and the interface must make that
impossible to miss.

Constants marked *(rule pack)* are declared in the versioned rule pack, not
hard-coded, so that a verdict can always be attributed to an exact configuration.

### 5.1 Compliance Score

*Of the requirements we could determine, how many are satisfied?*

Domain: **determinate** requirements only — verdict in {`PASS`, `FAIL`, `PARTIAL`}.
`UNKNOWN` requirements are excluded from both numerator and denominator; they are
the subject of Verification Coverage, not of this metric.

```
credit(PASS)    = 1.0
credit(PARTIAL) = partial_credit        (rule pack, default 0.50)
credit(FAIL)    = 0.0

weight(mandatory) = w_mandatory         (rule pack, default 1.00)
weight(desirable) = w_desirable         (rule pack, default 0.30)

ComplianceScore = 100 × Σ weight(i)·credit(i) / Σ weight(i)     over determinate i
```

**If the denominator is zero, the score is `null` — not `0`.** Every renderer must
show `—` and never a numeral. A `0` reads as "totally non-compliant" when the
truth is "nothing could be determined," and that specific confusion is the exact
failure this whole design exists to prevent. Enforce with a CI test.

### 5.2 Verification Coverage

*What fraction was checked against an authoritative source at all, versus resting
on self-declaration?*

Domain: **all** requirements, including `UNKNOWN` ones. That is the entire point —
the denominator is what makes the unverified remainder visible.

```
verified(i) = requirement i has ≥ 1 supporting evidence item of Tier A
              whose verification is within its freshness window

Coverage         = 100 × |{i : verified(i)}| / |all requirements|
CoverageMandatory = 100 × |{i : verified(i) ∧ mandatory(i)}| / |{i : mandatory(i)}|
```

Report both. Mandatory coverage is what an officer actually acts on. A stale
verification does **not** count as covered — it counts as `STALE_VERIFICATION`,
which is why the freshness clause is inside the predicate.

`<CoverageMeter>` renders the unverified remainder explicitly and is structurally
incapable of showing 100% when coverage is partial.

### 5.3 Evidence Confidence

*How reliable is the evidence underlying those determinations?*

Domain: determinate requirements. Per requirement, multiplicative, capped at 1.0:

```
conf(i) = tier_factor(i)
        × channel_factor(i)
        × extraction_factor(i)
        × recency_factor(i)
        × corroboration_bonus(i)

tier_factor(i)     = max over supporting evidence of {A:1.00, B:0.70, C:0.40}
channel_factor(i)  = factor of the channel that produced the tier-defining item
extraction_factor(i) = MIN extraction confidence across every field feeding i
recency_factor(i)  = 1.0 within freshness window;
                     decaying linearly to recency_floor (rule pack, default 0.50)
                     across a second window of equal length; then recency_floor
corroboration_bonus(i) = 1 + corroboration_step × (independent_sources(i) − 1)
                     (rule pack, default step 0.10)

EvidenceConfidence = 100 × mean over determinate i of min(conf(i), 1.0)
```

`extraction_factor` uses **MIN, not mean** — weakest link. A requirement resting
on one field read at 0.4 confidence and three at 0.95 is a 0.4-confidence
requirement, because the doubtful field can still be the wrong one.

### 5.4 Enforcement

A CI test asserts that no API response, projection, export or component prop ever
carries a single fused figure derived from more than one of these three. The
charter forbids it in prose; this makes it a build failure.

---

## 6. Risk classification

Deterministic function of the three metrics plus conflict signals. Versioned
exactly like a rule pack. **Never a model's opinion.**

```
HIGH   if any of:
         ∃ mandatory requirement with verdict FAIL
         ∃ mandatory requirement with verdict UNKNOWN
         ∃ identifier conflict (PAN embedded in GSTIN disagrees, CIN mismatch, …)
         ∃ collusion edge to another bidder on the same tender
         ∃ mandatory document expired at the bid-submission date
         CoverageMandatory < coverage_floor_high      (rule pack, default 50)

MEDIUM if any of:
         ∃ mandatory requirement with verdict PARTIAL
         ∃ mandatory requirement resting solely on Tier C evidence
         CoverageMandatory < coverage_floor_medium    (rule pack, default 80)
         EvidenceConfidence < confidence_floor        (rule pack, default 70)
         ∃ desirable requirement with verdict FAIL
         ∃ verification outside its freshness window

LOW    otherwise
```

Evaluated in order; first match wins. A mandatory `UNKNOWN` is `HIGH` risk and
this is deliberate — "we could not verify a mandatory requirement" is a serious
procurement risk even though it is not a compliance failure. This is the cleanest
demonstration in the product that `UNKNOWN ≠ FAIL` while still being taken
seriously.

---

## 7. Worked example

Tender requirement 4: *"Bidder shall hold valid GST registration, PAN, and
demonstrate any 3 of 5 listed work orders."*

```
R4  ALL_OF
├── R4.1  GST registration active on bid-submission date
│         Tier A, DIRECT via aggregator (channel 0.85), verified today
│         → PASS  (AUTHORITY_CONFIRMED)
├── R4.2  PAN valid and active
│         Tier A, AGGREGATOR, verified today
│         → PASS  (AUTHORITY_CONFIRMED)
└── R4.3  K_OF_N, k=3, n=5   (work orders)
    ├── WO-1  authority-corroborated        → PASS
    ├── WO-2  authority-corroborated        → PASS
    ├── WO-3  self-declared only, mandatory → PARTIAL (SELF_DECLARED_CEILING)
    ├── WO-4  issuer letter, unreachable    → UNKNOWN (AUTHORITY_UNAVAILABLE)
    └── WO-5  dated after bid deadline      → FAIL    (DOCUMENT_EXPIRED)
```

R4.3: p=2, r=1, u=1, f=1, k=3.
`p >= k`? 2 >= 3 no. `p+r+u < k`? 4 < 3 no. `p > 0`? yes → **`PARTIAL`**
(`SUBSET_SATISFIED`). Correct: two are proven, a third is reachable through either
WO-3 or WO-4, so this is neither settled nor doomed.

R4: `ALL_OF` over {PASS, PASS, PARTIAL} → no FAIL, not all PASS → **`PARTIAL`**.

Metrics for this subtree: Compliance Score `100 × (1+1+0.5)/3 = 83`.
Coverage `2/3 = 67%` (R4.3 has no single Tier A item covering the composite).
Confidence for R4.1 = `1.00 × 0.85 × extraction × 1.0` — the aggregator channel is
visible in the number, as it should be.

The officer sees **83 / 67 / n** — and the 67 is what tells them a third of this
requirement rests on the bidder's own word.
