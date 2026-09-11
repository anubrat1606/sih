# Next tasks, round 4 — Suhani and Rishika, frontend interactivity

**Read this whole file before writing any code. Paste your own section — and
only your own section, plus the Hard Rules — into your own fresh Claude Code
session.** Your session has no memory of the conversation that produced this
document. Everything it needs to know is written down here.

Full context and the visual plan: https://claude.ai/code/artifact/9283803f-2c0c-483f-a0d7-7a95800f008f

Rounds 1–3 are done and merged, all clean, zero merge conflicts. Neither of
you has touched `frontend/` before now — it was Anubrat's sole lane through
round 3. That changes starting this round, but the file-overlap discipline
that made rounds 1–3 conflict-free stays identical: **every file you touch
this round is a brand-new file that does not exist yet.** Neither of you
edits an existing page, `App.jsx`, `App.css`, `api.js`, `components.jsx`, or
`tokens.css`. Anubrat imports your new components into the existing pages
himself in a later integration pass — the same "you build the isolated
piece, Anubrat wires it in" pattern every backend round has used, just
applied to frontend for the first time.

The product works end to end — 495 tests passing, three live government
verification integrations, a hash-chained audit log. What's missing is
polish and feedback: pages render data and stop, with no confirmation when
an action succeeds, no loading state between "nothing" and "the answer," a
tender list that's a bare `<ul>`, and an audit log that's a raw JSON dump.
Your job this round is building the reusable pieces that fix that — as new,
self-contained files only.

---

## Hard rules — apply to both of you, no exceptions

1. **Start from latest `main`.** `git checkout main && git pull origin main`,
   then `git checkout -b feat/<yourname>-<topic>`.

2. **Every file you touch is a new file.** If a task genuinely seems to need
   an edit to an existing page (`pages/*.jsx`), `App.jsx`, `App.css`,
   `api.js`, or `components.jsx` — stop and message Anubrat rather than
   editing it yourself. That integration step is intentionally reserved for
   one person so two people are never resolving a merge conflict in the same
   file.

3. **Use the existing design tokens, nothing hand-rolled.** Every colour,
   spacing value, radius, shadow, and duration comes from
   `frontend/src/tokens.css` by CSS custom property name (`var(--space-3)`,
   `var(--status-fail-fg)`, etc.) — never a new hex value, never a magic
   pixel number. Read `tokens.css` and `components.jsx` before you start so
   you know what already exists (badges, `Metric`, `CoverageMeter`,
   `EvidenceChip` and friends) — don't rebuild something that's already
   there.

4. **No mock or fabricated data, including in your own component's demo/test
   usage.** A component that needs example data to develop against uses
   data clearly labelled as a fixture — same rule the backend has followed
   all along, now applied to frontend fixtures too.

5. **Each new component is a real, working React component** — imported and
   rendered nowhere yet (that's Anubrat's integration step), but exportable
   and usable on its own. Write it the way you'd write it if you were about
   to hand it to someone else to wire in immediately, because you are.

6. **Definition of done, every task:**
   ```bash
   cd frontend
   npm run build   # must stay clean
   npm run lint    # must stay clean
   ```
   No backend test suite involvement this round — everything you're
   building is presentational, frontend-only.

7. **Push your branch, open a PR against `main`, do not merge it yourself.**
   CI (`.github/workflows/ci.yml`) runs the frontend build+lint job
   automatically.

8. **If anything is ambiguous, stop and ask** — especially "does this need
   an existing file touched," since that's the one thing that could create
   a conflict this round.

---

## SUHANI — feedback, loading, and validation

**Files you create:** `frontend/src/notifications/` (a new directory: at
least `ToastProvider.jsx`, `useToast.js`, `ToastHost.jsx`, and
`notifications.css`), `frontend/src/Skeleton.jsx` + `frontend/src/skeleton.css`,
`frontend/src/validation.js`, `frontend/src/FieldHint.jsx`,
`frontend/src/ConfirmDialog.jsx`, `frontend/src/EmptyState.jsx`. Nothing
else.

### S1 — Notification system (do this first, it's the biggest)

Right now every action in this app — register a bidder, upload a document,
run verification, evaluate, record a decision, override a verdict — either
silently updates the page or shows one red line via the existing `ErrorBox`.
Nothing ever confirms success. Build:

```jsx
// notifications/ToastProvider.jsx
export function ToastProvider({ children }) { /* holds toast state, renders children + <ToastHost/> */ }

// notifications/useToast.js
export function useToast() {
  // returns { notify } where notify(message, { kind: "success" | "error" | "info" }) queues a toast
}

// notifications/ToastHost.jsx
export function ToastHost() { /* renders the current queue, each toast auto-dismisses after ~4s */ }
```

Design notes:
- A toast is a small card, bottom-right or top-right (your call), using
  `var(--status-pass-bg)` / `var(--status-pass-fg)` for `success`,
  `var(--status-fail-bg)` / `var(--status-fail-fg)` for `error`, and neutral
  surface tokens for `info` — the exact same status-colour vocabulary the
  rest of the app already uses, not a new palette.
- Respect `prefers-reduced-motion` on the enter/exit animation (see how
  `tokens.css` zeroes `--duration-*` under that media query and follow the
  same pattern — don't hardcode a transition duration that ignores it).
- Multiple toasts stack, most recent on top or bottom (pick one, be
  consistent), each independently dismissible by click.
- Include a short demo/test page or story showing 3 toasts (success, error,
  info) stacked, so Anubrat can visually confirm it before wiring it in.

### S2 — Loading skeletons

Every page today either renders nothing or jumps straight from blank to
full once its `fetch` resolves. Build generic, reusable skeleton
placeholders:

```jsx
export function SkeletonLine({ width }) { /* one shimmering bar */ }
export function SkeletonCard() { /* a card-shaped placeholder, matches .card's dimensions in App.css */ }
export function SkeletonTable({ rows = 4, columns = 4 }) { /* a table-shaped placeholder, matches .evidence-table */ }
```

Use a subtle shimmer or pulse animation built from `tokens.css` durations —
again, must degrade to a static (non-animated) placeholder under
`prefers-reduced-motion`. Base the dimensions on the real components they'll
replace (`.card`, `.evidence-table`) so there's no layout shift when the
real content arrives.

### S3 — Inline form validation

`RegisterBidderPage.jsx` and the upload/verify flow currently give no
feedback until the server rejects something. Build pure, framework-free
validators:

```js
// validation.js
export function checkGstinFormat(value) {
  // returns { valid: boolean, hint: string } -- structural shape only
  // (2-digit state + 10-char PAN + entity code + Z + checksum char),
  // mirrors the shape services/orchestrator/.../extract/grammars.py
  // validates server-side, but this is a UX hint, not the real validator --
  // the server remains the source of truth, always.
}
export function checkPanFormat(value) { /* same idea, 10-char PAN shape */ }
```

And a component to show the hint inline:

```jsx
export function FieldHint({ result }) {
  // result is checkGstinFormat()'s return shape; renders nothing when
  // result is null/undefined (field not yet touched), a neutral hint while
  // typing, or a clear valid/invalid state once there's enough input to judge
}
```

### S4 — Confirmation dialog (phase 2)

A generic, reusable modal:

```jsx
export function ConfirmDialog({ open, title, body, confirmLabel, onConfirm, onCancel }) { ... }
```

Will be wired later to the Disqualify decision button and the officer
Override action — both currently fire immediately with no confirmation
step. Build it generic (not hardcoded to either use case); keyboard-
dismissible (Escape closes it), focus-trapped while open, and styled with
the `button.danger` treatment already in `App.css` for the confirm action
when it's destructive.

### S5 — Empty states (phase 2)

A single reusable component for "there's nothing here yet":

```jsx
export function EmptyState({ message, actionLabel, actionTo }) {
  // renders a message and an optional link/button to the action that
  // would create the first item -- e.g. "No tenders yet" + a link to /register
}
```

Will replace the plain `<p className="hint">` empty-state text scattered
across `TendersPage.jsx`, `TenderDashboardPage.jsx` (no bidders), and the
document list.

### PR shape

One PR for S1–S3 (phase 1), a second PR for S4–S5 (phase 2) once the first
is merged — don't block the second on review of the first if you can avoid
it, but keep them separate so each is reviewable on its own.

---

## RISHIKA — search, charts, audit, and reports

**Files you create:** `frontend/src/SearchFilterBar.jsx`,
`frontend/src/charts.jsx` + `frontend/src/charts.css`,
`frontend/src/AuditTimeline.jsx`, `frontend/src/ReportActions.jsx`. Nothing
else.

### R1 — Search + filter bar

A generic list-filtering control, not hardcoded to tenders or bidders:

```jsx
export function SearchFilterBar({ items, searchKeys, sortOptions, onChange }) {
  // items: array of plain objects
  // searchKeys: array of property names to substring-match against (e.g. ["bidder_id"])
  // sortOptions: array of { label, compare(a, b) }
  // onChange(filteredAndSortedItems): called whenever the query or sort changes
  // Renders its own search input + a sort <select>, calls onChange, renders nothing else --
  // the caller (Anubrat, wiring this into TendersPage/TenderDashboardPage later) owns the list itself.
}
```

Will replace `TendersPage.jsx`'s bare `<ul>` and add sort-by-risk to the
bidder card grid on `TenderDashboardPage.jsx`.

### R2 — Chart primitives

Pure SVG, no new dependency (this project explicitly avoids adding chart
libraries where a few dozen lines of SVG do the job — same reasoning that
kept the Evidence Graph hand-rolled instead of force-directed):

```jsx
export function RiskDistributionBar({ low, medium, high }) {
  // a horizontal stacked bar, segment widths proportional to counts,
  // coloured with --risk-low-fg/--risk-medium-fg/--risk-high-fg -- the
  // exact same three-value risk palette the rest of the app already uses
}
export function Sparkline({ values }) {
  // a small inline line/area chart, values is an array of numbers
}
export function StatTile({ label, value }) {
  // a single big-number tile: value in --font-mono/tabular-nums, label beneath in --text-xs
}
```

Follow the artifact-design chart guidance even though this isn't an
artifact: draw to the real scale (a `RiskDistributionBar` of 2 low / 0
medium / 3 high must show segments genuinely proportional to 2:0:3, not
evenly split), and every text label takes its colour from a token, never a
literal, so it reads in both themes.

Will be used in the new Mission Control dashboard (Anubrat's A7) and
possibly the tender report page.

### R3 — Audit timeline

`AuditPage.jsx` currently dumps the full JSON Lines export into a `<pre>`
block. Build a real visual renderer:

```jsx
export function AuditTimeline({ events, filterType }) {
  // events: array of { event_type, occurred_at, payload, seq, ... } --
  // the shape GET /audit/export's JSON Lines already is, one object per line
  // filterType: optional event_type to restrict the view to
  // Renders a vertical chronological list, most recent first or oldest
  // first (your call, be consistent) -- one row per event, an icon + colour
  // keyed by event_type (VERIFICATION_OBSERVED vs VERIFICATION_FAILED vs
  // REQUIREMENT_EVALUATED etc. should look visibly different), the
  // timestamp in --font-mono, and the seq number.
}
```

Reuse the same `PROVENANCE_SUMMARY`-style one-line-per-event-type idea
already in `components.jsx`'s `ProvenanceStep` for how to summarise a
payload without a raw JSON dump — don't invent a second convention for the
same problem, read that function first.

### R4 — Report actions (phase 2)

Two backend endpoints have been live since round 3 with no UI ever calling
them:

```
GET /tenders/{tender_id}/report/csv
GET /tenders/{tender_id}/blockers
```

Build:

```jsx
export function ReportActions({ tenderId }) {
  // a small action row: "Download CSV" (triggers a real browser download of
  // the CSV endpoint's response) and "Show blockers" (fetches and renders
  // the blocker-summary list inline -- reuse the existing .evidence-table
  // class, one row per requirement_id, blocked_bidder_count, classifications)
}
```

You'll need a `getTenderReportCsv(tenderId)` / `getTenderBlockers(tenderId)`
pair added to `api.js` — this is the one narrow, explicitly-allowed
exception to rule 2 above: **only add two new exported functions to the
bottom of `api.js`, following the exact pattern every other function there
already uses. Do not touch any existing line in that file.**

### R5 — Responsive pass (phase 3, sequenced last)

**Do not start this until Anubrat tells you Phase 3 integration (A8/A9) has
landed on `main`.** Once every other piece from this round is wired into
the real pages, audit every page at ~400px width and fix what breaks —
this genuinely does mean editing existing page CSS, which is exactly why
it's sequenced after everything else, so there's one stable version of each
page to fix instead of a moving target.

### PR shape

One PR for R1–R3 (phase 1), a second for R4 (phase 2). R5 is its own PR,
opened only after Anubrat confirms integration is merged.

---

## What happens after both PRs land

Anubrat (Phase 3, tasks A8/A9 in the roadmap artifact):
- Wires `ToastProvider`/`useToast` into every action handler across the app.
- Replaces blank initial-load states with the skeleton components.
- Wires `FieldHint` into the register/upload forms.
- Wires `ConfirmDialog` into Disqualify and Override.
- Replaces plain empty-state text with `EmptyState` everywhere a list can be
  zero-length.
- Wires `SearchFilterBar` into `TendersPage.jsx` and the bidder grid.
- Replaces the audit page's raw dump with `AuditTimeline`.
- Wires `ReportActions` into the tender dashboard.
- Uses the chart primitives in the new Mission Control dashboard (A7).

Neither of you touches an existing page this round. That's the whole point.
