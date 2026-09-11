# What We're Building — Simple Guide & Checklist

No jargon. This is for anyone on the team (or anyone judging this) who
wants to understand what the project does and how much of it is actually
working, without reading code. For the technical details, see `STATUS.md`.

## The problem, in one paragraph

Government tenders (like on GeM, the Government e-Marketplace) get bids
from hundreds of companies. An officer has to check every single bid
against a long list of rules — does this company have valid tax
registration, valid business registration, enough experience, no secret
connection to a rival bidder, and so on. Doing this by hand is slow, and
mistakes are easy to make and easy to challenge later ("why was my bid
rejected? prove it"). This project (sponsored by the Ministry of
Petroleum & Natural Gas, for CPCL) builds a tool that does this checking
automatically, but never hides its reasoning — every decision the system
shows can be traced back to the exact document, page, and rule that
produced it.

## The one rule that matters more than any feature

**The system is never allowed to guess.** If it can't actually check
something (no way to verify a document online, no evidence provided), it
says "I don't know" instead of quietly assuming a pass or a fail. That
rule shapes almost everything below — several things are listed as "can't
be checked automatically yet" not because nobody built them, but because
doing so honestly requires a real, working connection to a government
database that doesn't exist yet.

---

## ✅ What's built and working right now

- [x] **Officer accounts and secure login** — only authorized people can use the system, and different roles (officer / senior officer / admin) can do different things
- [x] **Create a tender** — enter its title, which department issued it, category, and important dates
- [x] **Upload the tender's own document** (the official notice/PDF)
- [x] **Upload a bidder's documents** — PAN card, GST certificate, Udyam (MSME) registration, company registration
- [x] **Automatic reading of ID numbers off those documents** — no manual typing of GSTIN/PAN/registration numbers, and it double-checks the numbers are even structurally valid (catches typos/fakes before anything else happens)
- [x] **Real, live verification** of GST registration, PAN, and company registration status against government-linked verification services — this is genuinely switched on and working today, not a placeholder
- [x] **Collusion detection** — automatically flags if two bidders on the same tender secretly share a director, address, phone number, or bank account
- [x] **Building the rulebook for a tender** — an officer can define exactly what's required (GST valid? PAN valid? MSME registered?) through a guided form, not by writing code
- [x] **AI-assisted suggestions** — the system can read a tender document and suggest candidate requirements for an officer to review (the AI never decides anything on its own — a human always approves or rejects each suggestion)
- [x] **Automatic scoring** of each bidder against the rulebook, with three separate scores (how compliant, how confident the evidence is, how much got independently verified) — kept separate on purpose, never mashed into one misleading number
- [x] **"Why did this bid fail?"** — a plain-language explanation for any bid, pointing at exactly which requirement failed and why
- [x] **"What do you need to fix it?"** — the flip side: tells a bidder exactly what document or action would cure the problem
- [x] **A visual map** connecting each requirement → the document that answers it → the verification result → the final decision, so nothing is a black box
- [x] **A permanent, tamper-evident record** of every action — nobody, including an admin, can secretly edit or delete history after the fact
- [x] **Reports** — exportable summaries and spreadsheets of how a tender's bidders are doing
- [x] **The whole thing is live on the internet right now** — every team member can open it in a browser and use the same shared system, no installation needed
- [x] **One real government tender has been loaded in** as the first real test case (a real BHEL/GeM tender for metallic expansion joints), with a real rulebook built and switched on for it

## 🚧 What's left to build or finish

- [ ] **Test the system with real bidder companies.** So far only the tender side has real data — nobody has run a real company's real documents all the way through yet. This needs 3+ real, consenting people/businesses (teammates, family, or willing volunteers), with two of them sharing something real (so the collusion detector has something genuine to catch).
- [ ] **A handful of checks still need a human, not the computer, because no official online source exists to check them automatically yet:**
  - Minimum business turnover (needs financial statements)
  - Past work experience / track record
  - Quality certifications
  - Provident Fund (EPFO) / employee insurance (ESIC) registration — confirmed: there's genuinely no lawful way to check this online today, this isn't a "haven't built it yet"
  - Signed declarations/undertakings
  
  These are captured and clearly flagged as "needs manual review" rather than pretending to check them — that's intentional, not a bug.
- [ ] **Turn on the AI-suggestion feature for real.** It works, but it needs a paid AI service key that hasn't been added yet — until then, requirements have to be typed in by an officer reading the document directly (which still works fine, just slower).
- [ ] **Run the whole thing start-to-finish with real data** — a real tender, real bidders, verification, scoring, and the collusion alarm actually firing on real (not test) data. This is the next milestone once the point above is done.
- [ ] **Put together the final demo/presentation** — walking a judge or reviewer through the working system with a real example, once there's real data to show.

---

## The short version

**Built:** the entire engine — upload, verify, score, explain, detect collusion, keep an honest permanent record, and it's live for the whole team to use today.

**Left:** feeding it real bidder data to prove the whole chain works end-to-end, and a few checks that are honestly outside what can be automated right now without more official data access.
