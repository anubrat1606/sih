# Next tasks, round 6 — the bidder portal, and the officer's review-and-finalise desk

**Read this whole file before writing any code.** Paste only your own
section, plus "Where this round sits," "Two decisions this round takes,"
"Design language," "File ownership this round," and "Hard rules" into your
own fresh Claude Code session — it has no memory of any earlier
conversation, so everything it needs is written down here.

Read `STATUS.md` first (what's actually built and merged), then
`docs/SIMPLE_CHECKLIST.md` (the plain-language version of the same), then
`CONTRIBUTING.md` (file ownership and the branch/PR workflow — still in
force, extended below for this round's new folders).

## Where this round sits

Rounds 1–5 built the **procurement officer's** side end to end: a real
tender, a real adopted rule pack, real document extraction, real live
verification (GST/PAN/CIN via Sandbox.co.in), scoring, risk, collusion
signals, Bid Autopsy, Compliance Repair, the audit trail, and an officer
records a QUALIFY/DISQUALIFY decision. All of it is live at:

- Frontend: https://sih26100-frontend.onrender.com
- Backend: https://sih26100-orchestrator.onrender.com (interactive docs at `/docs`)
- Shared login: ask Anubrat for the bootstrap admin credentials. It's a
  **shared Neon database** — everything anyone does lands in the same
  place, and nothing is ever deleted (append-only log). Test carefully.

Round 6 adds the **other side of the same product**: the bidder. Today a
bidder is a record an officer creates and uploads documents for. This
round gives the bidder their own login and their own portal — discover the
tender, read what it requires, submit their own documents, see that they
were received, and later see the officer's final decision — and gives the
officer a proper **review desk**: one queue of every bidder that needs a
human decision (flagged risk, a shared-attribute signal, a failed or
undetermined mandatory requirement), and a single place to finalise it.

This is a **frontend round**, with one small, real backend prerequisite
(Anubrat's A1) that nothing else can honestly work without.

## Two decisions this round takes — read before disagreeing with the tasks

Both were made deliberately, both are reversible later, and neither is a
task in this round. Don't quietly build around them.

**1. No auction / price-bidding screens.** This system has no concept of
a bid amount, a bidding window, a bidding clock, or "the highest/lowest
bid" — not in the event log, not in the schema, not in the architecture
charter (`satyapramana.md`). It is a *compliance* platform: the "bid" is a
bidder's documents against a tender's requirements, and the outcome is a
human officer's QUALIFY/DISQUALIFY decision. Building a live-auction UI
against no backend would mean either fabricating what it shows or
shipping screens that can never do anything — both out. If the team later
decides to add price bidding, that's a backend design round first
(events, a bid ledger, rules), then a UI. Not this round.

**2. Bidder accounts are provisioned, not self-registered.** The existing
model — no self-signup, every account created by an admin with an explicit
role (`STATUS.md`, "Auth") — extends to bidders unchanged: an officer or
admin creates a `BIDDER` account and links it to an existing bidder
record. No public sign-up page, no email OTP, no mobile OTP, no "Continue
with Google" this round: each of those needs infrastructure this project
doesn't have (an email/SMS provider, an OAuth app registration), and a UI
for them that isn't wired to a real backend would have to fake "sent" and
"verified" states — which is exactly what this project refuses to do.
The profile page shows these honestly as *not available on this
deployment*, never as a green tick.

## The bidder lifecycle this round must represent accurately

```
tender published (officer)             POST /tenders, rule pack adopted
        ↓
bidder discovers it                    bidder portal: Tenders
        ↓
bidder reads what it requires          bidder portal: Tender detail → Eligibility
        ↓
bidder submits documents               bidder portal: Documents (own bidder only)
        ↓
system extracts + verifies             existing pipeline, unchanged
        ↓
officer reviews flagged bidders        officer portal: Review desk   ← new
        ↓
officer finalises the decision         existing POST /bidders/{id}/decision
        ↓
bidder sees the final decision         bidder portal: My results
```

Two things the bidder UI must never imply: that submitting documents is
itself a result, and that any automatic score decides anything. Only the
officer's recorded decision is a result, and the bidder sees nothing
evaluative until that decision exists.

## Design language — "looks like GeM," not "looks like a startup"

Reference gem.gov.in directly for structure. Do **not** copy the GeM logo,
the national emblem, or GeM's branding — the reference is the *shape* of a
Government of India procurement portal, not its identity.

**Reuse `frontend/src/design/tokens.css` as-is. Nobody adds a colour.**
The palette already there is the whole palette: navy brand
(`--color-brand`), one action blue (`--color-accent`), white surfaces on a
cool-gray ground, gray borders, dark text, and the four restrained status
colours (pass / fail / partial / unknown). If you think a screen needs a
fifth colour, it doesn't — use hierarchy, spacing, or a border instead.

What the bidder portal should look like, concretely:

- **A thin top strip, then a navy header bar** with the portal name on the
  left and the signed-in bidder's organisation + sign-out on the right —
  the way GeM's header sits above everything. Bidder navigation lives in
  this header (or a plain left rail on wide screens); either way it is
  flat, text-first, and never more than the seven items listed under
  "Bidder navigation" below.
- **White content panels on the gray ground**, hairline borders,
  `--radius-sm`/`--radius-md` only. No shadows beyond what
  `design/components.css` already gives cards. No hero sections, no
  gradients, no illustrations, no glass, nothing animated except the
  existing toast and drawer.
- **Tables for lists, not card grids.** Tender discovery is a table
  (`ui/DataTable.jsx`), same as the officer side. Cards are for one thing's
  summary (a tender's key facts), never for browsing many things.
- **Every ID, date, deadline, hash, and reference in `--font-mono`** with
  tabular figures — tender IDs, bidder IDs, dates, document hashes.
- **Status = icon + colour + text, always**, via the existing badge
  primitives in `ui/primitives.jsx`. Never colour alone.
- **Dense but calm.** GeM screens are information-dense and mostly
  text. Match that density; earn every pixel of whitespace.
- **Breadcrumbs** on every bidder page below the header (Home ›
  Tenders › BHEL-T7J1Z68239). A plain footer with the two portal links
  and nothing else.
- Both themes stay first-class (`tokens.css` already carries dark);
  `prefers-reduced-motion` respected; `:focus-visible` on everything
  interactive; tables scroll inside their own frame on narrow screens.

The officer portal is **not** restyled this round. The review desk (A4)
is added to it using the exact primitives it already uses.

## Bidder navigation — exactly these, in this order

```
Dashboard · Tenders · My submissions · My results · Notifications · Profile · Help
```

No "My bids," no "Upcoming auctions," no "Documents" as a top-level item
(documents live under the tender a bidder is submitting to). Seven items.

## What the bidder may and may not see — the policy A1 enforces server-side

This is enforced by the backend endpoints Anubrat builds in A1, not by
hiding buttons. The frontend relies on it; it doesn't substitute for it.

| Bidder sees                                                        | Bidder never sees                                       |
|--------------------------------------------------------------------|---------------------------------------------------------|
| Tenders (id, title, authority, department, category, issue date, deadline, whether requirements are published) | Other bidders — existence, identity, documents, anything |
| The adopted rule pack's **requirements** (id, quoted text, obligation, source page, plain-language evidence expected) | The rule pack's constants, weights, freshness windows, or internal review notes |
| Their own uploaded documents, with the extraction result the upload returns (fields found, page, rejected, unreadable pages) | Verification outcomes, evidence tiers, coverage/confidence metrics |
| "Documents received" / "Under evaluation" / the officer's **final decision** once recorded, with the officer's note if one was written | Risk level, risk triggers, collusion clusters, Bid Autopsy, anything from `/audit` |
| After a decision: per-requirement outcome (PASS/FAIL/PARTIAL/UNKNOWN) and the Compliance Repair actions for curable gaps | Verdict reasons beyond the repair action, override justifications, officer identity |

If a screen in your section needs something from the right-hand column,
stop — that's a policy change, not a UI decision; raise it with Anubrat.

## Merge approval — unchanged

**Nobody merges their own work, ever, under any circumstance.** Open your
PR against `main`, make sure CI is green, and stop. Anubrat reviews and
merges every PR — including his own, per the standing rule. A green CI run
is a necessary condition for review, not a substitute for it.

## File ownership this round

`CONTRIBUTING.md`'s table is still authoritative for everything it
already lists. This round adds new folders so four people can work
without touching each other's files. **New files only, in your own paths,
unless a row below says otherwise.**

| Path | Owner | Note |
|---|---|---|
| `services/orchestrator/**` (BIDDER role, bidder-scoped endpoints, tests) | **Anubrat** | Already his under `CONTRIBUTING.md` |
| `frontend/src/App.jsx`, `auth.jsx`, `authContext.js`, `api.js`, `shell/**`, `pages/**` (all existing officer pages), `design/**` | **Anubrat** | Already his — existing frontend files. Nobody else edits these. |
| `frontend/src/bidder/bidderApi.js` | **Anubrat** | The bidder service layer. Written **first** (A2) so everyone builds against declared shapes. Others import it, never edit it. |
| `frontend/src/bidder/shell/**` | **Anubrat** | Bidder header, footer, breadcrumbs, layout |
| `frontend/src/officer/review/**` | **Anubrat** | The review desk |
| `frontend/src/bidder/pages/DashboardPage.jsx`, `TendersPage.jsx`, `TenderDetailPage.jsx`, `ResultsPage.jsx` | **Rishika** | Discovery + results |
| `frontend/src/bidder/pages/SubmissionsPage.jsx`, `SubmitDocumentsPage.jsx`, `ProfilePage.jsx` | **Suhani** | Submission flow + profile |
| `frontend/src/lib/validation.js` (new) | **Suhani** | Client-side structural pre-checks |
| `frontend/src/bidder/notifications/**`, `frontend/src/bidder/pages/NotificationsPage.jsx`, `HelpPage.jsx` | **Kevin** | Notifications + help |
| `frontend/src/bidder/responsive.css` (new) | **Kevin** | Mobile/tablet rules for bidder pages only |
| `frontend/src/bidder/bidder.css` (new) | **Anubrat** | Shared bidder-portal styles. If you need a rule, ask; don't add a second stylesheet. |
| `docs/*.md` | Shared | Append to your own section only |

Nothing this round touches `services/core/`, `schemas/`, the officer
pages' behaviour, or `extract/` (Suhani's, but not needed here).

## Hard rules — same five as always

1. No mock, sample, or simulated data anywhere, including anything that
   doubles as a demo. A screen with nothing real to show renders its
   empty state, not an example row.
2. No model ever makes a final determination. Only the officer's recorded
   decision is a result.
3. Nothing changes state except by appending an event.
4. Every change ships with a test where a test runner exists (backend);
   the frontend ships with `npm run build` and `npm run lint` clean and
   the manual checklist in your section walked through on the live app.
5. Secrets live in `.env` / Render env vars, never in a commit.

Three more, specific to this round:

6. **No fake "sent," "verified," or "notified" state, ever.** If the
   backend can't confirm it, the UI says it isn't available — it never
   shows the success state.
7. **The bidder-visible policy table above is enforced by A1's endpoints.
   Don't call an officer endpoint from a bidder page** — not even one the
   bidder "would be allowed" to see part of. If the data isn't in
   `bidderApi.js`, the bidder doesn't get it.
8. **No new colour, font, radius, or shadow.** `tokens.css` is closed.

---

## Anubrat — the prerequisite, the shell, the review desk, and the wiring

**Goal:** make a bidder a real, role-scoped user of the same system, and
give the officer one place to finalise every bidder that needs a human.
Everything else in this round depends on A1 and A2 landing first — do
those before anything else, and tell the other three the moment A2 is on
`main` so they can build against it.

### A1 — backend: the `BIDDER` role and what it may read (blocks everyone)

The whole round rests on this being real. Small, but every rule below
matters.

1. `auth/models.py`: add `Role.BIDDER`, ordered **below** `OFFICER`
   (`_ORDER`: BIDDER 0, OFFICER 1, SENIOR_OFFICER 2, ADMIN 3), so every
   existing `require_role(Role.OFFICER)` gate keeps excluding bidders
   with no other change. Mirror the order in `frontend/src/authContext.js`'s
   `ROLE_ORDER` (your file).
2. A bidder account links to a bidder record. Extend `users` with a
   nullable `bidder_id` (new migration `sql/008_bidder_accounts.sql`,
   additive, `ADD COLUMN IF NOT EXISTS`). `CreateUserIn` accepts
   `role: BIDDER` plus a required `bidder_id` for that role, refused for
   any other role. Account creation stays ADMIN-only (`POST /auth/users`),
   and *any* officer may create a BIDDER account — decide which and
   document it in the endpoint docstring (recommended: `OFFICER` or
   higher, since officers register bidders today).
3. `GET /auth/me` returns `bidder_id` when the role is BIDDER.
4. **Bidder-scoped read endpoints**, every one gated
   `require_role(Role.BIDDER)` *and* checking the path/query bidder
   matches the session's `bidder_id` (403 otherwise — a bidder can never
   read another bidder by guessing an id):
   - `GET /me/tenders` — tenders this bidder is registered on, each with
     the public tender fields and `requirements_published: bool` (an
     adopted pack exists). Also every tender with an adopted pack the
     bidder is *not* on yet, flagged `registered: false`, so discovery
     works. Reuse `list_tenders`/`proj_tenders`/`active_pack`; don't
     re-derive.
   - `GET /me/tenders/{tender_id}/requirements` — the adopted pack's
     requirements projected to the bidder-visible shape only (`id`,
     `text`, `obligation`, `source.page`, and a `evidence_expected`
     string derived from the predicate's field — e.g. "GST registration
     certificate" for `bidder.gst.*`). **Strip** `constants`,
     `freshness_days`, `review_note`, weights, everything else.
   - `GET /me/tenders/{tender_id}/submission` — this bidder's own
     documents on that tender (from `DOCUMENT_INGESTED` events for their
     bidder_id) with each upload's extraction summary, plus a `status`
     from exactly this vocabulary: `NOT_REGISTERED` · `REGISTERED` ·
     `DOCUMENTS_RECEIVED` · `UNDER_EVALUATION` · `DECIDED`. Derive it
     from events only (registered → any document → any verdict exists →
     a `DECISION_RECORDED` exists). Nothing evaluative before `DECIDED`.
   - `GET /me/tenders/{tender_id}/result` — `404`-style honest empty
     (`{"published": false}`) until a `DECISION_RECORDED` exists for this
     bidder; then `decision`, `decided_at`, the officer's `note` if any,
     the per-requirement effective verdicts, and the Compliance Repair
     actions for curable gaps (reuse `repair_plan`). **No** metrics, risk,
     collusion, autopsy, officer identity, or override justifications.
   - `POST /bidders/{bidder_id}/documents` — additionally callable by a
     `BIDDER` whose `bidder_id` matches; unchanged for officers. The
     response already returns the extraction summary the bidder page
     needs; don't add to it.
5. **Officer review-desk read**: `GET /review-queue` (OFFICER+). Every
   bidder across every tender, with `tender_id`, `bidder_id`, `status`
   (same vocabulary), `risk.level`, `collusion.flagged`, counts of
   FAIL/UNKNOWN verdicts on mandatory requirements, and
   `needs_decision: bool` (no `DECISION_RECORDED` yet). Build on
   `_list_tender_bidders` + a single `rebuild_projections` — do **not**
   re-introduce the per-bidder rebuild `docs/PERFORMANCE_AUDIT.md`
   removed. This endpoint will be hit on every review-desk load.
6. Tests: `tests/test_bidder_portal.py` — a BIDDER can read their own
   submission and result; cannot read another bidder's (403); cannot call
   any officer endpoint (403 on `/dashboard`, `/review-queue`,
   `/bidders/{other}` etc.); the requirements endpoint never leaks
   `constants`; the result endpoint is empty before a decision and
   correct after. Run the full suite — the `Role` change must not move a
   single existing test.

**Done when:** the suite is green against real Postgres, `/docs` shows
the new endpoints, and you've exercised every one on the live deployment
with a real BIDDER account you created for the existing real bidder
`GSTIN-TEST-1` on `GST-VERIFY-TEST`.

### A2 — `frontend/src/bidder/bidderApi.js` and role routing (blocks everyone)

1. `bidderApi.js`: one exported function per A1 endpoint, same style as
   `api.js` (which it imports `call` from — don't duplicate the fetch
   wrapper). **Declare the response shape of each in a JSDoc block above
   it** — this is the contract Rishika, Suhani, and Kevin build against
   while A1 is still landing. Anything not real yet (see K1) is exported
   as a function that returns `{ available: false, reason }` and is
   clearly commented as a backend dependency — never a fake success.
2. `auth.jsx`: add `RequireRole({ role, children })` alongside
   `RequireAuth`; a bidder hitting an officer route is redirected to
   `/portal`, an officer hitting a bidder route to `/dashboard`.
3. `App.jsx`: mount the bidder portal under `/portal/*` inside the bidder
   shell; after login, route by role (`BIDDER → /portal`, everything
   else → `/dashboard` as today). `LoginPage.jsx`'s redirect is yours.
4. `authContext.js`: `ROLE_ORDER` mirrors A1 exactly — BIDDER 0,
   OFFICER 1, SENIOR_OFFICER 2, ADMIN 3. Re-check every `roleAtLeast`
   call site and confirm the officer pages still gate exactly as before.

**Done when:** it's on `main`, the three others have been told, and a
BIDDER login lands on an empty-but-real `/portal` shell.

### A3 — the bidder shell

`frontend/src/bidder/shell/BidderShell.jsx` (+ `bidder.css`): the
GeM-shaped header (thin strip → navy bar → nav), breadcrumbs slot,
content area, plain footer. Seven nav items, in the order listed above,
with `aria-current`. A skip link. Signed-in organisation name from
`GET /auth/me` (display_name) and sign-out. Mobile: nav collapses to a
single menu control; Kevin's `responsive.css` handles the pages, you
handle the shell.

### A4 — the officer review desk

`frontend/src/officer/review/ReviewQueuePage.jsx` at `/review`, added to
the officer nav (`shell/AppShell.jsx`, yours) between Bidders and
Documents:

1. One `DataTable` over `GET /review-queue`: tender, bidder, status,
   risk badge, "shared attribute" badge, mandatory FAIL/UNKNOWN counts,
   decision state. Default filter: `needs_decision`. Sort by risk then
   by mandatory failures. Search by tender or bidder id.
2. Row → the existing `BidderCompliancePage` (it already records
   decisions and overrides — **extend, don't duplicate**). Add to it a
   clearly separated **"Finalise"** panel (`officer/review/FinalisePanel.jsx`,
   rendered by the page — the page file is yours): what the bidder will
   see once you decide (call `GET /me/...`-equivalent preview using the
   officer's data, projected through the *same* bidder-visible filter, so
   the officer sees exactly what the bidder will), the decision control
   (QUALIFY / DISQUALIFY + note), and the existing `ConfirmDialog` before
   it fires. After a decision: the panel shows "Decided — visible to the
   bidder as of <timestamp>" and locks the control (a decision is an
   event; a second one is a new event, not an edit — say so).
3. Empty state when nothing needs a decision; error state with retry.

### A5 — bidder account provisioning

`pages/SettingsPage.jsx` (yours): the existing account form gains
`BIDDER` in `ROLES` with a `bidder_id` field that appears only for that
role, populated from a select of existing bidder ids (from
`listTenderBidders` across `listTenders`, or a small new officer endpoint
if that's cleaner — your call, document it). The "What each role can do"
card gets a BIDDER row.

### A6 — integration, and the close-out

The established pattern: others build isolated files, you wire them into
routes and the shell in one integration commit at the end, then fold the
round into `STATUS.md` ("Built and merged") and update
`docs/SIMPLE_CHECKLIST.md`'s ✅ list. Same review discipline for every
PR: full diff, scope check against this file, build + lint, live check on
the deployment, then merge.

**Test / done when (whole lane):** backend suite green; frontend build +
lint clean; on the live app, a real BIDDER account for `GSTIN-TEST-1` can
log in, see `GST-VERIFY-TEST`, read its requirements, see their received
document, and see "Under evaluation" — then an officer finalises it from
the review desk and the bidder's My results shows the decision. Every
step against real data already in the shared database.

---

## Rishika — discovery and results (the bidder's reading screens)

**Goal:** a bidder can find a tender, understand exactly what it asks
for, and see the officer's final decision — cleanly, in tables and
sections, never in card grids.

**Depends on:** A2 on `main` (build against `bidderApi.js`'s declared
shapes from day one; every page must render its loading, empty, and error
states correctly *before* the real endpoints exist, so you're never
blocked waiting).

All four files are new, under `frontend/src/bidder/pages/`. Use only
`ui/primitives.jsx`, `ui/DataTable.jsx`, `lib/useApi.js`, and
`lib/audit.js`'s formatters. Import `bidderApi.js`; never `api.js`
directly.

### R1 — `DashboardPage.jsx` (`/portal`)

Answers, top to bottom, with real data only:

1. **Four `Stat` tiles**: tenders open to you (adopted pack, not yet
   registered), tenders you're on, submissions awaiting a decision,
   decisions received. All from `GET /me/tenders` + submission statuses —
   no fifth number.
2. **"Action needed"** — the only section that's allowed to be prominent:
   tenders you're on with status `REGISTERED` (no documents yet) and a
   deadline, nearest deadline first, each with a "Submit documents" link
   to Suhani's flow. Empty state: "Nothing needs your attention."
3. **"Closing soon"** — a plain table of tenders (registered or not) by
   `bid_submission_deadline`, with time remaining computed client-side
   from the real deadline and shown in mono. No deadline on file → shown
   as "—", never estimated.
4. **"Recent results"** — last three decisions, linking to R4.

### R2 — `TendersPage.jsx` (`/portal/tenders`)

A `DataTable`: Tender ID (mono, link) · Title · Organisation · Department
· Category · Issued · Deadline · Requirements (published / not yet) ·
Your status · Action ("View"). Search over id/title/organisation; filters
for organisation, category, and status; sort on every column; client-side
pagination at 25 (the list is small today — note in a comment that
server-side paging is the first thing to add if `/me/tenders` ever grows
past a few hundred). **Columns the backend doesn't have — location,
estimated value, bid type — are not shown**, not shown as "—". Don't
invent them.

### R3 — `TenderDetailPage.jsx` (`/portal/tenders/:tenderId`)

`PageHeader` with the title, mono tender id, organisation. Then `Tabs`:

- **Overview** — the tender's real fields as `Field`s; the deadline in
  mono with time remaining; a single "Your status" badge.
- **Eligibility** — the requirements from
  `GET /me/tenders/{id}/requirements`, as a table: requirement id (mono)
  · quoted text · Mandatory/Desirable tag · "Evidence expected" · source
  page. A one-line note above it: "These are the requirements the
  procuring officer adopted for this tender. Verification is performed
  by the procurement office; this list is what you'll be assessed
  against." Empty state if no pack is adopted yet: "Requirements have not
  been published for this tender."
- **Documents** — the tender's own uploaded notice, if any (from the
  tender record), with a view link to the existing `/documents/{sha}`
  endpoint. Not the bidder's own documents — those are Suhani's screen.
- **Important dates** — issue date and deadline in chronological order,
  as a simple vertical list with mono dates. Two dates today; the
  component should take a list so more can be added without redesign.

Actions in the header: "Submit documents" (→ Suhani's
`SubmitDocumentsPage` for this tender; disabled with a hint if not
registered) and "View my submission". No "Set reminder" — there is no
reminder backend (see K1).

### R4 — `ResultsPage.jsx` (`/portal/results`)

One row per tender the bidder is on, status from the vocabulary in A1.
`DECIDED` rows expand (or link to `/portal/results/:tenderId`) to the
decision: a single, plain sentence —

- QUALIFY: "Your submission for <tender> was assessed as compliant by the
  procurement office on <date>."
- DISQUALIFY: "The procurement office recorded a final decision on your
  submission for <tender> on <date>."

— the officer's note if present, then a table of per-requirement outcomes
(`VerdictBadge`), and, for curable gaps, the repair action text under
"What would resolve this". **Never** the words "awarded," "won," "L1," or
anything implying a contract — this system records compliance decisions,
not awards. Before a decision, the row simply shows its status badge and
"The procurement office has not yet recorded a decision."

**Test:** `npm run build && npm run lint` clean; every page's loading /
empty / error / retry state seen on the live app; R3's Eligibility tab
verified on `BHEL-T7J1Z68239` (real adopted pack) and its empty state on
a tender with no pack.

**Done when:** the four pages are on `main`, unwired (Anubrat wires
routes in A6), each rendering real data from the live deployment for
`GSTIN-TEST-1`.

---

## Suhani — the submission flow and the profile (the bidder's doing screens)

**Goal:** a bidder submits their own documents to a tender through a
short, calm, step-based flow, sees exactly what was read from them, and
is never told anything was verified when it wasn't.

**Depends on:** A2 on `main` (same as Rishika — build the states first).
You own `extract/`, so you already know the exact shape
`POST /bidders/{id}/documents` returns (`extracted[]` with path/value/
page/region, `rejected[]`, `unreadable_pages[]`,
`identifier_cross_check`) — that response *is* this screen's data.

### S1 — `frontend/src/lib/validation.js` (new)

Client-side **structural pre-checks only**, mirroring
`extract/grammars.py` exactly: GSTIN grammar + check digit + embedded-PAN
consistency, PAN grammar + holder-type letter, CIN grammar + RoC state
code + year range. Pure functions, each returning `{ ok, detail }`, unit-
testable by reading. Used by S3's profile form to catch a mistyped GSTIN
*before* it's saved. The file's top comment states what the round-4
`validation.js` (deleted in the redesign) already said and this one must
say again: **a structural check is not verification** — it says "this
could be a GSTIN," never "this GSTIN is valid."

### S2 — `SubmissionsPage.jsx` (`/portal/submissions`) and `SubmitDocumentsPage.jsx` (`/portal/tenders/:tenderId/submit`)

`SubmissionsPage`: one row per tender the bidder is on — status badge,
documents received (count), last upload (mono timestamp), "Continue" /
"View". Empty state: "You haven't been registered on a tender yet. Ask
the procuring office." (Registration is still officer-side this round.)

`SubmitDocumentsPage`: **three steps, one screen, no wizard chrome** —
a numbered left column, the current step's content on the right, back/
next as plain buttons:

1. **Review the requirements** — the same requirements list R3 shows
   (call the same `bidderApi` function; don't re-implement the table —
   if you both need the same component, ask Anubrat to lift it into
   `bidder/shell/` rather than importing across owners), plus a
   four-item "Before you submit" checklist the bidder must tick:
   requirements reviewed · documents ready · tender terms read ·
   details checked. The checklist is a UI gate only and says so.
2. **Upload documents** — one upload control, one declared type per file
   (the same `declared_type` values the officer page uses), progress per
   file, and **the real extraction result rendered immediately** from the
   response: each field found (path → value, page), anything rejected
   and why, any unreadable page. This is the one place a bidder learns
   their PDF was a scan with no text layer — say it plainly, with the
   real reason string from the response. A cross-check failure
   (`identifier_cross_check`) is shown as a warning with its detail.
3. **Confirm** — a summary of what was received (document names, hashes
   in mono, fields found), then a single sentence and nothing else:
   "Your documents have been received by the procurement office. This
   confirms receipt only; assessment is performed by the procuring
   officer and you'll see the outcome under My results." No "submitted
   successfully," no tick that could read as approval.

Errors from the upload (network, 4xx, an empty file) use `ErrorState`
with retry. Never assume a success the response didn't return.

### S3 — `ProfilePage.jsx` (`/portal/profile`)

Three sections, read from `GET /auth/me` and the bidder's registration
data in `bidderApi`:

- **Account** — display name, username, role (Tag), bidder id (mono).
- **Organisation** — the bidder record's fields as they exist today
  (`bidder_id`; director name / address / phone / bank account are
  officer-entered at registration and shown read-only here **only if A1
  exposes them** — otherwise this section shows what it has and no
  more). GSTIN/PAN/CIN as *extracted from their own documents* (from the
  submission endpoint), each with S1's structural badge — labelled
  "structure checked," never "verified".
- **Verification status** — three rows: Email · Mobile · Organisation.
  Each renders `UnavailableNote`: "Not available on this deployment."
  No toggle, no button, no tick. (This is the honest state; see decision
  2 above.)
- **Security** — "Change password" (not available on this deployment,
  same note — there's no endpoint) and Sign out. No "sign out of all
  sessions" — there's no session store to do it against.

**Test:** build + lint clean; the full S2 flow walked on the live app
with a real bidder account against `GST-VERIFY-TEST` using a real PDF —
the extraction result on screen must match the API response byte for
byte; S1 checked against the three real identifiers already in the
system (the CWC GSTIN `24AAACC1206D1ZM` and its embedded PAN).

**Done when:** the three pages + `validation.js` are on `main`, unwired,
each rendering real data for `GSTIN-TEST-1`.

---

## Kevin — notifications, help, and the small-screen pass

**Goal:** the bidder can see what's happened on their account, read a
plain-language guide, and use the portal on a phone — with every
"notification" being a real, backend-derived fact, and every missing
piece of notification infrastructure named, not faked.

**Depends on:** A2 on `main`.

### K1 — `bidder/notifications/` and `NotificationsPage.jsx` (`/portal/notifications`)

Notifications this round are **derived, not delivered**: a list computed
from what the bidder-scoped endpoints already return. Concretely, from
`GET /me/tenders` and each tender's `/submission` and `/result`:

- "Requirements published for <tender>" — an adopted pack exists.
- "Documents received for <tender>" — each `DOCUMENT_INGESTED` of theirs.
- "Deadline approaching for <tender>" — deadline within 7 days, computed
  client-side from the real deadline at render time.
- "Decision recorded for <tender>" — a result exists.

`bidder/notifications/deriveNotifications.js`: a pure function from
those responses to a sorted list `{ kind, tender_id, title, at, to }`.
`NotificationBell.jsx`: a header control (Anubrat mounts it in the shell)
showing the count of items newer than a `localStorage` "last seen"
timestamp — per-browser convenience only, wrapped in try/catch, never
treated as state. `NotificationsPage.jsx`: the list, grouped by day,
each row linking to the right bidder page. Empty state: "No
notifications."

**What this round does not do, stated in the page itself** (an
`UnavailableNote` at the bottom, not hidden): there is no backend
scheduler and no email/SMS provider, so there are **no scheduled
reminders and no emails**. Add to `bidderApi.js` (via Anubrat — it's his
file) one exported function `getScheduledNotifications()` that returns
`{ available: false, reason: "no notification scheduler on this deployment" }`,
and call it from the page so the dependency is a real, visible
integration point rather than a comment. A "Notification preferences"
card renders each preference (tender updates · deadline reminders ·
decision notifications) as read-only "Not available" rows. **No
switches that don't do anything.**

### K2 — `HelpPage.jsx` (`/portal/help`)

Static, plain-language, in the voice of `docs/SIMPLE_CHECKLIST.md`:
what this portal is, the lifecycle diagram from this file rendered as a
simple numbered list, what "documents received" does and doesn't mean,
what a decision means and who makes it, what to do if a document was
unreadable (the real reason: a scanned image with no text layer), and who
to contact (the procuring office named on the tender). No FAQ accordion,
no chat widget. One page, headings and paragraphs.

### K3 — `bidder/responsive.css`

Rules scoped under `.bidder-portal` (Anubrat's shell sets that class)
for ≤ 900px and ≤ 600px: `DataTable` rows collapse to stacked
label/value rows on the tender list and submissions list (keep tender
id, title, deadline, status, action visible first); the three-step
submit layout stacks; the notification bell stays visible in the header.
Nothing else — no new colours, no new components. Test at 400px width.

**Test:** build + lint clean; K1's derived list checked against the real
events for `GSTIN-TEST-1` on the live app (the count of "Documents
received" rows must equal that bidder's real upload count); K3 checked at
400px on the live app.

**Done when:** the files are on `main`, unwired, rendering real data.

---

## Sequencing — who's blocked on whom

```
A1 (backend) ──► A2 (bidderApi.js + routing) ──► R1–R4, S1–S3, K1–K3 in parallel
                                                   │
                                     A3, A4, A5 in parallel with those
                                                   │
                                                   └──► A6 integration + STATUS.md
```

Rishika, Suhani, and Kevin: **start the day A2 merges**, not before, and
start with your empty/loading/error states so nothing you build ever
depends on data that isn't there yet.

## After this round lands

Not tasks — the decisions the *next* round will need, written down now so
nobody improvises them:

- **Price bidding / auction**: still a backend design decision first.
  If the team wants it, the next brief starts with events (a bid ledger,
  a bidding window as tender metadata), not screens.
- **Bidder self-registration** with real email/mobile verification and
  Google sign-in: needs a provider and an OAuth registration; a real
  decision about who's allowed to register at all; and a spam/abuse
  story. Not a frontend task.
- **A distinct "result published" step** (an officer decides, then
  separately publishes) — a small new HUMAN event type
  (`RESULT_PUBLISHED`) if the team wants officer control over *when* a
  bidder learns the decision. This round treats "decided" as "visible."
- **Scheduled notifications and email** — a scheduler and a provider,
  then K1's `getScheduledNotifications()` becomes real with no UI change.

Whoever picks any of these up opens `NEXT_TASKS_7`, same format, same
reason it's worked every round.
