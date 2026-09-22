# Round 10 — close the real PS26100 gaps + judge-facing UI (Anubrat, Rishika)

Rescopes `docs/ROUND_10_PLANNING.md`. That doc's single-bidder read
performance fix is real but invisible to a judge — deferred, not
cancelled; revisit once the items below ship. This round exists because
of a direct finding: checking the actual SIH26100 problem statement
(not just our own `satyapramana.md` charter) against the live code
turned up 6 of its 14 named "Expected Solution" points as not met or
partially met, and the one artefact currently being judged (the idea
PPT) has zero screenshots of a product that, in every other respect,
is ahead of typical SIH idea-stage submissions.

No staggered start this time — unlike round 8, neither track blocks
the other. Both start now.

---

## Anubrat — close the real integration gaps

Checked what's actually buildable before assigning anything, instead of
guessing:

**Real quick wins — same vendor account you already have live
credentials with, no new registration:**

- **GST return-filing status.** Sandbox.co.in's GST product (the same
  one backing `GST_STATUS` in `adapters/sandbox_co_in.py`) also exposes
  GSTR-1/3B/2B filing data. Add a `GST_RETURN_STATUS` capability
  alongside the existing three, same adapter file, same
  `capability_manifest` / raw-response-archive / failure-taxonomy
  pattern the other three already follow. Closes PS point 3 in full
  (registration was already done; filing status was the missing half).
- **DigiLocker.** Sandbox's KYC product line includes DigiLocker and
  EntityLocker — already referenced in a design comment
  (`adapters/base.py:58`, consent-artefact handling) but never built.
  This is PS point 8, named explicitly, currently at zero coverage.
  Same vendor, same consent-metadata discipline that comment already
  anticipates.

**Real gaps, closed honestly rather than left silent — reuse round 9's
declaration mechanism, don't build new infrastructure:**

- Make in India / local content (PS 5), Startup India / NSIC / OEM
  authorization (PS 7), blacklisting/debarment status (PS 9) — none of
  these have a public verification API path that turned up in research.
  Model each as a new requirement type on the existing self-declared
  Tier C path (`declarations.py`'s `declaration_field()`, the
  `SELF_DECLARED_CEILING` rule already caps these at `PARTIAL` on a
  mandatory requirement — correct, not a shortcut). This is a
  `requirement_types.py` + rule-pack-schema registration task, not new
  adapter code.
- Udyam **status** verification (PS 2) and EPFO/ESIC (PS 6) — no real
  path found this round either (Udyam: confirmed no Sandbox product;
  EPFO/ESIC: confirmed unavailable in round 10's own prior research).
  Give both the same one-string honesty fix the ITR note already got:
  say the specific real reason, not the generic "no capability yet"
  placeholder. Udyam **number extraction** (not status) already works
  and stays as-is.

**Definition of done:** `GST_RETURN_STATUS` and `DIGILOCKER` live and
tested the same way `PAN_STATUS`/`GST_STATUS`/`CIN_STATUS` are (real
adapter, real capability manifest, honest failure taxonomy, tests that
hit the real Sandbox sandbox environment, not a mock). The three
self-declared types adoptable in a rule pack and evaluated end-to-end
with a real `SELF_DECLARED_CEILING` test, same shape as
`test_declarations.py`. Udyam-status and EPFO/ESIC notes rewritten.

---

## Rishika — landing page + judge-facing UI pass

**Start with an audit, not an assumed list of defects** — I haven't
done a fresh pass on `frontend/src/landing/LandingPage.jsx` or the
officer-facing pages this round, so don't take the items below as
confirmed bugs. Check each against `satyapramana.md` §2.3 (Commitment
III — the design system the charter requires): design tokens with no
hard-coded hex, both themes fully defined (not one as an afterthought),
one display family / one text family / one tabular-numeral mono for
every identifier, amount, date, score, the locked four-value status
palette (color + glyph + label, never color alone), and the named
primitives (`EvidenceChip`, `VerdictBadge`, `ProvenanceTrail`,
`CoverageMeter`) actually used consistently rather than one-off markup
per page. Fix what the audit actually finds.

**Concrete, not audit-gated:**

- **Screenshot-readiness pass** on the Evidence Graph
  (`EvidenceGraphPage.jsx`) and the Audit/Temporal-Scrubber views
  (`AuditTrailPage.jsx`, `BidderHistoryTimeline.jsx`) — these are the
  two screens the readiness review flagged as needed in the SIH idea
  PPT and currently absent. "Screenshot-ready" means: real data on
  screen (not an empty state), nothing clipped or overlapping at the
  resolution a screenshot would use, no debug/placeholder text visible.
- **Landing page** — public-facing, no login required, the first thing
  anyone opens from a link. Make it earn that position: what the
  product is, the four-state verdict promise, a real (not simulated)
  path into the live system. Same design-token discipline as above.

**Definition of done:** a written note of what the audit found (even if
the answer is "already compliant, nothing to fix" on some points — say
that too, don't pad it), the two screenshot-ready views, and the
landing page refresh, each demoed live before merge same as every prior
round.

---

## Rules, unchanged

Nobody merges their own PR except Anubrat's own backend task (same
exception as every round). Real Postgres, real Sandbox sandbox
environment, real screenshots before claiming "done." No mock data —
the `data/satyapraman_mock_...xlsx` file sitting untracked in the repo
right now is not sanctioned for use in either track until its origin
and purpose are confirmed.
