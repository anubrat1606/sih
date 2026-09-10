# STATUS — where the project is and what to do next

Last reviewed: 2026-09-10. Read `../CLAUDE.md` first for architecture and conventions.

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
