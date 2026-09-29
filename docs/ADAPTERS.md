# Verification Adapters — SIH26100 / SATYAPRAMĀṆA

Status: **proposed**. Implements charter §7. Depends on `VERDICT_ALGEBRA.md` and
`RULE_PACKS.md`. Adds new files; does not modify the five frozen schemas.

---

## 1. The one rule that shapes everything else

> **An adapter never emits a verdict. It emits observations.**

This is the sibling of the AI/deterministic boundary, and it is just as
load-bearing. An adapter does not decide that a bidder passed. It reports what an
authority said, when it said it, how it was reached, and how sure we are that the
answer is about the right entity. `FUSE` reconciles those observations against
the bidder's claims; `DECIDE` evaluates the rule pack; only then does a verdict
exist.

The practical consequence: an adapter has **no access to the rule pack** and no
knowledge of thresholds. It cannot know whether ₹2.4 crore of turnover passes,
because that fact lives in versioned data it never sees. This is what makes
charter §7's promise real — swapping API Setu for a direct departmental API, or
adding a new authority, touches no rule, no projection, and no screen.

---

## 2. Capability, not adapter, is the unit

The rule engine does not reference adapters. It references **capabilities**.
An adapter is merely something that currently provides some.

```
capability_id      GST_STATUS
provides           bidder.gst.status, bidder.gst.status_history,
                   bidder.gst.legal_name, bidder.gst.registration_date
tier               A
channel            AGGREGATOR
as_of_supported    false
freshness_days     30                (default; overridable per rule pack)
```

Two consequences worth stating:

1. **`provides` is what rule pack validation rule 8 checks against.** A predicate
   referencing `bidder.gst.status` is valid only because some registered
   capability declares it. A rule pack that references an evidence path nothing
   can produce is rejected at adoption, rather than yielding a permanent,
   unexplained `UNKNOWN` in production.
2. **Swapping providers is a manifest change, not a code change.** If you move
   GST from an aggregator to a direct GSTN connection, `channel` becomes
   `DIRECT`, Evidence Confidence rises by the 0.85 → 1.00 factor, and nothing
   else in the system is touched.

---

## 3. Interface

```python
class VerificationAdapter(Protocol):
    manifest: CapabilityManifest

    def verify(self, request: VerificationRequest,
                     ctx: EvaluationContext) -> VerificationOutcome: ...
```

### 3.1 Request

```python
class VerificationRequest(BaseModel):
    capability_id: str
    subject: dict[str, str]        # identifiers: {"gstin": "..."} etc.
    as_of: date | None             # from the rule pack's evaluation context
    lawful_basis: LawfulBasis      # see §7
```

### 3.2 Outcome — a closed sum type

```python
VerificationOutcome = Success | Failure

class Success(BaseModel):
    observations: list[Observation]
    raw_response_ref: str          # content hash into the raw archive
    observed_at: datetime          # when WE asked
    source_asserted_at: date|None  # the date the AUTHORITY says its answer is as of

class Failure(BaseModel):
    code: FailureCode              # §5
    detail: str                    # the real error, never a paraphrase
    raw_response_ref: str | None   # archived even on failure, when a body exists
    retry_after: datetime | None

class Observation(BaseModel):
    path: str                      # e.g. "bidder.gst.status"
    value: str | int | bool | None
    tier: Literal["A","B","C"]
    channel: Literal["DIRECT","AGGREGATOR"]
    subject_match_confidence: float   # see §4
```

`observed_at` and `source_asserted_at` are **two different facts** and conflating
them is a real evidentiary error. We may have asked this morning (`observed_at`)
about a status the authority last refreshed a fortnight ago
(`source_asserted_at`). Freshness is computed from the second, not the first.

---

## 4. Subject match confidence

An authority answers about *an* entity. Whether it is *this* bidder is a separate
question, and adapters must not paper over it.

```
1.00  exact match on a statutory identifier (GSTIN, PAN, CIN, Udyam number)
0.00  no identifier matched — the observation is not about a known subject
```

Values between the two are reserved for adapters that can only be queried by
name, and such an adapter must declare `identifier_queryable: false` in its
manifest. Its observations feed `RESOLVE`, not `DECIDE`, and can never on their
own establish a Tier A fact.

Charter §2.2 states it and it holds here: **identifier match beats semantic
similarity, always.**

---

## 5. Failure taxonomy → verdict consequence

Total, and one-way. Every mapping is declared here, once.

| Code | Cause | Leaf verdict | Reason code | Retry |
|---|---|---|---|---|
| `UNAVAILABLE` | Timeout, connection refused, 5xx | `UNKNOWN` | `AUTHORITY_UNAVAILABLE` | Yes, exponential backoff |
| `RATE_LIMITED` | 429, quota exhausted | `UNKNOWN` | `AUTHORITY_RATE_LIMITED` | Yes, honour `Retry-After` |
| `NOT_FOUND` | Authority holds no matching record | `UNKNOWN` *(see §5.1)* | `AUTHORITY_NOT_FOUND` | No |
| `AMBIGUOUS` | Multiple records matched the subject | `UNKNOWN` | `AUTHORITY_AMBIGUOUS` | No — human review |
| `MALFORMED` | Response failed contract validation | `UNKNOWN` | `AUTHORITY_MALFORMED` | No — alert engineering |
| `UNAUTHORIZED` | Credentials absent, invalid, or expired | `UNKNOWN` | `AUTHORITY_UNAUTHORIZED` | No — alert operations |
| `NOT_CAPABLE` | No registered capability for this path | `UNKNOWN` | `NO_ADAPTER_FOR_FIELD` | No |
| `AS_OF_UNSUPPORTED` | Historical query asked of a present-tense-only source | `UNKNOWN` | `AS_OF_UNSUPPORTED` | No |

**No row maps to `PASS`. No row maps to `FAIL`** — except by the single explicit
mechanism in §5.1. A source being down is not evidence against a bidder, and
allowing infrastructure failure to become an adverse finding is the most damaging
mistake this layer could make.

### 5.1 The one path from failure to `FAIL`

`NOT_FOUND` is tempting to treat as disproof. Usually it is not: the identifier
may have been misread by OCR, or the authority's index may lag.

A capability **may** declare `not_found_is_negative: true` — but only where the
authority's register is *complete and authoritative* for that identifier space,
such that absence genuinely disproves existence. A PAN validity service is a fair
candidate: if the register has no such PAN, the PAN is not valid.

When set, `NOT_FOUND` yields `FAIL` with reason `AUTHORITY_CONTRADICTED`, and the
manifest must carry a `not_found_justification` string naming the register and
why its coverage is complete. That justification is rendered in the UI beside the
verdict, because a `FAIL` derived from an absence is exactly the finding a bidder
will contest.

**Default is `false`.** It is never inferred, and never set to make a demo look
more decisive.

---

## 6. Raw response archive

> When a response is later disputed, the parsed interpretation is not evidence.
> The raw payload is.

Every call archives, immutably and content-addressed by sha256:

| Field | Note |
|---|---|
| `request_url`, `request_method`, `request_body` | **Credentials redacted before archival** |
| `request_headers` | Authorization, API-key and cookie headers replaced with `[REDACTED]` |
| `response_status`, `response_headers`, `response_body` | Verbatim bytes, undecoded, unformatted |
| `observed_at` | Wall clock at the moment of the call |
| `adapter_id`, `adapter_version`, `capability_id` | Attribution to an exact configuration |
| `lawful_basis`, `consent_reference`, `requested_by` | §7 |

Archived on **failure as well as success** — a 500 body is the evidence that the
authority was down, and it is what answers "why is this `UNKNOWN`" eighteen
months later.

Redaction happens **before** the bytes reach storage, never as a display filter.
An archive that has ever held a live API key is a credential-disclosure incident,
and immutable storage means it cannot be cleaned up afterwards.

---

## 7. Lawful basis and consent

Recorded on the verification event, not inferred:

```python
class LawfulBasis(BaseModel):
    basis: Literal["TENDER_EVALUATION", "BIDDER_CONSENT", "PUBLIC_REGISTER"]
    consent_reference: str | None    # required when basis == BIDDER_CONSENT
    requested_by: str                # officer identity
    purpose: str                     # free text, retained
```

`BIDDER_CONSENT` without a `consent_reference` is a validation error, not a
warning. This matters concretely for the API Setu / DigiLocker route, which is
consent-based by design: those calls are only lawful with a consent artefact, and
the artefact must be citable later.

---

## 8. Freshness

```
age = ctx.as_of − (source_asserted_at or observed_at)
window = rule_pack.constants.freshness_days[capability_id]

age ≤ window          fresh    · counts toward Coverage · recency_factor 1.0
window < age ≤ 2×w    stale    · does NOT count toward Coverage
                               · recency_factor decays linearly to recency_floor
                               · leaf carries STALE_VERIFICATION
age > 2×window        expired  · does NOT count toward Coverage
                               · recency_factor = recency_floor
```

A stale verification is not discarded — it is still a real observation and still
shown. It simply stops counting as coverage and stops being fully confident. The
interface must never render a 40-day-old GST status identically to one checked
this morning; every `<EvidenceChip>` carries its `source_asserted_at`.

---

## 9. Temporal queries

`as_of_supported` is declared per capability and it is **never assumed**.

When a predicate uses `active_on` with `context.bid_submission_date` and the
capability does not support historical queries, the adapter returns
`AS_OF_UNSUPPORTED` → `UNKNOWN`. It does **not** answer the present-tense
question and let it stand in for the historical one.

This is a real differentiator and worth saying out loud in the pitch: *"Was this
GST registration active on the bid submission date"* is the question procurement
law actually asks. Most systems silently answer *"is it active today"* instead.
Ours declines to, and says why.

---

## 10. The null adapter

A missing integration is **not** an omission and **not** a mock. It is a
registered adapter with an empty `provides` list that returns `NOT_CAPABLE`.

Being explicit buys real things: the UI can state *"EPFO establishment
verification — no lawful programmatic source available"* rather than silently
having no row; Coverage counts the requirement in its denominator, so the
unverified remainder stays visible; and the rule pack validator can still resolve
the capability id.

Charter §7: *"A missing integration is an adapter with an empty capability
manifest that honestly returns `UNAVAILABLE`. That state must render beautifully
and informatively in the UI, because at v1 it will be common — and handling it
with visible integrity is more impressive than faking coverage."*

---

## 11. Registry — current honest state

`/schemas/capability_registry.json` is the live inventory. As of round 10
(2026-09), one Sandbox.co.in aggregator account backs four live capabilities;
everything else below still resolves to `UNKNOWN`. This is recorded rather
than hidden.

| Capability | Tier | Channel | Status | Note |
|---|---|---|---|---|
| `PAN_STATUS` | A | AGGREGATOR | **LIVE** | Sandbox.co.in KYC; Protean/NSDL direct remains the Tier A DIRECT upgrade path |
| `GST_STATUS` | A | AGGREGATOR | **LIVE** | Sandbox.co.in GST search |
| `CIN_STATUS` | A | AGGREGATOR | **LIVE** | Sandbox.co.in MCA company master data |
| `GST_RETURN_STATUS` | A | AGGREGATOR | **LIVE** | Sandbox.co.in Track GST Returns (round 10); FY-in-progress only, see adapter docstring |
| `DIGILOCKER_DOCUMENT` | A | AGGREGATOR | **LIVE** | Sandbox.co.in DigiLocker (round 10) — real bidder-consent redirect flow, not a server-to-server lookup; `POST /bidders/{id}/digilocker/session` then `GET .../digilocker/status`. Aadhaar only this round. Consent proves a real Aadhaar-verified person, not that they're this bidder — `bidder.digilocker.pan_identity_match` closes that gap by reading the real signed Aadhaar XML's name and cross-checking it against `bidder.pan.holder_name`, the same pattern the GSTIN↔PAN cross-check already uses. Name and DOB only; the XML's address and photo are deliberately never read or stored. |
| `UDYAM_STATUS` | A | AGGREGATOR | **confirmed unavailable** | Checked round 10 against Sandbox's own KYC/KYB catalog — Udyam is not offered by this aggregator account |
| `EPFO_ESTABLISHMENT` | — | — | **null adapter** | No lawful programmatic source. Renders as unavailable. |
| `ESIC_ESTABLISHMENT` | — | — | **null adapter** | As above |
| `ITR_FILING` | — | — | **null adapter** | Confirmed round 10: Sandbox's ITR-V API requires the calling org to be a registered ERI with the Income Tax Department — a legal/business registration, not an API credential |

Verification Coverage is no longer honestly 0% — PAN, GST registration, GST
return filing, and CIN/MCA21 are real, live, aggregator-backed checks today.
The remaining rows are confirmed gaps, each with a specific reason, not
unresearched placeholders.

Scraping the CAPTCHA-walled portals is not the fallback. Charter §3.2: absence of
an API is an `UNAVAILABLE` capability, not an invitation.
