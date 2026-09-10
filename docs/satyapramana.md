# SIH26100 — SATYAPRAMĀṆ
### Master Build Prompt · AI-Powered Integrated Bid Compliance Verification Platform for GeM Procurement
**Problem Statement:** SIH26100 · Software Edition · Smart Automation
**Sponsor:** Ministry of Petroleum & Natural Gas — Chennai Petroleum Corporation Limited (CPCL)
**Document class:** Architecture charter. Not a feature request. Not a chat prompt.
 
> *Working codename. `satya` (truth) + `pramāṇa` (valid means of knowledge / evidence). Replace if the team prefers — but keep a name. Nameless projects look like homework.*
 
---
 
## 0 · How to read this document
 
You are not being asked to "build an app." You are being asked to design a **sovereign-grade evidentiary system** that a procurement officer will one day cite in a tender rejection that gets challenged in court.
 
Assume that adversary. Every design decision in this document is downstream of one question:
 
> **If this decision is contested eighteen months from now, can the system reproduce exactly how it was reached, from what evidence, under which rule version, verified against which authority, at what timestamp — without anyone re-running a model?**
 
If the answer is no, the design is wrong. Not suboptimal. Wrong.
 
**Output of this pass is architecture, not code.** Do not write application code. Do not scaffold repositories. Do not create migrations. Produce the artefacts listed in §9, then stop and wait for approval.
 
---
 
## 1 · Product charter
 
**What it is:** A decision-support platform that ingests a tender, ingests a bidder's submission, independently verifies claims against authoritative government sources, and produces a per-requirement compliance verdict with a complete evidentiary chain behind every single one.
 
**What it is not:**
- Not a chatbot. Not a copilot. Not a "ask questions about your tender" surface.
- Not an auto-rejector. It never disqualifies a bidder. It hands a human officer a defensible, reproducible dossier and lets them decide.
- Not a document summariser with a compliance skin on it.
**Primary user:** A tender evaluation officer under time pressure and audit exposure, reviewing dozens of bids against hundreds of atomic requirements.
 
**The product promise, in one line:**
*Every verdict on this screen can be traced to a page number, an authority, a rule version, and a timestamp — in two clicks.*
 
---
 
## 2 · The three architectural commitments
 
These three commitments define *how* this system is built. They are not preferences. They replace the conventional approach outright, and §10 lists exactly what they replace.
 
---
 
### 2.1 · Commitment I — An append-only evidentiary core
 
**Nothing in this system is ever updated in place. Nothing is ever deleted.**
 
There is no `compliance_status` column that gets overwritten. There is no `verified = true` flag that gets flipped. Those are the artefacts of systems that cannot explain themselves.
 
Instead:
 
- The **write model** is an immutable, ordered, cryptographically chained log of **facts that happened**: a document was ingested, a field was extracted, an authority was queried, a rule was evaluated, an officer overrode a verdict.
- Every event carries: monotonic sequence, event type, payload, actor (human / agent / adapter, with identity), causation ID (what caused this), correlation ID (which evaluation run it belongs to), wall-clock timestamp, and hash of the previous event.
- **Current compliance state is a projection** — a materialised read model derived by folding the event log. It is a cache. It can be dropped and rebuilt from zero at any time and must produce byte-identical output.
- **Audit trail is not a feature.** It is not a table someone remembers to write to. It is the substrate the entire system is made of. There is no code path that changes state without emitting an event, because there is no other way to change state.
**What this buys, that the conventional design cannot:**
 
| Capability | Why it falls out for free |
|---|---|
| Time-travel — "show me this bid's status as of 14 March, 09:40" | Fold events up to that sequence number |
| Counterfactual replay — "re-run this bid under rule pack v2.3" | Replay the same extraction events against a different rule version |
| Adversarial audit — "prove nobody edited this after the decision" | Hash chain breaks if they did |
| Regression safety — "did the new extractor change any historical verdict?" | Replay the full corpus, diff the projections |
| Zero-cost provenance | Provenance *is* the causation chain, not metadata bolted alongside it |
 
**Design rule:** if you find yourself writing an `UPDATE` statement against a compliance table, you have violated this commitment. Projections are rebuilt, never patched.
 
---
 
### 2.2 · Commitment II — A typed, replayable agent pipeline
 
The AI in this system is **not a service you call**. It is a **sequence of narrow, typed, individually-evaluated stages**, orchestrated by deterministic code that the model never controls.
 
Model the pipeline as a **directed acyclic graph of stages**, where every stage:
 
1. Declares a **typed input contract** and a **typed output contract** (Pydantic → JSON Schema → generated TypeScript; one source of truth, never hand-mirrored).
2. Is **individually replayable** — given the same inputs and the same stage version, it can be re-run in isolation.
3. Is **individually evaluated** — has a golden-set fixture suite with accuracy thresholds that gate CI. A stage with no eval set cannot ship.
4. Emits its output as **events**, never as mutations.
5. Records **stage version, model identifier, prompt hash, and parameters** on every output, so any result can be attributed to an exact configuration.
**The stages:**
 
```
INGEST ──▶ SEGMENT ──▶ EXTRACT ──▶ NORMALIZE ──▶ RESOLVE ──▶ VERIFY ──▶ FUSE ──▶ DECIDE ──▶ SCORE ──▶ EXPLAIN
  det.      VLM/det.     VLM        LLM+det.      LLM+det.    adapters  det.     det.       det.      LLM
```
 
- **INGEST** — deterministic. Hash, store, register, classify container type.
- **SEGMENT** — page/region segmentation, document-type classification. VLM proposes, deterministic validator accepts.
- **EXTRACT** — VLM reads the document. Emits *candidate field values with page number, bounding region, and self-reported confidence*. It extracts. It does not conclude.
- **NORMALIZE** — canonicalise formats: dates to ISO-8601, currency to integer minor units, entity names to a canonical form, identifiers to their statutory format. LLM proposes normalisations for messy input; deterministic validators enforce the target grammar and reject anything malformed.
- **RESOLVE** — entity resolution across documents. Is the "M/s Alpha Industries Pvt Ltd" on the GST certificate the same legal entity as "ALPHA INDS. PRIVATE LIMITED" on the work order? LLM proposes linkage with reasoning; deterministic identifier matching (PAN embedded in GSTIN, CIN, Udyam number) confirms or refuses. **Identifier match beats semantic similarity, always.**
- **VERIFY** — adapter layer. Deterministic. Calls authoritative sources. See §7.
- **FUSE** — deterministic. Reconcile bidder-claimed evidence against authority-returned evidence. Produce agreement / conflict / gap for each field.
- **DECIDE** — **fully deterministic. Zero model involvement.** Evaluate the rule pack against fused evidence. Emit a verdict per atomic requirement.
- **SCORE** — deterministic. Compute the three independent metrics (§4.2).
- **EXPLAIN** — LLM renders the already-final decision into officer-readable prose. It is a **narrator**, not a judge. It receives the verdict and the evidence chain as input and may not alter either. If the explainer is unavailable, the system still returns complete, correct, structured verdicts — the prose is a presentation layer, not a dependency.
**The hard boundary, stated once:** the model's outputs are *inputs to* the decision. The model is never *in* the decision.
 
---
 
### 2.3 · Commitment III — Design system before screens
 
Build the design language **before** the first screen exists. Not after. Not "we'll polish it later." Later never arrives, and the difference between a platform that looks state-issued and a dashboard that looks like a hackathon submission is decided in this step.
 
**Ship a design foundation first, as a real artefact:**
 
- **Design tokens** — a single typed token source (color, spacing, radius, elevation, motion duration/easing, type scale) that both Tailwind config and the component layer consume. No hard-coded hex values anywhere in the application. Ever.
- **Dual theme, both first-class.** Light theme is the default for daylight office use; dark is not an afterthought. Every token is defined in both. Neither is a filter over the other.
- **Typography as hierarchy, not decoration.** One display family, one text family, one tabular-numeral mono for identifiers, amounts, dates and scores. Identifiers and figures **never** render in a proportional font — GSTINs, PANs, CINs and currency must align vertically down a column.
- **Restraint as the visual signature.** Institutional confidence comes from generous whitespace, precise alignment, a narrow palette, and typographic authority — not gradients, glow, glassmorphism, or decorative iconography. The system should feel closer to a central bank terminal than to a SaaS landing page.
- **Semantic status colour is a locked, accessible four-value scale** — PASS / FAIL / PARTIAL / UNKNOWN — that meets WCAG 2.2 AA contrast in both themes, is never used decoratively for anything else, and is **never the only carrier of meaning**. Every status is colour **plus** glyph **plus** label. An officer with deuteranopia reads the same verdict.
- **Motion is functional and it is short.** 120–200ms, standard easing, used only to communicate state change, causality, or spatial relationship. Nothing loops. Nothing bounces. `prefers-reduced-motion` is honoured everywhere, not on a subset of components.
- **Density is a mode, not a compromise.** Officers reviewing 200 requirements need a compact mode; a mentor being walked through the system needs comfortable. Ship both, driven by tokens.
**Then build the evidence-native component primitives.** These are the components that make this product feel unlike anything else in the room, and they must exist in the design system before any page uses them:
 
| Primitive | What it does |
|---|---|
| **`<EvidenceChip>`** | Any rendered fact — a date, an amount, a status — is a chip. Hovering reveals its source; clicking opens the source document at the exact page with the extracted region highlighted. A number on screen is never orphaned from its origin. |
| **`<VerdictBadge>`** | The four-value verdict, rendered identically everywhere in the product. One component, one appearance, zero drift. |
| **`<ProvenanceTrail>`** | The causation chain for a single verdict, rendered as a walkable path: requirement → rule version → fused evidence → extraction event(s) → source page → authority response → timestamp. |
| **`<CoverageMeter>`** | Renders verification coverage honestly — including the unverified remainder. Visually incapable of showing 100% when coverage is partial. |
| **`<TemporalScrubber>`** | Drag to move the entire evaluation view backward through the event log. The screen re-renders as the projection at that sequence. |
| **`<ConflictCard>`** | Bidder claim vs authority response, side by side, with the delta made unmissable. |
| **`<RepairAction>`** | A corrective action written as a specific, executable instruction — which document, which field, which authority, which deadline. |
 
**The signature screen — the Evidence Graph.** One tender, one bidder, rendered as a navigable graph: requirements on one axis, evidence nodes beneath, authority verifications beside, edges weighted by verdict and confidence. Click any edge and the `<ProvenanceTrail>` opens. This is the screen that gets remembered. Design it as a serious information-visualisation problem — clear at a glance, precise on inspection, legible when projected in a room — not as a decorative force-directed blob.
 
**The demo axiom:** the single most impressive thing this product can do in front of a judge is **click a green PASS badge and land on the exact highlighted line of a PDF, next to the API response that corroborates it, next to the rule that consumed both, with a timestamp on all three.** Design every screen so that path is always two clicks away.
 
---
 
## 3 · Non-negotiable invariants
 
Violating any of these is a defect, regardless of how well the rest of the system works.
 
**Evidentiary integrity**
 
1. **No mock government data. No fabricated API responses. Not in demos, not in seeds, not in tests-that-double-as-demos.** Where a live authority is unreachable, the system returns `UNKNOWN` with a machine-readable reason — it does not simulate.
2. **No scraping of government portals** unless explicitly permitted in writing and no API alternative exists. Absence of an API is an `UNAVAILABLE` capability, not an invitation.
3. **Missing verification never becomes PASS.** Not "assumed compliant," not "pending → pass," not a default. The absence of evidence is itself a first-class, visible, reportable state.
4. **Every conclusion carries provenance or it does not exist.** A verdict with an unresolvable evidence chain is a bug that must fail CI, not a display quirk.
5. **Page numbers and extracted regions are preserved** from ingestion through to the rendered UI, unbroken.
6. **Verification timestamps are preserved and surfaced.** A GST status verified 40 days ago is not the same fact as one verified this morning, and the interface must never let those look identical. Staleness has a policy, and the policy is visible.
**Decision integrity**
 
7. **No LLM makes a final numerical, date, threshold, status, or eligibility determination.** Ever. Under any prompt. In any fallback path.
8. **Rules are declarative data, not code.** Compliance rules live in versioned, human-readable, machine-validated rule packs — not in `if` statements scattered through services. Rule packs are content-addressed and versioned; every verdict records the exact rule pack version that produced it. Amending a rule never mutates history.
9. **Determinism is testable and tested.** The same evidence plus the same rule pack must produce the identical verdict, every time, on every machine. This is enforced by a replay harness in CI, not by convention.
10. **Human override is a first-class, recorded event** — with actor identity, justification text, and timestamp — never a silent database edit. An officer may overrule the system; the system remembers that they did.
**System integrity**
 
11. **Four verdict states, never three, never a boolean.** `PASS` · `FAIL` · `PARTIAL` · `UNKNOWN`. `UNKNOWN` is not a failure state and must never be collapsed into `FAIL` for convenience of display.
12. **Three independent metrics, never fused into one number.** Compliance Score, Evidence Confidence, Verification Coverage (§4.2). A single blended "trust score" destroys the exact information an auditor needs.
13. **No technology beyond the locked stack** (§8) without an explicit written justification and approval. Every added dependency is future audit surface.
---
 
## 4 · The verdict algebra
 
Define this formally before anything else is designed. It is the semantic centre of the product, and everything — schema, adapters, UI, reports — is downstream of it.
 
### 4.1 · Verdict states
 
| State | Meaning | Never means |
|---|---|---|
| `PASS` | Requirement satisfied, corroborated by evidence of stated sufficiency | "Bidder claimed it and nothing contradicted them" |
| `FAIL` | Requirement demonstrably not satisfied, with positive evidence of the failure | "We couldn't check" |
| `PARTIAL` | Requirement satisfied on some sub-conditions, unsatisfied or unverifiable on others | A polite `FAIL` |
| `UNKNOWN` | Insufficient or unavailable evidence to determine | `FAIL`, or `PASS` |
 
Every verdict carries a **machine-readable reason code** in addition to prose — because reports, filters, analytics and appeals need the code, and only humans need the prose.
 
**Specify the algebra explicitly:** how do child verdicts compose into a parent requirement? What does `PASS` + `UNKNOWN` compose to under a conjunctive requirement? Under a disjunctive one? Under "any 3 of 5 work orders"? Write the composition table. It is not obvious, and getting it wrong silently corrupts every downstream number.
 
### 4.2 · The three metrics — orthogonal by construction
 
| Metric | Question it answers | Never conflated with |
|---|---|---|
| **Compliance Score** | Of the requirements we could determine, how many are satisfied — weighted by mandatory vs desirable? | How sure we are |
| **Evidence Confidence** | How reliable is the evidence underlying those determinations — extraction quality, source authority tier, corroboration count, recency? | Whether they passed |
| **Verification Coverage** | What fraction of requirements were checked against an authoritative source at all, versus resting on self-declaration? | Either of the above |
 
A bid can be **100% compliant, at 40% coverage, with 60% confidence** — and that combination is a *materially different procurement risk* from 100/95/95. The interface must make that difference impossible to miss. Never average them. Never blend them into a badge.
 
### 4.3 · Risk classification
 
Risk is a **deterministic function of the three metrics plus conflict signals** (identifier mismatches, entity ambiguity, expired validity, temporal gaps, self-declaration in mandatory positions). Define the function explicitly and version it exactly like a rule pack. Risk is never a model's opinion.
 
---
 
## 5 · The AI / deterministic boundary
 
State this boundary explicitly in the architecture output, module by module. It is the single most important thing a judge, an auditor, or a sponsoring ministry will interrogate.
 
| **LLM / VLM may** | **Deterministic code must** |
|---|---|
| Read and understand document layout | Compute arithmetic — turnover, ratios, aggregations |
| Classify document type | Compare dates and evaluate validity windows |
| Extract candidate field values with location | Evaluate thresholds and eligibility bounds |
| Decompose tender prose into atomic requirements | Check mandatory-document presence |
| Propose normalisations for messy input | Enforce format grammars and reject malformed values |
| Propose entity linkage with reasoning | Confirm linkage via identifier matching |
| Classify requirement semantics and category | Evaluate rule packs and emit verdicts |
| Detect ambiguity and flag it for human review | Compute all three metrics |
| Narrate a finished decision in officer-readable prose | Classify risk |
| Draft corrective-action language | Determine which corrective actions apply |
 
**The tell-tale test:** if you removed every model from this system, it must still produce *correct verdicts on already-extracted evidence*. The models make the system usable at scale. They do not make it correct. If removing them changes a verdict, the boundary has leaked.
 
---
 
## 6 · Domain scope
 
**Supported document types at v1** — GST certificate · PAN · CIN / company registration · Udyam / MSME · ITR · audited financial statement · work order · experience certificate · OEM authorisation · EPFO documents · ESIC documents · ISO / certification documents · bank certificate · self-declaration.
 
**Classify each by evidentiary tier**, and make the tier visible in the UI, because it directly drives Evidence Confidence:
 
- **Tier A — Authority-verifiable.** Independently confirmable against a government source. Highest confidence.
- **Tier B — Issuer-attested.** Issued by an identifiable third party (bank, OEM, auditor, certification body) but not independently queryable at v1. Medium confidence, and the reason is recorded.
- **Tier C — Self-declared.** Asserted by the bidder alone. **A mandatory requirement resting solely on Tier C evidence can never reach `PASS`** — its ceiling is `PARTIAL`, and it must be surfaced as a rejection risk. This single rule is the sharpest anti-fraud property in the system. State it prominently.
---
 
## 7 · Verification adapter architecture
 
**The core abstraction:** every authoritative source sits behind a uniform adapter interface. The rule engine knows only the interface. Swapping API Setu for a direct departmental API, or adding a new authority, must require **zero changes** to the rule engine, the projections, or the UI.
 
Each adapter declares:
 
- **Capability manifest** — which fields it can verify, at what authority tier, with what freshness guarantee, and whether it supports historical/as-of queries.
- **Typed request/response contracts**, validated at the boundary in both directions.
- **A raw-response archive**, stored verbatim and immutably alongside the parsed form. When a response is later disputed, the parsed interpretation is not evidence — the raw payload is.
- **Explicit failure taxonomy** — `UNAVAILABLE` · `RATE_LIMITED` · `NOT_FOUND` · `AMBIGUOUS` · `MALFORMED` · `UNAUTHORIZED`. Every one maps to a defined verdict consequence, and **none of them map to `PASS`**.
- **Freshness and staleness policy** — how long a verification remains citable before it must be re-run, and what the interface shows when it is stale.
- **Consent and lawful-basis metadata** — under what authorisation this query was made, recorded on the event.
**Temporal verification:** where an authority supports as-of queries, model that capability explicitly. "Was this GST registration active on the tender's bid-submission date?" is a fundamentally different and more correct question than "is it active today," and answering it correctly is a genuine differentiator. Where as-of is unsupported, the system says so — it does not silently substitute today's answer for a historical one.
 
**No adapter is a mock.** A missing integration is an adapter with an empty capability manifest that honestly returns `UNAVAILABLE`. That state must render beautifully and informatively in the UI, because at v1 it will be common — and handling it with visible integrity is more impressive than faking coverage.
 
---
 
## 8 · Locked technology stack
 
Nothing outside this list without written justification.
 
**Frontend** — Next.js · TypeScript · Tailwind CSS
**Backend** — Python · FastAPI · Pydantic · SQLAlchemy
**Database** — PostgreSQL (pgvector-ready)
**Storage** — object-storage abstraction, single interface, no vendor leakage into domain code
**AI** — provider-agnostic LLM/VLM abstraction; no provider SDK imported outside the adapter
**Verification** — API Setu and authorised government APIs, behind the adapter interface of §7
 
No message broker, no orchestration framework, no graph database, no vector database, no workflow engine, no additional cache, no agent framework — until an approved artefact demonstrates that PostgreSQL and FastAPI cannot carry the requirement. **PostgreSQL is your event store, your projection store, your queue, and your vector index at this stage.** Adding infrastructure is the most common way a strong architecture becomes an unshippable one.
 
---
 
## 9 · Required output artefacts
 
Produce all of the following. Diagrams as Mermaid. Contracts as concrete typed schemas, not prose descriptions.
 
**A · High-level architecture** — system context, trust boundaries, external dependencies, and where the append-only core sits relative to everything else.
 
**B · Component architecture** — every module of §11 as a component with declared responsibility, inputs, outputs, and — explicitly — its AI/deterministic classification.
 
**C · Data flow** — tender ingestion → requirement decomposition → bidder ingestion → extraction → normalisation → entity resolution → verification → fusion → decision → scoring → reporting. Annotate every arrow with the contract that crosses it.
 
**D · Data model** — the event schema first (this is the spine), then the projections derived from it, then the read models the API serves. State explicitly which tables are immutable-by-construction and which are rebuildable caches.
 
**E · API boundaries** — resource design, command/query separation, versioning strategy, and the contract-generation pipeline (Pydantic → OpenAPI → generated TS client; hand-written duplicate types are forbidden).
 
**F · AI vs deterministic responsibility matrix** — the §5 table, expanded per module, with the failure behaviour of every model-dependent path.
 
**G · Verification adapter architecture** — interface definition, capability manifest schema, failure taxonomy, raw-response archival, freshness policy, temporal query support.
 
**H · Evidence and provenance architecture** — the causation chain from rendered pixel back to source page and authority response. Include the exact query path that answers "why does this say PASS."
 
**I · Security architecture** — authentication, role model (officer / reviewer / auditor / admin), tenant and tender-level isolation, document encryption at rest, PII handling and minimisation, credential custody for authority APIs, and — separately — the threat model for *evidence tampering*, which is the threat unique to this product.
 
**J · Audit architecture** — hash chaining, actor attribution, override recording, retention policy, export format for external audit, and the procedure by which a third party independently verifies the integrity of the log without trusting the application.
 
**K · Development dependency graph** — what genuinely blocks what, as a DAG, with the critical path marked.
 
**L · Implementation order** — sequenced phases, each with an explicit exit criterion and a demonstrable capability.
 
**Additionally, answer directly:**
 
1. **What must be built first?** Justify from the dependency graph, not from what is easiest.
2. **What can be postponed without weakening the demonstration?** Be specific and be ruthless.
3. **What must never be handled solely by an LLM?** Enumerate exhaustively, with the failure mode of each.
4. **What must be stored for auditability?** Field by field, with retention duration and justification.
5. **Where is this architecture most likely to fail in practice?** Name the top five risks honestly — extraction accuracy on poor scans, entity resolution ambiguity, authority API availability, rule-pack coverage of tender prose diversity, and whatever sixth thing you find. State the mitigation for each. **A design document with no stated weaknesses reads as a design document nobody stress-tested.**
---
 
## 10 · Explicitly rejected patterns
 
Do not produce a design containing any of these. They are the default habits this brief exists to override.
 
| Rejected | Required instead |
|---|---|
| CRUD-first tables with mutable status columns | Append-only event log + rebuildable projections |
| Compliance rules as `if` statements in service code | Versioned, content-addressed declarative rule packs |
| One large prompt that "analyses the document" | Narrow typed stages, each independently evaluated |
| LLM output written directly to a status field | LLM emits candidates; deterministic code decides |
| Confidence as a single blended trust score | Three orthogonal metrics, never averaged |
| Mock adapters, seeded fake API responses, demo fixtures posing as verification | Honest `UNAVAILABLE`, rendered with integrity |
| `audit_log` as a table someone remembers to write to | Audit as the substrate; no other way to change state |
| Boolean `is_compliant` | Four-state verdict algebra with composition rules |
| Building screens, then designing them | Tokens and evidence-native primitives first |
| Bootstrap-grade admin dashboard aesthetics | A deliberate institutional design language |
| Hand-mirrored TypeScript interfaces | Types generated from the Python contracts |
| "Tests later" | Golden-set evals gating every model stage; replay determinism in CI |
| Vendor SDK calls scattered through business logic | One adapter boundary, provider-agnostic core |
 
---
 
## 11 · Module map
 
Seventeen modules, mapped onto the pipeline of §2.2 — so that no module is an orphan and every one has a stage:
 
`Authentication` · `Tender Management` · `Tender Intelligence` · `Document Management` · `Document Intelligence` · `Verification Layer` · `Entity Resolution` · `Evidence Fusion` · `Compliance Rule Engine` · `Temporal Compliance` · `Compliance Scoring` · `Risk Engine` · `Bid Autopsy` · `Compliance Repair` · `Evidence Graph` · `Audit Trail` · `Reporting`
 
For each, declare in artefact **B**: stage position, AI/deterministic classification, upstream dependencies, emitted event types, and consumed projections.
 
Two of these deserve explicit definition because they are the product's distinguishing capabilities and are easy to under-specify:
 
- **Bid Autopsy** — a post-hoc, structured forensic account of *why a bid would fail*: the ranked set of blocking requirements, the specific evidentiary gap behind each, whether the gap is fatal or curable, and the counterfactual — *"had these three items been present, this bid would have moved from FAIL to PASS."* Deterministic. Derived from the event log, not regenerated by a model.
- **Compliance Repair** — the forward-looking inverse: a prioritised, actionable remediation plan. Not "obtain the required certificate," but *"GST registration shows SUSPENDED as of 04 Sep 2026; file pending GSTR-3B returns and obtain revocation before the 22 Sep bid deadline; this unblocks requirements 4.2, 4.3 and 7.1."* Deterministic in *what* is required; the LLM may draft only the phrasing.
---
 
## 12 · Definition of done for this pass
 
This response is complete when:
 
- [ ] All twelve artefacts **A–L** are delivered, with diagrams and concrete typed contracts
- [ ] The event schema is fully specified — it is the spine, and everything else depends on it
- [ ] The verdict composition table is written out, including every `UNKNOWN` interaction
- [ ] The three metrics have explicit, independently computable formulas
- [ ] Every module carries an AI/deterministic classification and a stated model-failure behaviour
- [ ] The adapter interface is defined precisely enough that a second engineer could implement a new authority against it with no further conversation
- [ ] The design token set and the seven evidence-native primitives are specified before any screen is described
- [ ] The five honest risks are named with mitigations
- [ ] **No application code has been written**
---
 
## 13 · Stop condition
 
Deliver the architecture. Then **stop and wait for explicit approval.**
 
Do not scaffold. Do not create files. Do not begin implementation. Do not propose additional technologies. If a requirement in this document is ambiguous or internally contradictory, **surface the ambiguity rather than resolving it silently** — a wrong assumption baked into the event schema is expensive to remove later, and the event schema is the one thing in this system that is genuinely hard to change after the fact.
 