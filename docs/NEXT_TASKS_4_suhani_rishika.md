# Next tasks, round 4 — frontend interactivity, in full detail

**Read this whole file before writing any code. Paste your own sections —
and only your own sections, plus every "Hard rules" and "Groundwork"
section — into your own fresh Claude Code session.** Your session has no
memory of the conversation that produced this document. Everything it needs
to know is written down here, in enough detail that no follow-up question
about scope should be necessary.

Executive-level view of this same plan (module status, the UX gap audit,
the SIH demo script): https://claude.ai/code/artifact/9283803f-2c0c-483f-a0d7-7a95800f008f
That page groups this round into three broad phases; this document is the
ground-level expansion of the same work into nine — nothing in the two
disagrees, this one just doesn't skip anything.

## Where this round sits

Rounds 1–3 are done and merged, all clean, zero merge conflicts, 495 tests
passing (182 `services/core` + 313 `services/orchestrator`). Neither of you
has touched `frontend/` before now — it was Anubrat's sole lane through
round 3. That changes starting this round, but the file-ownership
discipline that made rounds 1–3 conflict-free stays identical in spirit:
**every file either of you touches this round is a brand-new file that does
not exist yet on `main`.** Anubrat imports your new components into the
existing pages himself, in a dedicated later phase — the same "you build
the isolated piece, Anubrat wires it in" pattern every backend round has
already used, just applied to frontend for the first time.

The product works end to end. What's missing is polish and feedback: pages
render data and stop, with no confirmation when an action succeeds, no
loading state between "nothing" and "the answer," a tender list that's a
bare `<ul>`, and an audit log that's a raw JSON dump. This round builds the
reusable pieces that fix that.

## Merge approval — read this before your first PR

**Neither of you merges anything, ever, under any circumstance.** Open your
PR against `main`, make sure CI is green, and then stop — Anubrat reviews
and merges every PR himself, the same way it's worked every round so far.
A green CI run is not approval; it's a necessary condition for review, not
a substitute for it. If a PR sits unreviewed for a while, say so — don't
merge it to unblock yourself. This applies to all nine phases, including
the ones that are "just" new, self-contained files with no conflict risk:
approval is about reviewing what you built, not about conflict risk.

---

## Phase map

| Phase | What | Owner(s) | Depends on |
|---|---|---|---|
| 1 | Groundwork & environment audit | Suhani, Rishika | nothing — do this first |
| 2 | Core interaction primitives | Suhani (S1, S2), Rishika (R1) | Phase 1 |
| 3 | Feedback, validation & confirmation | Suhani (S3, S4, S5) | Phase 1 |
| 4 | Data visualisation | Rishika (R2, R3) | Phase 1 |
| 5 | Backend-wired report actions | Rishika (R4) | Phase 1; touches `api.js` (the one narrow exception) |
| 6 | Anubrat's parallel heavy build | Anubrat (A1–A7) | nothing from Suhani/Rishika — runs concurrently with 2–5 |
| 7 | Integration | Anubrat (A8, A9) | Phases 2–6 all merged |
| 8 | Regression, accessibility & cross-theme QA | Anubrat (A10) | Phase 7 |
| 9 | Demo prep, responsive pass & rehearsal | Anubrat (A11), Rishika (R5) | Phase 8 |

Phases 2, 3, 4, and 5 have no dependency on each other — open separate PRs
for each rather than one giant branch, so each is reviewable and mergeable
on its own timeline. Phase 5 is sequenced last of the four only because it's
the one that touches `api.js`, and touching a shared file even in a narrow,
additive way is lower-risk once you've had practice with the zero-conflict
pattern on the other three.

---

## Phase 1 — Groundwork & environment audit (both of you, first, no exceptions)

Do not write a component until every box below is checked. This is the
"read before you build" pass that prevents the single most likely mistake
this round: rebuilding something that already exists, or picking a naming
convention that collides with one already in use.

### 1.1 — Get the app running locally

```bash
git clone https://github.com/anubrat1606/sih.git   # or pull if you already have it
cd sih
git checkout main && git pull origin main

# Backend (you won't be changing it, but the frontend needs it running to render real data)
cd services/orchestrator
python3 -m venv venv
./venv/bin/pip install -r requirements.txt -e ../core
createdb satyapramana_dev
export SATYAPRAMANA_MIGRATE_ON_START=1
export DATABASE_URL=postgresql://localhost/satyapramana_dev
./venv/bin/uvicorn satyapramana_store.app:app --port 4000

# Frontend, separate terminal
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Confirm `npm run build` and `npm run lint` are **both clean on `main` before
you change anything** — if either fails before you've touched a line, that's
a local setup problem, not something to fix as part of your task.

### 1.2 — Read, don't skim, these five files before writing any component

1. **`frontend/src/tokens.css`** — every colour, spacing value, radius,
   shadow, and motion duration you're allowed to use. There is no colour or
   pixel size anywhere in this task list that isn't already a token here.
   Note the three-part dual-theme structure (`:root`, the
   `prefers-color-scheme: dark` block, the `[data-theme="dark"]` block) —
   any new token you introduce (you shouldn't need to, but if a genuinely
   new semantic colour comes up, ask first) must follow the identical
   three-part pattern or it will break in one theme.
2. **`frontend/src/components.jsx`** — what already exists (`VerdictBadge`,
   `RiskBadge`, `Metric`, `CoverageMeter`, `ConflictCard`, `RepairAction`,
   `EvidenceChip`, `ProvenancePanel`). Read every one of their doc comments.
   If a task below sounds like it overlaps one of these, it doesn't — but
   confirm that for yourself rather than assuming.
3. **`frontend/src/App.css`** — the existing utility classes (`.hint`,
   `.error`, `.status`, `.card`, `.card-grid`, `.evidence-table`, `.badge`,
   `.actions`, `.form`) so you reuse them instead of reinventing equivalents
   with different names.
4. **`frontend/src/api.js`** — the one pattern every API call in this app
   follows (`call(path, options)`, the `URLSearchParams` convention for
   query params, the error-shape contract). Your own new API functions
   (Rishika, Phase 5 only) must follow this exact pattern, not a new one.
5. **This whole document**, including the phases that aren't yours, so you
   understand what Anubrat is building in parallel and why certain
   boundaries exist.

### 1.3 — Internalise the four rules that make zero-overlap possible

1. **Every file you create is new.** If a task seems to require editing an
   existing page (`pages/*.jsx`), `App.jsx`, `App.css`, `components.jsx`, or
   `tokens.css` — stop and message Anubrat. The one narrow, explicit
   exception is Rishika's Phase 5 (`api.js`, additive only, two new
   functions at the bottom of the file, nothing existing touched).
2. **Prefix every new CSS class with your component's own name.** A class
   called `.item` or `.row` will eventually collide with something in
   `App.css`. `.toast-item`, `.skeleton-row`, `.audit-timeline-item` — always
   namespaced to the component that owns it.
3. **Co-locate your CSS.** Each new component imports its own stylesheet
   directly in its own file — `import "./notifications.css"` at the top of
   `ToastHost.jsx`, for example. This is a real, working Vite pattern and it
   means your CSS reaches the page the moment your component is imported
   anywhere, with zero edits to any shared file, ever.
4. **To preview your own work while building it, temporarily render your
   component from `frontend/src/main.jsx` on your own machine — and revert
   that edit before your final commit.** `git diff main` right before you
   push must show only the new files your task names. This is the one place
   people who've never worked this way accidentally touch a shared file
   without meaning to; check for it explicitly every time.

### 1.4 — Cross-cutting requirements that apply to every component you build, no exceptions

These aren't optional polish — they're part of the definition of done for
every single task below, and are called out once here instead of repeated
nine times.

- **Both themes.** Toggle the theme switch in the top nav (light / dark /
  system) and look at your component in all three states before you
  consider it finished. Every colour must come from a token, which makes
  this automatic *if* you followed rule 1.3.2 — but actually look, don't
  assume.
- **`prefers-reduced-motion`.** Any animation or transition you add must
  read `tokens.css`'s `--duration-*` variables rather than a hardcoded
  `ms` value, so it goes to zero automatically under that media query
  (see the bottom of `tokens.css` for exactly how the existing tokens do
  this).
- **Keyboard operable.** Anything clickable is a real `<button>` or has a
  proper `role` and `tabIndex`, not a `<div onClick>`. Anything that opens
  (a toast, a dialog) is dismissible without a mouse.
- **No layout shift.** A skeleton must match the real content's dimensions
  closely enough that the page doesn't visibly jump when the real content
  replaces it.
- **A component that fetches or receives nothing renders an honest empty
  state, never a fabricated placeholder value.** Same "never guess" rule
  the whole backend already follows — it applies to frontend components
  now too.

---

## Phase 2 — Core interaction primitives

The building blocks everything later in this round sits on top of. Build
these before anything in Phase 3.

### S1 — Notification system (Suhani)

**Files:** `frontend/src/notifications/ToastProvider.jsx`,
`frontend/src/notifications/useToast.js`,
`frontend/src/notifications/ToastHost.jsx`,
`frontend/src/notifications/notifications.css`,
`frontend/src/notifications/index.js` (re-exports the three pieces so
Anubrat's later `import { ToastProvider, useToast } from "./notifications"`
is one line).

Right now every action in this app — register a bidder, upload a document,
run verification, evaluate, record a decision, override a verdict — either
silently updates the page or shows one red line via the existing
`ErrorBox`. Nothing ever confirms success.

```jsx
// notifications/ToastProvider.jsx
export function ToastProvider({ children }) {
  // Holds an array of { id, message, kind, createdAt } in state.
  // Renders children, then <ToastHost /> — do NOT require the caller to
  // place ToastHost themselves; bundling it here means Anubrat's
  // integration step is exactly one line: wrap <App/> in <ToastProvider>.
  // Expose the notify/dismiss functions through React context.
}

// notifications/useToast.js
export function useToast() {
  // Reads the context ToastProvider set up.
  // Returns { notify, dismiss }.
  // notify(message, { kind = "info", durationMs = 4000 } = {}) queues a
  //   toast and returns its id.
  // dismiss(id) removes one early (used by the toast's own close button).
  // Throws a clear error if called outside a ToastProvider — don't fail
  //   silently; a developer error here should be loud, not a fabricated
  //   no-op.
}

// notifications/ToastHost.jsx
export function ToastHost() {
  // Renders the current queue as a fixed-position stack (bottom-right is
  // the conventional choice; pick one, document it in a comment).
  // Each toast auto-dismisses after its durationMs unless the viewer
  // hovers it (pause countdown on hover, resume on mouseleave) — a toast
  // that vanishes while someone is mid-read is a real usability bug.
  // aria-live="polite" region wrapping the stack so screen readers
  // announce new toasts without interrupting whatever the user is doing.
}
```

Visual spec:
- `kind: "success"` → `var(--status-pass-bg)` background,
  `var(--status-pass-fg)` text/icon (reuse a checkmark glyph, same visual
  vocabulary as `VerdictBadge`'s own glyphs in `components.jsx` — don't
  invent a second icon language).
- `kind: "error"` → `var(--status-fail-bg)` / `var(--status-fail-fg)`.
- `kind: "info"` → neutral surface tokens (`var(--color-surface)`,
  `var(--color-border)`).
- Each toast: a card, `var(--radius-md)`, `var(--shadow-md)`, a close
  button, stacks with `var(--space-2)` gap between multiple toasts.
- Enter/exit transition uses `var(--duration-base)` and
  `var(--ease-standard)` — both already defined, both already zero out
  correctly under reduced motion.

**Acceptance criteria:**
- [ ] `useToast()` outside a provider throws a descriptive error, doesn't
      silently no-op.
- [ ] Three toasts fired in quick succession all render, stacked, each
      independently dismissible and independently timed.
- [ ] Hovering a toast pauses its auto-dismiss timer.
- [ ] Visually correct in light, dark, and system theme.
- [ ] Zero animation under `prefers-reduced-motion: reduce` (test via your
      browser devtools' rendering-emulation panel).
- [ ] A short temporary preview (rendered from `main.jsx`, reverted before
      your final commit per rule 1.3.4) showing all three `kind`s stacked.

### S2 — Loading skeletons (Suhani)

**Files:** `frontend/src/Skeleton.jsx`, `frontend/src/skeleton.css`.

Every page today either renders nothing or jumps straight from blank to
full the instant its `fetch` resolves.

```jsx
export function SkeletonLine({ width = "100%" }) {
  // One shimmering bar, height matched to --text-base line height.
}
export function SkeletonCard() {
  // A placeholder matching .card's real padding/border/radius from
  // App.css exactly, containing a couple of SkeletonLines at varied
  // widths so it doesn't read as a single grey rectangle.
}
export function SkeletonTable({ rows = 4, columns = 4 }) {
  // Matches .evidence-table's real row height and border treatment.
}
```

Shimmer: a `background-position` animation sweeping a lighter gradient band
across `var(--color-border)`, duration from `var(--duration-slow)` — but
because a single sweep is barely perceptible, this is the one place a
*looping* animation is justified (the token comment says "nothing loops" for
functional motion; a loading shimmer is the standard, expected exception —
note this reasoning in a code comment so a future reader doesn't "fix" it
into matching the no-loop rule everywhere else). Must still collapse to a
static, non-animated placeholder under reduced motion — a still grey block
communicates "loading" perfectly well without motion.

**Acceptance criteria:**
- [ ] `SkeletonCard`'s rendered height/width is within a few pixels of a
      real populated `.card` (put one of each side by side to check).
- [ ] `SkeletonTable` accepts `rows`/`columns` and renders correctly at
      both extremes (1×1 and 8×6).
- [ ] Shimmer is static under reduced motion, animated otherwise.
- [ ] Correct in both themes.

### R1 — Search + filter bar (Rishika)

**Files:** `frontend/src/SearchFilterBar.jsx`,
`frontend/src/searchFilterBar.css`.

A generic list-filtering control — not hardcoded to tenders or bidders, so
it can be reused anywhere a list needs it later.

```jsx
export function SearchFilterBar({ items, searchKeys, sortOptions, onChange, placeholder }) {
  // items: array of plain objects, owned entirely by the caller.
  // searchKeys: array of property names to case-insensitive substring-
  //   match against (e.g. ["bidder_id"]). Matches if ANY key matches.
  // sortOptions: array of { label, compare(a, b) } — rendered as a
  //   <select>; the first option is the default/initial sort.
  // onChange(filteredAndSortedItems): called on mount and on every
  //   change to the query or sort selection. This component renders
  //   ONLY its own search input + sort <select> — it never renders the
  //   list itself. The caller (Anubrat, in Phase 7) owns rendering the
  //   filtered result.
  // placeholder: optional input placeholder text, defaults to "Search…".
}
```

**Acceptance criteria:**
- [ ] Empty `items` array: renders the controls, calls `onChange([])`,
      doesn't throw.
- [ ] Typing a query that matches nothing calls `onChange([])`, and your
      temporary preview shows this doesn't look broken (there's nothing
      about this component that should render "no results" text itself —
      that's the caller's job — but confirm the control itself stays
      usable, doesn't clear itself, etc.).
- [ ] Switching `sortOptions` mid-query re-applies the current search
      query to the new sort, doesn't reset the search box.
- [ ] Keyboard-only: tab into the search box, type, tab to the sort
      `<select>`, change it with arrow keys — no mouse required at any
      point.

---

## Phase 3 — Feedback, validation & confirmation (Suhani)

Depends only on Phase 1. Can start alongside Phase 2 if you want to
parallelise your own two PRs, or after — your call.

### S3 — Inline form validation

**Files:** `frontend/src/validation.js`, `frontend/src/FieldHint.jsx`,
`frontend/src/fieldHint.css`.

`RegisterBidderPage.jsx` and the upload/verify flow currently give no
feedback until the server rejects something.

```js
// validation.js — pure functions, no React, fully unit-testable in isolation
export function checkGstinFormat(value) {
  // Returns { valid: boolean, hint: string }.
  // Structural shape only: 2-digit state code + 10-char PAN + 1-digit
  // entity code + literal "Z" + 1 checksum char = 15 chars total.
  // This mirrors the SHAPE services/orchestrator/satyapramana_store/
  // extract/grammars.py validates server-side (read GSTIN_RE there for
  // the real regex) but this is a UX hint only — it must never claim a
  // GSTIN is valid or invalid with more confidence than "looks
  // structurally plausible" vs "doesn't." The server remains the one
  // real validator; this only saves someone a wasted round trip for an
  // obviously malformed value.
  // Return an empty hint (not null) for an empty/untouched value — let
  // the caller (FieldHint) decide whether "untouched" renders anything.
}
export function checkPanFormat(value) {
  // Same idea: 5 letters + 4 digits + 1 letter, 10 chars.
}
export function checkCinFormat(value) {
  // Same idea: 21-char CIN shape (L or U, 5 digits, 2-letter state, 4-
  // digit year, 3-letter ownership class, 6 digits).
}
```

```jsx
// FieldHint.jsx
export function FieldHint({ result }) {
  // result is one of the above functions' return shape, or
  // null/undefined for "field not yet touched" — renders nothing in
  // that case (never a placeholder-shaped ghost element).
  // Once there's a result: a small inline hint line, neutral tone while
  // the value is still short/ambiguous, a clear positive or negative
  // tone (reuse --status-pass-fg / --status-fail-fg, glyph + text, same
  // colour-is-never-the-only-signal rule VerdictBadge already follows)
  // once the value is long enough to judge structurally.
}
```

**Acceptance criteria:**
- [ ] Each `checkXFormat` function has been exercised against at least one
      genuinely valid structural example and three genuinely malformed
      ones (wrong length, wrong character class, right length wrong
      shape) — write these as plain `console.assert` checks in a
      temporary scratch file if you don't have a test runner wired up for
      pure JS yet; don't skip verifying the logic just because there's no
      formal test harness for this file today.
- [ ] `FieldHint` with `result={null}` renders nothing at all (not an
      empty box, not `undefined` text — literally nothing in the DOM).
- [ ] Colour is never the only signal — every valid/invalid state also
      has a glyph and a text label.

### S4 — Confirmation dialog

**Files:** `frontend/src/ConfirmDialog.jsx`, `frontend/src/confirmDialog.css`.

```jsx
export function ConfirmDialog({ open, title, body, confirmLabel, cancelLabel, danger, onConfirm, onCancel }) {
  // open: boolean, controls mount/visibility entirely (caller owns state).
  // danger: boolean — when true, the confirm button uses the existing
  //   button.danger treatment from App.css (don't redefine that colour,
  //   reference the same class or the same tokens it uses).
  // onConfirm / onCancel: called, caller closes the dialog by flipping
  //   `open` to false — this component never manages its own open state.
}
```

Will be wired later (Phase 7) to the Disqualify decision button and the
officer Override action — both currently fire immediately with zero
confirmation. Build it generic, not hardcoded to either use case.

**Required behaviour, not optional:**
- `role="dialog" aria-modal="true"`, labelled by the `title` prop via
  `aria-labelledby`.
- Focus moves into the dialog when it opens (to the cancel button, not the
  confirm button — the safer default when a real destructive action is one
  Enter-key press away), and returns to whatever triggered it when it
  closes.
- Escape key calls `onCancel`.
- Clicking the backdrop calls `onCancel`.
- Focus is trapped inside the dialog while open — Tab cycles between its
  own focusable elements only, never escapes to the page behind it.

**Acceptance criteria:**
- [ ] Every item in "Required behaviour" above, checked by hand — open the
      dialog, immediately press Tab repeatedly and confirm focus never
      leaves it; press Escape and confirm it closes; click outside it and
      confirm it closes.
- [ ] `danger={true}` visibly differs from `danger={false}`.
- [ ] Correct in both themes.

### S5 — Empty states

**Files:** `frontend/src/EmptyState.jsx`, `frontend/src/emptyState.css`.

```jsx
export function EmptyState({ message, actionLabel, actionTo }) {
  // message: the honest "there's nothing here yet" text.
  // actionLabel / actionTo: optional — when both are given, renders a
  //   link (react-router's <Link>, already a project dependency) to the
  //   action that would create the first item. When omitted, renders
  //   just the message, centred, with some breathing room — never a
  //   broken half-rendered action row.
}
```

Will replace the plain `<p className="hint">` empty-state text scattered
across `TendersPage.jsx` ("No tenders yet"), `TenderDashboardPage.jsx` (no
bidders registered), and the document list on the bidder detail page.

**Acceptance criteria:**
- [ ] Renders correctly with only `message` (no action).
- [ ] Renders correctly with `message` + `actionLabel` + `actionTo`.
- [ ] The action, when present, is a real keyboard-focusable link, not a
      styled `<span>`.

---

## Phase 4 — Data visualisation (Rishika)

Depends only on Phase 1. Independent of Phase 3 and Phase 5 — build in
whatever order you prefer, but open R2 and R3 as separate PRs.

### R2 — Chart primitives

**Files:** `frontend/src/charts.jsx`, `frontend/src/charts.css`.

Pure SVG, no new dependency — this project explicitly avoids adding chart
libraries where hand-drawn SVG does the job (the same reasoning that kept
the Evidence Graph a deterministic hand-rolled layout instead of pulling in
another graph library).

```jsx
export function RiskDistributionBar({ low, medium, high }) {
  // A horizontal stacked bar. Segment widths must be genuinely
  // proportional to the three counts — if low=2, medium=0, high=3, the
  // rendered segments are a 2:0:3 ratio of the bar's total width, not an
  // evenly-thirded bar with one empty-looking segment. Colours:
  // --risk-low-fg / --risk-medium-fg / --risk-high-fg, the exact three-
  // value risk palette the rest of the app already uses — never a new
  // colour for this. Each segment shows its count as a label if there's
  // room, and the bar overall needs a total count somewhere near it
  // (caller can also render that separately — your call, document which
  // you chose).
}
export function Sparkline({ values, width = 120, height = 32 }) {
  // A small inline line/area chart. values is a plain array of numbers,
  // may be empty (render a flat baseline, not an error) or contain a
  // single value (render a single point, not a divide-by-zero crash on
  // an x-axis step calculation).
}
export function StatTile({ label, value }) {
  // A single big-number tile: value in --font-mono with
  // font-variant-numeric: tabular-nums (matches .metric-value's existing
  // convention in App.css — read it, mirror it, don't reinvent it),
  // label beneath in --text-xs, uppercase, --color-text-secondary. When
  // value is null/undefined, render an em dash "—", never a fabricated
  // 0 — the exact same honesty rule Metric already follows in
  // components.jsx; read that component before you build this one.
}
```

Chart-drawing requirements (from this project's own design process, apply
them even though this isn't a Claude-published artifact):
- Draw to the real scale — a value of 0 must visibly differ from a small
  non-zero value, never rounded up to "looks like something."
- Every text label takes its colour from a token, never a literal hex, so
  it reads correctly in both themes.
- Leave room in the SVG `viewBox` for every label so nothing clips at the
  edge.
- Every drawn shape has an explicit `fill` (or explicit `fill="none"` with
  a `stroke`) — never rely on SVG's implicit default fill, which is black
  and will look like a bug in dark mode.

**Acceptance criteria:**
- [ ] `RiskDistributionBar` with `{low: 0, medium: 0, high: 0}` renders an
      honest "nothing to show" state, not a divide-by-zero-sized bar.
- [ ] `RiskDistributionBar` with a real, visibly-asymmetric input (e.g.
      `{low: 1, medium: 0, high: 5}`) shows segments genuinely
      proportional to 1:0:5 — measure the rendered widths, don't eyeball
      it.
- [ ] `Sparkline` handles an empty array and a single-value array without
      throwing.
- [ ] `StatTile` with `value={null}` renders "—", not "0", not "null",
      not "NaN".
- [ ] All three correct in both themes.

### R3 — Audit timeline

**Files:** `frontend/src/AuditTimeline.jsx`, `frontend/src/auditTimeline.css`.

`AuditPage.jsx` currently dumps the full JSON Lines export into a raw
`<pre>` block. Build a real visual renderer:

```jsx
export function AuditTimeline({ events, filterType }) {
  // events: array of { event_type, occurred_at, payload, seq, ... } —
  //   exactly the shape GET /audit/export's JSON Lines already is, one
  //   object per line, already parsed into objects by the caller.
  // filterType: optional single event_type string to restrict the view
  //   to; when omitted, show everything.
  // Renders a vertical chronological list — pick oldest-first or newest-
  //   first and be consistent (oldest-first mirrors how the hash chain
  //   itself is built and is the more defensible choice, but either is
  //   fine; document which you picked in a code comment).
  // One row per event: an icon + a distinct colour keyed by event_type
  //   (VERIFICATION_OBSERVED should look visibly different from
  //   VERIFICATION_FAILED, which should look visibly different from
  //   REQUIREMENT_EVALUATED, DOCUMENT_INGESTED, FIELD_EXTRACTED, and so
  //   on — there are roughly ten distinct event types in this system;
  //   grep `event_type=` across services/orchestrator/satyapramana_store/
  //   for the authoritative list rather than guessing at what exists),
  //   the timestamp in --font-mono, and the seq number.
}
```

Reuse the same "one readable line per event type" idea already solved in
`components.jsx`'s `PROVENANCE_SUMMARY` object and `ProvenanceStep`
component — don't invent a second convention for summarising an event
payload without a raw JSON dump. Read that object's structure and mirror
its shape (a lookup table keyed by `event_type`, with a fallback for any
type not listed so an unrecognised event still renders something instead of
nothing).

**Acceptance criteria:**
- [ ] At least six distinct real event types (pull a real sample from
      `GET /audit/export` against your local running backend after you've
      clicked through a few actions in the app) each render visibly
      differently — different icon and/or colour, not just different
      text.
- [ ] An event type not in your lookup table still renders a readable row
      (the fallback path), never a blank or broken one.
- [ ] `filterType` set to a real event type shows only matching rows.
- [ ] Correct in both themes.

---

## Phase 5 — Backend-wired report actions (Rishika)

Depends on Phase 1. The one phase that touches a shared file — do this
after R2/R3 are already merged, so you're rebasing a small, focused change
onto a `main` that's only moved forward by your own earlier merges, not
racing anyone else's edit to the same file.

### R4 — Report actions

**Files:** `frontend/src/ReportActions.jsx`, `frontend/src/reportActions.css`,
**plus exactly two new lines appended to the bottom of** `frontend/src/api.js`.

Two backend endpoints have been live and tested since round 3 with no UI
ever calling them:

```
GET /tenders/{tender_id}/report/csv
GET /tenders/{tender_id}/blockers
```

Add to `api.js` — **append only, following the file's existing pattern
exactly, do not reformat or reorder anything already there:**

```js
export const getTenderReportCsv = (tenderId) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/report/csv`);

export const getTenderBlockers = (tenderId) =>
  call(`/tenders/${encodeURIComponent(tenderId)}/blockers`);
```

Then build:

```jsx
export function ReportActions({ tenderId }) {
  // A small action row with two controls:
  //
  // 1. "Download CSV" — calls getTenderReportCsv(tenderId), which
  //    returns the raw CSV text (api.js's call() already returns text
  //    for a non-JSON content-type — confirm this by reading call()'s
  //    implementation, don't assume). Trigger a real browser download:
  //    build a Blob from the text with type "text/csv", an object URL,
  //    a temporary <a download> click, then revoke the object URL. Name
  //    the downloaded file something like `${tenderId}-report.csv`.
  //
  // 2. "Show blockers" — calls getTenderBlockers(tenderId), toggles an
  //    inline table into view (reuse the existing .evidence-table class
  //    from App.css, don't invent a new table style): one row per
  //    requirement_id, its blocked_bidder_count, and its
  //    classifications (join the array with ", "). An empty blockers
  //    list renders an honest "no blockers" message, not an empty
  //    table with just a header row and nothing under it.
  //
  // Both actions independently loading-state and error-state aware —
  // reuse the notify() pattern from Phase 2's S1 if it's merged by the
  // time you build this (optional — if S1 isn't merged yet, a plain
  // inline error message is an acceptable fallback; don't block on
  // Suhani's PR).
}
```

**Acceptance criteria:**
- [ ] Clicking "Download CSV" against your real local backend produces an
      actual file download with real content — open the downloaded file
      and confirm it's genuine CSV, not `"[object Object]"` or similar.
- [ ] "Show blockers" against a tender with a real adopted rule pack and a
      real blocking requirement shows a real row.
- [ ] "Show blockers" against a tender with nothing blocking anyone shows
      the honest empty message, not a bare empty table.
- [ ] `git diff main -- frontend/src/api.js` shows **only** the two new
      exported lines above added at the end of the file — nothing else in
      that file changed, not even whitespace.

---

## Phase 6 — Anubrat's parallel heavy build (context only — not your task)

Runs concurrently with Phases 2–5, touches only files Anubrat owns
(`app.py`, `core`, existing frontend pages). Included here so you understand
what will exist by the time Phase 7 (Integration) starts:

- **A1** — `GET /dashboard` aggregate endpoint (tender/bidder counts, risk
  distribution, recent decisions, capability status).
- **A2** — Rule pack builder: replaces the raw-JSON textarea on
  `TenderDashboardPage.jsx` with a guided requirement composer.
- **A3** — Explicit Tender Management: a real "create tender" endpoint +
  flow, instead of a tender only existing implicitly once a bidder
  registers on it.
- **A4** — Tender Intelligence: Gemini reads a tender PDF and *proposes* a
  draft rule pack; an officer must review and adopt it before it's ever
  live — the LLM proposes, it never decides, same boundary EXPLAIN already
  follows.
- **A5** — Zoom/pan/reset/legend/click-to-filter on both the collusion
  force-graph and the Evidence Graph.
- **A6** — `PdfEvidenceViewer` as a real modal/lightbox with multi-region
  navigation.
- **A7** — The new Mission Control dashboard page, built on A1 plus your
  Phase 4 chart primitives and Phase 4 audit timeline (a preview of it) —
  this is the reason R2/R3 are useful beyond the audit page itself.

---

## Phase 7 — Integration (Anubrat only)

**Neither of you touches this phase.** Once Phases 2–6 have all merged to
`main`, Anubrat:

- **A8** — Wires `ToastProvider`/`useToast` around `<App>` and into every
  action handler across the app; replaces blank initial-load states with
  the skeleton components; wires `FieldHint` into the register/upload
  forms; wires `ConfirmDialog` into Disqualify and Override; replaces plain
  empty-state text with `EmptyState` everywhere a list can be zero-length.
- **A9** — Wires `SearchFilterBar` into `TendersPage.jsx` and the bidder
  card grid; replaces the audit page's raw dump with `AuditTimeline`; wires
  `ReportActions` into the tender dashboard; uses the chart primitives in
  the Mission Control dashboard.

You'll be told when this phase lands — that's your signal for Phase 9.

---

## Phase 8 — Regression, accessibility & cross-theme QA (Anubrat only)

**A10** — After Phase 7 merges: full build, full lint, the full backend
test suite, a live curl-and-click walkthrough of every feature (the same
standard every PR this project has been held to all along), plus a
dedicated pass through the cross-cutting requirements in section 1.4 above
— now checked at the integrated, whole-app level rather than per-component.

---

## Phase 9 — Demo prep, responsive pass & rehearsal

- **A11** (Anubrat) — A one-command seed script producing a realistic
  multi-bidder, multi-tender demo state; at least one full dry run of the
  demo script in the roadmap artifact linked at the top of this document.
- **R5** (Rishika) — **Do not start until Anubrat confirms Phase 8 is
  merged to `main`.** Audit every page — including the new Mission Control
  dashboard and every component built this round — at ~400px width and fix
  what breaks. This genuinely does mean editing existing page CSS, which is
  exactly why it's sequenced dead last: there's one stable, fully-integrated
  version of every page to fix by the time you start, instead of a moving
  target.

---

## PR shape, across the whole round

Open one PR per numbered task-group as noted in each phase (S1 alone, S2
alone, S3+S4+S5 together or separately — your call as long as each PR is
independently reviewable; R1 alone, R2 alone, R3 alone, R4 alone, R5 alone
at the end). Each PR description states which acceptance-criteria checklist
it satisfies, copied in with boxes checked. CI
(`.github/workflows/ci.yml`) runs the frontend build+lint job automatically
on every PR — it must be green before anyone reviews it. Then wait: per the
"Merge approval" section above, Anubrat merges every PR himself once he's
reviewed it. Green CI plus an open PR is where your part ends.

**Definition of done, every single task in Phases 2–5:**
```bash
cd frontend
npm run build   # must stay clean
npm run lint    # must stay clean
```
No backend test suite involvement this round — everything either of you is
building is presentational, frontend-only, and the acceptance criteria
listed under each task are the real test suite for this round.

If anything anywhere in this document is ambiguous, stop and ask — the
sections above were written to leave nothing to interpretation, so an
ambiguity you find is more likely a real gap worth flagging than something
you're missing.
