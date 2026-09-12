# Evaluation Readiness — what works, what to do in the next 6-7 hours

Written for the team, in plain language, ahead of the first evaluation.
No jargon where it can be avoided — for full technical detail see
`STATUS.md`; for the pitch itself see `PRESENTATION.md`.

**Snapshot as of now:** everything below "Live and working" is merged to
`main` and running on the internet today. One more branch
([PR #66](https://github.com/anubrat1606/sih/pull/66)) is built, tested,
and waiting for review — merging it is the single highest-value thing to
do in the next 6-7 hours, and it's listed first for that reason.

---

## ✅ Live and working right now

Anyone can open the deployed link and see this today — nothing below is
aspirational.

- **Officer portal** — secure login, three roles (officer / senior officer
  / admin), create a tender, upload the tender's own notice PDF, register
  a bidder, upload a bidder's documents (PAN / GST / Udyam / company
  registration), and run verification.
- **Real, live document reading** — GSTIN/PAN/registration numbers are
  read straight off the uploaded PDF, structurally validated (catches a
  typo'd or fake number before anything else happens), no manual typing.
- **Real, live government verification** — PAN, GST, and company
  registration (CIN) status are checked against a real verification
  service (Sandbox.co.in), genuinely switched on, not a placeholder.
- **Collusion detection** — automatically flags two bidders on the same
  tender who secretly share a director, address, phone number, or bank
  account.
- **Guided rule-pack builder** — an officer defines exactly what a tender
  requires through a form, not code; a requirement-type picker pre-fills
  the technical bits for the types the system can actually check.
- **AI-assisted requirement suggestions** — reads a tender PDF and
  proposes candidate requirements for an officer to approve or reject.
  The model never decides anything on its own.
- **Three-way scoring, kept honestly separate** — how compliant, how
  strong the evidence is, how much got independently verified. Never
  mashed into one misleading number.
- **"Why did this bid fail?" / "What fixes it?"** — a plain-language
  breakdown of every blocking requirement, and the specific action that
  would cure each curable one.
- **Evidence Graph** — a visual map from requirement → document → page →
  verification → final decision. Nothing is a black box.
- **A permanent, tamper-evident record** of every action — nobody,
  including an admin, can silently edit or delete history.
- **Reports** — exportable summaries and CSVs of how a tender's bidders
  are doing.
- **One real government tender loaded in** — a real BHEL/GeM tender
  (metallic expansion joints, Enquiry No. T7J1Z68239), sourced from GeM's
  own public catalog, with a real 3-requirement rule pack built and
  switched on.
- **Deployed and shared** — the whole thing runs on the internet
  (Render + a shared Neon Postgres database) so every team member and
  every evaluator uses the exact same live system, no installation.

## 🟡 Built and tested, one merge away from live

**Bidder self-service portal + real accounts** ([PR #66](https://github.com/anubrat1606/sih/pull/66))
— a second, public-facing side of the product, separate from the officer
tool:

- Real sign-up/sign-in for bidders (not a demo login) — hashed passwords,
  real sessions, a real database table, kept structurally impossible to
  mix up with an officer account.
- Email verification and mobile OTP verification — both fully real (a
  real one-time code/link is generated, checked, and expires); actually
  *delivering* that email/SMS needs one more piece of configuration (see
  below), so today it's provably real end-to-end except the last "text
  message leaves the building" step.
- Forgot/reset password, Google Sign-In (works once one config value is
  set), change password.
- A public bidder dashboard: browse tenders, register, upload documents,
  run verification, track "My Bids" and results — using the same real
  backend the officer portal uses, nothing faked.
- 213 automated tests passing for this alone.

**Why this matters for the evaluation:** right now, only an officer can
use the live system. This PR lets a judge or evaluator sign up *as a
bidder* themselves, in the browser, and watch their own document get
verified live — which is a much stronger demo than only being shown
screenshots of the officer side.

---

## 🎯 The single biggest gap: no real bidder data

Every piece above has been tested with structurally-real but
**not-yet-real-world** data. Nobody has pushed a real, consenting
person's real PAN/GST documents through the live system end to end. This
is not a coding gap — it needs actual people who agree to have their real
documents processed for the demo. **This has been the top blocker since
round 2 and only the team can close it**, not any amount of further
development.

What's needed, concretely: **3+ real, consenting people or small
businesses** (teammates, family, willing volunteers — anyone with a real
PAN and a real GST or Udyam registration), with **two of them sharing one
real attribute** (same director name, address, phone, or bank account) so
the collusion detector has something genuine to catch on stage.

---

## What to do in the next 6-7 hours, in order

1. **(30 min, whoever reviews code) Merge PR #66.** It's built, tested
   (213 passing), and reviewed against the existing patterns. This turns
   "bidder portal" from a screenshot into something a judge can click on
   themselves.
2. **(Team, ~1-2 hours, can run in parallel with everything else) Source
   3+ real consenting bidders** per the gap above, and get their real
   documents. This is the task with the longest lead time and the only
   one that isn't "more coding" — start it first, let it run in the
   background while the rest of this list happens.
3. **(15 min) Confirm the shared verification keys are live on Render.**
   `SATYAPRAMANA_SANDBOX_API_KEY`/`_SECRET` need to be set on the
   deployed backend (not just on someone's laptop) for PAN/GST/CIN
   verification to actually run during the live demo instead of showing
   `UNAVAILABLE`. Whoever has the Render dashboard access should check
   this first, since it's a five-minute fix if it's missing.
4. **(30-45 min, once step 2 lands) Run the real bidders through the
   live system**, end to end: register → upload → verify → see the
   score, the evidence graph, and (if two bidders share an attribute) the
   collusion flag actually fire on real data. This is the single most
   convincing thing to show a judge.
5. **(30 min) Rehearse a 5-minute walkthrough** using the real tender +
   real bidder(s) from steps 2 and 4: create/open the tender → show the
   rule pack → register a bidder → upload a document → show it get read
   automatically → show live verification → show the evidence graph →
   show the plain-language "why" explanation. Know the script before
   the room does.
6. **(30 min) Smoke-test the live URL fresh**, in an incognito window, as
   if you were the evaluator: does login work, does the bidder portal
   (once merged) work, does a fresh tender/bidder flow work with no
   leftover browser state helping it along?
7. **(Optional, if time remains) Configure email delivery** (SMTP) for
   the bidder portal's verification emails, so "sign up as a bidder"
   during the demo produces a real email in a real inbox, not just a
   "delivery not configured" notice. This is a few environment variables
   on Render — see `PR #66`'s description for exactly which ones.
8. **(Optional, if time remains) Refresh `STATUS.md` and `README.md`**
   so they reflect PR #66 being merged (`STATUS.md` currently predates
   it) — an evaluator who reads the repo, not just the demo, should see
   the same picture the demo shows.

## What is honestly still out of reach for this evaluation, and why

These are not being hidden — they're capability gaps with a real reason,
not unfinished homework:

- **Turnover, past experience, certifications, signed declarations** —
  there is no official online source to check any of these
  automatically. The system correctly flags them "needs a human to
  review" instead of pretending to check them. Fixing this needs a
  different kind of government data access this team doesn't have, not
  more engineering time.
- **EPFO/ESIC registration checks** — confirmed, permanently: no lawful
  online source exists for this anywhere. Not a "haven't built it yet."
- **SMS delivery for mobile OTP** — the code path is fully real (a real
  code is generated, hashed, rate-limited, and checked); only *texting*
  it to a phone needs a paid SMS provider account nobody has set up yet.
