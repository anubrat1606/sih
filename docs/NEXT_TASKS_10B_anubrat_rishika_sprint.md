# 2-day sprint (Anubrat, Rishika) — close DigiLocker, make the product demo-ready

Supersedes nothing — extends `NEXT_TASKS_10_anubrat_rishika.md`, which is
already half-shipped (PR #105: GST return filing + 5 self-declared types).
Both of us now have push access to both GitHub accounts. Two days, starting
now. Real Postgres, real Sandbox calls, real screenshots before either of
us calls anything done — same rules as every prior round, not relaxed for
the deadline. Speed comes from cutting scope, never from cutting testing.

data.gov.in checked and closed: no usable per-bidder verification API for
Udyam, EPFO/ESIC, or blacklist/debarment — only aggregate district-level
statistics. Does not change any existing gap.

---

## Day 1

### Anubrat — DigiLocker (PS26100 point 8), scoped tight

Real, not a stub: Sandbox.co.in's DigiLocker product exists on the same
account already backing PAN/GST/CIN/GST-returns, but it's a genuinely
different shape from those four — a consent flow, not a server-to-server
lookup. The bidder is redirected to DigiLocker, authenticates with their
own Aadhaar-linked OTP, and grants consent before any document comes back.
`adapters/base.py`'s `LawfulBasis.BIDDER_CONSENT` already exists for
exactly this.

Minimum real scope for two days, not the full SDK:
1. `POST /bidders/{bidder_id}/digilocker/session` — calls Sandbox's
   session-initiation endpoint, returns the DigiLocker consent URL to
   redirect the bidder to. Records a `VERIFICATION_REQUESTED`-shaped event
   with `basis=BIDDER_CONSENT` the moment the redirect is issued, not
   after — the request itself is the lawful-basis-relevant act.
2. `GET /bidders/{bidder_id}/digilocker/callback` — where DigiLocker
   redirects back. Exchanges whatever code/session id it returns for the
   actual document list, archives the raw exchange (`archive()`, same as
   every other adapter), records the consent artifact's reference on the
   event so it's citable later (charter §7's "consent and lawful-basis
   metadata" requirement, not a nice-to-have).
3. A `DIGILOCKER_DOCUMENT` capability manifest entry, `DOCUMENT_REQUIRED`
   type gets a real evidence path for the first time.

Do not build: multi-document-type parsing, every document Sandbox
supports, the SDK client-side integration. One document type end-to-end
(pick whichever extracts most easily) beats five half-wired ones.

### Rishika — landing page + screenshot readiness

Per `NEXT_TASKS_10`'s original brief: audit `LandingPage.jsx` against
`satyapramana.md` §2.3 (design tokens, both themes real, tabular-numeral
mono for every identifier/amount/date, the locked four-value status
palette). Then, concretely:
- Landing page earns the top of the funnel: what the product is, the
  four-state verdict promise, a real path into the live system.
- Screenshot-ready the Evidence Graph and Audit/Temporal-Scrubber views —
  real data on screen, nothing clipped, no placeholder text. These are
  the two screens going into the next PPT revision.

---

## Day 2

### Anubrat
- Wire the DigiLocker redirect into `SubmitDocumentsPage.jsx` (or hand
  Rishika the finished API contract if she's faster to it once day 1's
  backend is real and documented).
- Run real bidder data through the *entire* pipeline end to end on the
  live deployment, including the new GST_RETURN_STATUS and DigiLocker
  paths — this is what actually produces the screenshots that matter.
- Deploy, live-verify, merge.

### Rishika
- Apply the same design-token consistency pass across the officer-facing
  pages the audit flagged.
- Produce the two screenshots (Evidence Graph, Audit trail) from the real
  end-to-end run Anubrat produces above — screenshots must come from a
  real run, not a mid-build state.

---

## Definition of done, both days

Same as every round: real Postgres tests passing, a real live-browser
verification before merge (not just `npm run build` succeeding), and
nothing merged by its own author without either a real review or an
explicit admin-override decision made in the open, not silently.
