# STATUS — where the project is and what to do next

Last reviewed: 2026-09-10. Read `../CLAUDE.md` first for architecture and conventions.

## Architecture direction — added 2026-09-10

The team has a second, more ambitious spec (`satyapramana.md`, the architecture
charter). It is **not** compatible with the prompts file that built this repo:
it locks the stack to Next.js / FastAPI / PostgreSQL and forbids MongoDB and
graph databases.

Adopted position: **charter integrity, prototype infrastructure.** Take the
charter's evidentiary properties (four-state verdicts, evidence tiers, three
orthogonal metrics, rule packs as data, honest `UNAVAILABLE`); decline its
infrastructure cost (full event sourcing/CQRS, Next.js migration, 13 of the 17
modules). One migration only: the Node/Express + Mongo backend becomes
FastAPI + PostgreSQL, so the audit log is append-only at the database level.

Collusion detection stays in scope, as an 18th module: edges become events,
clusters become a PostgreSQL recursive-CTE projection instead of an in-memory
networkx graph, so a flag survives restart and can be audited.

New specs, both verified:

- `VERDICT_ALGEBRA.md` — four-state algebra, one composition function covering
  `ALL_OF` / `ANY_OF` / `K_OF_N`, the Tier A/B/C ceiling, reason codes, and the
  three metric formulas. Algebraic properties checked exhaustively.
- `RULE_PACKS.md` + `/schemas/rule_pack.schema.json` — declarative,
  content-addressed rule packs and the closed predicate language. Meta-schema is
  draft-07 valid; the worked example validates; 20 malformed variants rejected.
- `ADAPTERS.md` + `/schemas/capability_manifest.schema.json` +
  `/schemas/capability_registry.json` — the verification adapter interface,
  capability manifests, the failure taxonomy (no row maps to `PASS`), the raw
  response archive, lawful basis, freshness and temporal-query handling.
  Meta-schema draft-07 valid; all 6 registry adapters validate; 11 malformed
  variants rejected; the rule-pack operand grammar and the registry's evidence
  paths cross-check.

- `EVENTS.md` — the append-only hash-chained event log, the event catalogue,
  projections, the collusion recursive CTE, the "why does this say PASS"
  provenance query, and independent chain verification. **Every SQL statement in
  it was executed against PostgreSQL 14.20**, which surfaced three defects in the
  first draft: a row-level trigger does not fire on `TRUNCATE` (the log was
  wipeable), `char(64)` blank-pads the genesis sentinel (our own check passes
  while an independent verifier sees a broken chain), and `ORDER BY`/`LIMIT` is
  illegal in a recursive CTE anchor member (the provenance query was a syntax
  error). All three are fixed and re-verified: 0 chain forks across 8 concurrent
  writers, 200/200 events verified by an external script, tampering detected at
  the successor event.

The registry records the honest current state: four capabilities
(`PAN_STATUS`, `GST_STATUS`, `CIN_STATUS`, `UDYAM_STATUS`) sit at
`AWAITING_CREDENTIALS`, and EPFO/ESIC are registered null adapters with no
lawful programmatic source. Verification Coverage is therefore honestly 0%
until one aggregator account exists — still the highest-value errand outstanding.

**Two approvals still outstanding, both blocking implementation:**

1. **v2 schemas.** The four-state algebra replaces
   `PASS | FAIL | MISMATCH | UNVERIFIED`, and the three metrics replace
   `final_score.compliance_score`. `CLAUDE.md` freezes the five original
   schemas, so this needs an explicit yes. Nothing in `/schemas` has been
   modified; `rule_pack.schema.json` is purely additive.
2. **Charter section 8 amendment** — keep Vite, drop the Next.js requirement.
   Justification: no SSR, no file-based routing and no server components are
   needed; the charter's UI value is in design tokens and the seven evidence
   primitives, all framework-agnostic. Migrating costs days and gains nothing
   demonstrable.

The priorities below still stand and are unaffected by either approval.

---

## Verdict by component

| Component | State | Action |
|---|---|---|
| `services/collusion` | Complete, tested, honest | Ship as-is. Only touch it to add persistence (JSON dump on shutdown) if the demo needs restart-survival. |
| `services/extraction` | Real OCR works; returns `null` instead of guessing | Keep. Add EPFO regex once a real format is confirmed. Improve name/date extraction if time allows. |
| `backend` | Complete. Orchestrator + insert-only hash-chained audit log | Keep. Just needs a real MongoDB. |
| `frontend` | Builds clean; wired to the real API | Keep. Has never rendered a live backend response — do that. |
| `services/verification` | Portal URLs are unconfirmed guesses, CAPTCHA-walled, no public API; Udyam omitted; PAN needs a paid key | **The risk. Pick a data-source strategy before writing more.** |

The overall architecture and the schema-first contract are sound — do not
redesign. The "`UNVERIFIED` beats a fabricated `PASS`" stance is a genuine
strength; make it explicit in the pitch.

## Priorities, in order

### 1. Make verification real

The government portals (`services.gst.gov.in`, `epfindia.gov.in`) have no public
API and CAPTCHA-block programmatic access. Don't fight that.

- **PAN** — sign up for one KYC provider sandbox (Sandbox.co.in, Setu, or
  Signzy free tier). Put the real endpoint + key in
  `services/verification/.env`. Confirm the request/response shape against the
  provider's own docs, then fix `pan_live_kyc_check()` to match. The code path
  already exists.
- **GST** — use a GSTIN-verification aggregator (Sandbox / Masters India /
  RapidAPI), not the raw portal. Rewrite `gst_public_portal_check()` against it.
- **Udyam and EPFO** — formally cut from demo scope unless an aggregator turns
  up. The code already reports them as `UNVERIFIED`, which is defensible.

### 2. Stand up the whole stack once, locally

Nobody has done this. MongoDB + all five services + `scripts/e2e_test.js` with
real consented bidder data (two bidders genuinely sharing a phone or address for
the collusion case). This will surface the real integration bugs.

### 3. Collect demo data

Real people/businesses who have consented to appear in the demo, into
`data/consented_bidders/` (gitignored). See `data/README.md`. Need at least
three bidders on one tender, two of them sharing an attribute.

### 4. Extraction polish (only after 1–3)

- EPFO establishment-code regex, once a real format is confirmed — or drop EPFO.
- Populate `date_of_issue` / `date_of_expiry` so the expiry check in
  verification actually has something to test.

## Known code issues

- **Collusion registration is all-or-nothing.** `backend`
  `/bidders/:bidderId/verify` only POSTs to the collusion service when
  `director_name`, `address`, `phone`, and `bank_account` are *all* in the
  request body. Loosen it to register with whatever subset is present, or
  collusion detection silently won't run in real use.
- **EPFO check is decorative.** `epfo_public_portal_check()` returns
  `UNVERIFIED` even on a successful HTTP response ("parsing not implemented").
  Either wire a real source or remove the branch so it's not misleading.

## Explicitly deferred / out of scope

- Neo4j for the collusion graph — networkx is sufficient; correct call.
- Real S3 upload — local path in `source_s3_key` is fine for the demo.
- Auth — not in scope for the prototype.
- Udyam verification — no confirmed public verify URL.
