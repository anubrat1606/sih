# Demo script — screen recording + voiceover

For the YT submission video. Target ~4-5 minutes. Every number and screen
below was checked live against the real deployment on 2026-09-29 — if it's
been a while, spot-check the live numbers before recording (`GET
/capabilities`, the BHEL tender's bidder list) since they can genuinely
change as more real data gets added.

**Before you hit record**: open `https://sih26100-orchestrator.onrender.com/health`
once to wake the free-tier instance from cold-start — the first real
request after inactivity takes a couple of seconds, which reads as a
stall on camera if it happens mid-recording instead.

**Do not navigate to tender `34532`** — an empty stray tender from testing,
zero bidders, adds nothing and looks unpolished.

---

## 1. Open — the problem (15-20s, no screen yet or a title card)

> "Procurement officers on GeM verify bidder eligibility by hand — opening
> each document, checking it against separate government portals one at a
> time, with nothing cross-referencing bidders against each other for
> collusion. SATYAPRAMĀṆA — Sanskrit for 'true evidence' — automates that,
> with one rule we never break: nothing in this system is faked. Every
> fact you're about to see is either real extraction, a real live
> government-linked check, or explicitly marked as unverified, with the
> real reason why."

## 2. Settings / capabilities screen (20-30s)

Navigate to Settings (or wherever `GET /capabilities` renders).

> "Here's the honest state of what we can verify live, right now: PAN,
> GST registration, GST return filing, MCA company status, and DigiLocker
> Aadhaar consent — five real, live checks against real government-linked
> sources. Udyam is awaiting credentials for a second vendor. EPFO and
> ESIC verification genuinely doesn't exist anywhere as a public API — we
> checked, and we say so, instead of faking a green checkmark."

*(This screen is your strongest differentiator — most hackathon demos
never show what doesn't work. Spend real time on it.)*

## 3. Upload / registration flow (30-40s)

Register a bidder live, or open an already-registered one if a fresh
upload feels risky on camera (extraction + a live verification call adds
real wait time). If registering live:

> "An officer uploads a bidder's PAN and GST documents. Extraction is
> deterministic — regex-based, not a black box — and every field carries
> its real page and pixel location, which you'll see in a moment."

## 4. Bidder compliance page — `ANUBRAT-DAS` on `BHEL-T7J1Z68239` (45-60s)

This is a real GeM tender (BHEL, Enquiry No. T7J1Z68239) with a real
adopted rule pack.

> "This bidder is HIGH risk — 50% compliance, but more importantly, 0%
> verification coverage on mandatory requirements. That's the point of
> keeping these numbers separate: a bid can look compliant and still be a
> real procurement risk if almost none of it was actually checked against
> an authority."

Switch to `GST-BIDDER-01` on the same tender:

> "This one is the opposite case — 100% compliant, 100% evidence
> confidence, but only 33% coverage. Still flagged HIGH risk, because
> compliance alone was never the full picture. We never blend these three
> numbers into one badge — that would hide exactly the risk that matters."

## 5. Evidence Graph (45-60s) — the signature screen

Open the Evidence Graph for either bidder.

> "This is the Evidence Graph — every fact traced from its source
> document, through extraction, through verification, to the requirement
> it satisfies. Not a generic force-directed layout — a deterministic
> three-column trace. Click into a node and it opens the real source
> document, on the real page, with the exact region highlighted."

Click a node, show the PDF lightbox jumping to the real page/region.

## 6. EXPLAIN — the AI narration (30-40s)

Open the EXPLAIN panel for `ANUBRAT-DAS`.

> "This is the one place a language model touches the system — and it
> only narrates a decision that's already final. It can't alter a verdict,
> a score, or a reason code. Every fact it states was already computed
> deterministically before the model ever saw it."

Let the real narrative render on camera (it's already confirmed working
live — real prose, not a mock).

## 7. Audit log (20-30s)

Open the audit trail / `/audit/verify`.

> "Every action — every extraction, every verification call, every
> decision — is a real, hash-chained event. Each event's hash includes
> the one before it, so tampering with history breaks the chain visibly.
> This isn't a claim — it's independently re-verifiable, live, right now."

## 8. Honest close (15-20s)

> "What you haven't seen us do anywhere in this demo: fake a value, mock
> a check, or hide a gap behind a green checkmark. Where we can't verify
> something for real, we say so, and why. That discipline is the product."

---

## Notes for narration takes

- Say "verified" only for the five LIVE capabilities. Say "self-declared"
  or "awaiting credentials" for everything else — precision here is the
  entire pitch, don't blur it under recording pressure.
- If asked live (or in a Q&A cut) why Udyam/EPFO/ESIC/ITR aren't fully
  live: lead with "we checked, not assumed" — Sandbox.co.in confirmed not
  to offer Udyam, a second vendor (Attestr) does and is wired in pending
  credentials; EPFO/ESIC have no lawful API anywhere; ITR needs real
  government ERI registration, a legal process, not a credential.
- Collusion detection exists and is real, but as students without a
  second real consenting bidder sharing a genuine attribute, it hasn't
  fired on real data yet — say that plainly if it comes up, don't dodge
  it. It's a completeness gap in the demo data, not the engineering.
