# SATYAPRAMĀṆ — Problem, Approach, Architecture, Implementation

SIH26100 · Software Edition · Smart Automation
Sponsor: Ministry of Petroleum & Natural Gas — Chennai Petroleum
Corporation Limited (CPCL)

This is a narrative explainer, not a slide deck — read it top to bottom,
or use each section heading as a talking point in a live walkthrough.

---

## 1. The problem

Government tenders — on GeM (the Government e-Marketplace) and similar
platforms — routinely receive bids from hundreds of companies. Before a
single rupee is awarded, a procurement officer has to check every bid
against a long list of eligibility rules: valid tax registration (GST),
valid PAN, valid company registration, sometimes MSME/Udyam status,
minimum turnover, past experience, certifications, and more. And beyond
individual eligibility, the officer also has to watch for bidders who
look independent on paper but are secretly connected — the same director,
the same office address, the same phone number, the same bank account —
which is one of the most common ways collusive/cartel bidding hides in
plain sight.

Doing this by hand does not scale, and it creates a second, quieter
problem: **defensibility**. When a bid is rejected, the losing bidder can
and does challenge it. If the officer's only answer is "I checked it and
it failed," that is not a defensible record — there is no way to
reproduce, months later, exactly what was checked, against what document,
verified against which authority, under which version of the rules, at
what moment in time.

**The problem in one sentence:** procurement officers need to verify bid
compliance fast, at scale, *and* be able to prove — to a court, an
auditor, or a losing bidder — exactly how every single verdict was
reached, without re-running anything from memory.

## 2. The approach

Two design choices follow directly from that problem statement, and
almost everything else in this system is downstream of them.

**Choice 1 — never guess.** If the system cannot actually verify
something (no lawful online source exists, or a document wasn't
provided), it says so honestly — `UNKNOWN`, or "needs manual review" —
instead of quietly assuming a pass or a fail. A verdict is one of exactly
four states: `PASS`, `FAIL`, `PARTIAL`, or `UNKNOWN`. There is no boolean
"compliant: true/false" anywhere in this system, because a boolean cannot
represent "we don't know yet," and pretending otherwise is exactly the
kind of quiet dishonesty this project exists to remove.

**Choice 2 — every verdict must be reproducible, forever.** Nothing in
the system is ever updated in place or deleted. Every action — a document
uploaded, a field extracted from it, an authority queried, a rule
evaluated, an officer's decision — is recorded as a permanent, ordered,
cryptographically chained fact. The compliance status shown on screen is
never the "real" record — it's a live-computed summary *of* that record,
which means it can always be rebuilt from scratch and always agrees with
its own history. If a decision is challenged eighteen months later, the
system doesn't need anyone to remember anything; it replays the facts.

A third, smaller but equally deliberate choice: **AI proposes, a human
decides.** Two stages use an AI model — turning a tender PDF into
candidate requirements, and turning a finished verdict into
plain-language prose. Neither stage has any path to actually changing a
verdict or adopting a rule. The model's output is always a suggestion an
officer reviews, edits, or rejects — never a decision.

## 3. Architecture

**The core idea:** an append-only, hash-chained *event log* is the single
source of truth. Everything else — the dashboard, the scores, the
compliance status — is a read-only view computed from that log, the same
way a bank balance is a view computed from a ledger of transactions, not
a number that gets edited directly.

```
Tender PDF  ──┐
              │   deterministic extraction (no OCR, no model)
Bidder docs ──┼─► identifiers read + structurally validated
              │   (GSTIN / PAN / CIN / Udyam, with page + pixel region)
              ▼
      live verification against government-linked authorities
      (PAN / GST / CIN via Sandbox.co.in; UDYAM/EPFO/ESIC honestly
       UNAVAILABLE where no lawful online source exists)
              │
              ▼
   rule pack (officer-authored, versioned, schema-validated)
      evaluated deterministically against the evidence
              │
              ▼
   four-state verdict per requirement, three separate metrics
   (compliance score / evidence confidence / verification coverage —
    never blended into one number), risk classification, collusion check
              │
              ▼
   every one of the above steps is itself a permanent event ──► the
   append-only, hash-chained PostgreSQL event log (the real source
   of truth — the scores above are a projection folded from this)
```

**Two AI-assisted stages, both strictly bounded and both provider-agnostic
(currently Gemini):**
- *Tender Intelligence* reads a tender's real PDF text and proposes
  candidate requirements (with page references) for an officer to
  hand-review.
- *Explain* narrates an already-finished, already-correct dossier into
  officer-readable prose — it restates facts, it does not compute them.

Both degrade honestly to "unavailable" with no fabricated output if no
API key is configured — same rule as everything else.

**Two front doors on one backend:**
- The **officer portal** — the internal tool: create tenders, build rule
  packs, register/verify bidders, review evidence, decide, export
  reports.
- The **bidder portal** — public self-service: a company signs up with a
  real account, discovers tenders, registers, uploads its own documents,
  and watches its own compliance get checked live.

**Stack, and why:** FastAPI (Python) orchestrator, PostgreSQL as the
event store *and* the projection store (nothing else is bolted on for
that), a pure/framework-free domain layer for the verdict algebra and
rule evaluation, React (Vite) on the frontend. No Mongo, no graph
database, no Docker — every infrastructure choice was evaluated against
"does this buy real evidentiary or operational value for a hackathon
prototype," and declined where the honest answer was no.

## 4. Implementation plan (what got built, in the order it was built)

The system was built in rounds, each one shipped, tested against a real
PostgreSQL, and merged before the next began — not built once and
polished at the end.

1. **The domain core** — the four-state verdict algebra, the three
   orthogonal metrics, risk classification, the rule-pack predicate
   evaluator. Pure, deterministic, framework-free, fully unit-tested
   first, before any API existed to call it.
2. **The event log and document pipeline** — the append-only,
   hash-chained PostgreSQL log; deterministic (no-OCR) extraction of
   GSTIN/PAN/CIN/Udyam with exact page/region provenance for every
   extracted value.
3. **Live verification** — real integration with Sandbox.co.in for
   PAN/GST/CIN status, gated entirely by real credentials, with
   UDYAM/EPFO/ESIC confirmed as honest, permanent `UNAVAILABLE`s rather
   than left as vague TODOs.
4. **Rule packs and evaluation** — officer-authored, versioned,
   schema-validated rule packs; the DECIDE stage that folds evidence into
   a verdict deterministically, with zero code path that writes a verdict
   any other way.
5. **Reporting and explainability** — Bid Autopsy (why a bid would fail,
   with a real counterfactual), Compliance Repair (the specific fix for
   each curable gap), the Evidence Graph, the Compliance Dossier, CSV/PDF
   exports.
6. **Authentication and roles** — real officer accounts, hashed passwords,
   signed sessions, a three-tier role system, replacing an earlier
   deliberately-auth-free prototype phase once the project moved from "a
   panel demo" toward "a real officer-usable product."
7. **Tender Management + the admin tender builder** — structured tender
   metadata, tender-document upload, a requirement-type catalog computed
   live against what the system can actually check, a guided rule-pack
   builder with dry-run validation — replacing hand-written JSON with a
   form an officer can actually use.
8. **A real rule pack on a real tender** — a genuine public GeM/BHEL
   tender, decomposed and adopted for real, independently re-verified
   (hash-checked against the source PDF, not just trusted) before merge.
9. **Deployment** — a Render Blueprint running the backend and frontend
   as two services against a shared PostgreSQL (Neon), so the whole team
   and every evaluator use one live URL instead of a local setup each.
10. **The bidder-facing half of the product** — real self-service bidder
    accounts (signup, login, email verification, mobile OTP, password
    reset, Google Sign-In), and a full public bidder portal wired to the
    same real backend as the officer side — turning the system from "an
    internal tool judges are shown" into "a product a bidder can actually
    use themselves."

**What's deliberately not built, and why it's not a gap:** an
auto-rejection feature (the system never disqualifies anyone — it hands a
human officer a defensible dossier and the human decides), and automated
checks for turnover/experience/certifications/EPFO/ESIC (no lawful online
source exists for any of these today, so the honest, correct behavior is
"flag for manual review," not a fabricated automated check).

See `docs/STATUS.md` for the exact, currently-true technical state, and
`docs/EVALUATION_READINESS.md` for what's working right now versus what
the team is doing in the hours before the first evaluation.
