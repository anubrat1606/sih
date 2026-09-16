# Round 7 — Admin console expansion (Anubrat, Suhani, Rishika)

Kevin is off this round — just the three of us. Follow this file exactly,
same as round 6: stay inside your own files, nobody merges their own PR,
real data or `UNKNOWN`, never a guess.

## What's already done (this round, merged and live)

You don't need to redo or touch any of this — it's the foundation the
rest of the round builds on.

- **`GET /auth/users`, `POST /auth/users/{username}/disable|enable`**
  (backend, PR #88) — the account directory and the switch to disable an
  account. The `users` table already had a `disabled` column; this just
  exposes it.
- **The admin console itself** (frontend, PR #89) — a third portal at
  `/admin/*`, its own shell (`admin/shell/AdminShell.jsx`), gated to the
  literal `ADMIN` role the same way `/portal` is gated to `BIDDER`.
  - `/admin` (Overview) — live counts by role, the live capability
    registry, on-demand audit-chain verification.
  - `/admin/accounts` — directory, search/filter, create, disable/enable.
- **Landing page**: a real 3D tilt on the hero/verdict/step/principle
  cards and a genuinely 3D-spinning chakra (`Tilt3D.jsx`, PR #90).
- **PR #84 merged** (Suhani's demo rule pack) — verified independently
  against the live schema/registry, 0 violations. It's a clearly-labeled
  fictional worked example (`docs/RULE_PACKS.md` §8's own convention),
  not bidder data, so it's fine on its own merits.
- **PR #68 (Kevin's evaluation-readiness doc) — not merged.** It names
  PR #66 ("bidder portal + self-signup") as the single highest-priority
  merge. PR #66 was closed, never merged — it was the self-signup/OTP/
  Google-sign-in version the team explicitly rejected in round 6 in favor
  of officer-provisioned bidder accounts. The doc also predates the real
  bidder portal, which has been live for days. Don't build anything
  described in that PR; if it gets revived it needs a rewrite against
  what's actually on `main`, not a merge as-is.
- **The first fully real, non-fabricated bidder verification on this
  deployment**: a real e-PAN (its own layout — labels are in the card
  artwork, not the text layer — needed a small extraction fix, PR #87)
  and a real GST certificate, both verified live against their real
  issuing authorities. One genuine `AUTHORITY_CONFIRMED` PASS.

## The standing rule, unchanged

No mock, sample, or synthetic data anywhere — see `data/README.md`. Two
mock/fictional documents were sent this round and declined for the same
reason as every prior round: a rule pack template clearly labeled
fictional is fine (see PR #84 above); a document dressed up to look like
someone's real GST certificate or PAN card is not, structurally-valid
numbers or not. If a task below needs real data to demo (it doesn't —
everything here is either account/system data you already have, or reads
of data already on the live system), say so and it'll get scoped around
that, the same as always.

---

## Anubrat — done this round (see "What's already done" above)

If there's time left: `docs/STATUS.md` and `docs/EVALUATION_READINESS.md`
need a pass to reflect the real bidder portal, the admin console, and
that PR #66 is dead — `EVALUATION_READINESS.md` doesn't exist on `main`
yet (it only exists on the unmerged PR #68), so this would mean writing
the real version, not editing Kevin's.

---

## Suhani — admin-triggered password reset

**Problem this closes**: there's no self-service password reset (no
self-signup, on purpose — round 6), so today the *only* way anyone
recovers a forgotten password is someone editing the database directly.
That's a real gap for a system four people are about to demo from.

**Backend** — `services/orchestrator/satyapramana_store/`:
- `auth/passwords.py` already has `hash_password`; `auth/store.py` needs
  one new function, e.g. `set_password(conn, username, new_password) ->
  User | None` — same shape as `set_disabled` (PR #88, just merged) is a
  good template to follow.
- New endpoint, `POST /auth/users/{username}/reset-password`, ADMIN-only
  (`require_role(Role.ADMIN)`), same file/area as `disable_account` /
  `enable_account` in `app.py`. Generate a real random password server-side
  (don't accept one from the request — an admin resetting someone's
  password shouldn't get to choose what it becomes and see it typed in a
  browser twice); return it **once**, in the response body, never stored
  or logged in the clear. `secrets.token_urlsafe(12)` or similar from the
  stdlib is enough — no new dependency.
- Tests in `tests/test_auth.py` next to the disable/enable tests: reset
  changes the password (old one stops working, returned one works),
  ADMIN-only, unknown username 404s.

**Frontend** — `frontend/src/admin/`:
- `api.js` — `resetPassword(username)`.
- `AccountsPage.jsx` (already built) — add a "Reset password" button next
  to Disable/Enable. On success, show the one-time password in a
  dismissible callout/modal with copy-to-clipboard, and a clear "this
  won't be shown again" note — same honesty pattern the rest of the app
  uses for anything shown exactly once.

**File ownership**: `auth/store.py`, `app.py` (only the new endpoint —
don't touch anything else in it), `tests/test_auth.py` (additions only),
`admin/api.js` additions, `admin/pages/AccountsPage.jsx`. Ask before
touching anything else.

---

## Rishika — Admin console: Audit & System page

**Problem this closes**: right now the only place to see the full event
log or a detailed capability breakdown is `AuditTrailPage.jsx`
(`/audit`), which lives in the *officer* shell, not the admin console —
and there's no per-officer activity view anywhere.

New route: `/admin/audit`, new file `admin/pages/AuditPage.jsx`, added to
`AdminShell.jsx`'s `NAV` array and `App.jsx`'s `AdminRoutes`
(`<Route path="audit" element={<AuditPage />} />`) — small, additive
changes to both, same pattern PR #89 used to add Overview/Accounts.

No new backend needed — build entirely on `getAuditExport()` and
`getAuditVerify()` (already in `api.js`), the same two calls
`AuditTrailPage.jsx` already uses, so read that file first for the real
event shape (`lib/audit.js`'s `parseAuditExport`/`summarizeEvent`).

Three things on the page:
1. **Chain integrity** — the same "Verify now" pattern as the Overview
   page's audit card (reuse the idea, not a copy-paste — look at how
   `OverviewPage.jsx` does it), but with the full breaks table
   (`AuditTrailPage.jsx` already renders one) if the chain ever isn't
   intact.
2. **Capability registry, in detail** — reuse the shape from the public
   landing page's `AuthorityTable` (`landing/LandingPage.jsx`) but for
   the authenticated admin: every field `GET /capabilities` returns
   (`tier`, `channel`, `as_of_supported`, `detail`), not just status.
3. **Officer activity** — derive this yourself from `getAuditExport()`'s
   real event list: group by `actor_id` where `actor_kind === "HUMAN"`,
   show each officer's event count and their most recent `occurred_at`.
   This is a real computed view over real data, not a new capability —
   don't add a backend endpoint for it.

**File ownership**: `admin/pages/AuditPage.jsx` (new), one line each in
`admin/shell/AdminShell.jsx` (NAV array) and `App.jsx` (the one route).
Don't touch `AuditTrailPage.jsx`, `lib/audit.js`, or `api.js` — read from
them, don't edit them, unless something is actually missing, in which
case ask first.

---

## Ground rules (same as every round)

- Real Postgres tests for anything backend (`export DATABASE_URL=postgresql://localhost/satyapramana_test`).
- `npm run lint` and `npm run build` clean before opening a PR.
- Stay inside your file list. If you need something outside it, ask —
  don't improvise around it.
- Nobody merges their own PR.
