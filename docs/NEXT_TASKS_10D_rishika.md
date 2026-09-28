# Round 10D — Rishika: the 3 flagged tokens + the screenshot that now actually works

Your landing-audit PR (#113) is reviewed, verified (build + lint re-run
independently, both clean, matches your own claims exactly), and merged.
Real, thorough work — the honest "already compliant" findings alongside
the real fixes, and the DigiLocker stage-label treatment in
`Pipeline.jsx` was the right call, not a lazy reuse of "located · p.1".

Two things follow directly from what you found.

---

## 1. The 3 colors you correctly didn't guess at

You left these flagged rather than mechanically swapped, since none has
an exact existing-token match:

- `shell.css` — `#62a0e0` (active-border), `#8fc0f0` (focus outline)
- `login.css` — `#dbe6f3`

That was the right call in the moment, but "flagged forever" isn't a
real end state. Your task: decide what these should actually be — either
map each to the *closest* existing semantic token if one is genuinely
close enough (say why), or propose a new token (name, value, where it
lives in the token source) if none of the existing ones honestly fit.
Same discipline as everything else this round: a real design decision
with real reasoning, not a guess dressed up as one.

## 2. The screenshot you flagged as currently impossible — now works

Your finding was exactly right: no bidder on `BHEL-T7J1Z68239` had both
a real PASS and a live PDF, because Render's free-tier ephemeral storage
had silently dropped both bidders' uploaded documents after a redeploy
(`ANUBRAT-DAS`'s PAN doc, `GST-BIDDER-01`'s GST doc — both were 404ing,
confirmed independently, not just taking your word for it).

Fixed by re-uploading both bidders' same real, already-consented
documents (`data/consented_bidders/`) fresh, so they're live under the
current deploy instead of a stale one. Verified live, just now:

- **`GST-BIDDER-01`, `R1_GST` → real `PASS`, `AUTHORITY_CONFIRMED`,
  document confirmed retrievable (HTTP 200, not 404).** This is your
  shot — the actual signature moment: click the PASS badge, land on the
  real GST certificate page, see the real GST_STATUS API response beside
  it, real timestamps on both.
- `ANUBRAT-DAS`, `R2_PAN` → genuinely `PARTIAL`
  (`SELF_DECLARED_CEILING`), document also live now. Worth its own
  screenshot too, separately: this is the anti-fraud ceiling rule — a
  mandatory requirement resting on an extracted-but-not-independently-
  verified identifier can never reach a clean PASS — actually firing on
  real data, not a contrived example. That's a real differentiator worth
  showing a judge exactly as honestly as the system reports it: PARTIAL,
  not padded into a PASS.

Hash chain reconfirmed intact after both re-uploads: 185 events, all
linked, zero breaks.

Both bidders are on the real tender, real rule pack, real deployment —
no setup needed, just log in as an officer and go to
`BHEL-T7J1Z68239 → GST-BIDDER-01` (and separately `ANUBRAT-DAS`) and
capture the Evidence Graph / Provenance Trail for real this time.

---

## Rules, unchanged

Real live-browser verification before calling either done — not just
that the screenshot exists, but that it's honest (nothing clipped, no
placeholder, the real numbers visible). If the ephemeral-storage issue
recurs before you get to this (a Render redeploy between now and then
would drop the documents again), say so rather than working around it
silently — it's a known, documented limitation
(`docs/DEPLOYMENT.md`), not something to paper over.
