# Demo script — screen recording + voiceover

For the YT submission video. Target ~5-6 minutes (Tender Intelligence's
real processing time, section 7, adds a genuine ~90s on its own). Every
number and screen below was checked live against the real deployment on
2026-09-30 — if it's been a while, spot-check the live numbers before
recording (`GET /capabilities`, the BHEL tender's bidder list) since they
can genuinely change as more real data gets added.

**Before you hit record**: open `https://sih26100-orchestrator.onrender.com/health`
once to wake the free-tier instance from cold-start — the first real
request after inactivity takes a couple of seconds, which reads as a
stall on camera if it happens mid-recording instead.

**On retakes of section 7 (Tender Intelligence)**: that call genuinely
uses real Groq quota; if you re-record it more than once or twice in
close succession, later attempts may return fewer proposals (a real,
honestly-reported rate-limit effect, not a bug) since the free tier's
per-minute budget is shared across attempts. Leave a minute or two
between takes of that section specifically if you need more than one.

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

## 7. Tender Intelligence — a real, large document (60-100s of real wait, shown honestly)

Open the tender detail page for `BHEL-T7J1Z68239` and click "Read
requirements from PDF" (Tender Intelligence's decompose action) against
its real source document — a genuine 71-page GeM tender PDF.

> "This tender's own source document is real and large — 71 pages. We
> deliberately don't hide that from you: watch what happens."

Let it actually run on camera. Confirmed live, 2026-09-30: it takes
roughly 60-100 seconds and returns real, honest results — **34 real
proposed requirements** extracted from the actual document text (e.g.
"the bidder should not have been under suspension for business or
blacklisted", "the cyclic life of the expansion bellows shall be a
minimum of 10,000 cycles", "material test certificates for both chemical
and mechanical as per code requirements"), plus a plain note that some
page ranges couldn't be analyzed within the free tier's rate limit for
this round.

> "Thirty-four real candidate requirements, pulled straight from the
> tender's own language — real weld standards, real inspection
> requirements, a real blacklist check. Some page ranges didn't make it
> into this run — a free-tier rate limit on the model we're using, named
> honestly right here, not hidden. Every one of these is still just a
> proposal: an officer reviews and re-enters each one by hand before it
> ever becomes a real requirement. No model gets a path around that."

*(This segment is a genuine live wait, not padding — plan the cut/voiceover
around it rather than trying to hide it. It is also the demo's second
strongest honesty moment after the capabilities screen: showing a real
scale limit, named plainly, mid-feature, is a harder thing for a judge to
distrust than a suspiciously instant result would be.)*

## 8. Audit log (20-30s)

Open the audit trail / `/audit/verify`.

> "Every action — every extraction, every verification call, every
> decision — is a real, hash-chained event. Each event's hash includes
> the one before it, so tampering with history breaks the chain visibly.
> This isn't a claim — it's independently re-verifiable, live, right now."

## 9. Honest close (15-20s)

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
