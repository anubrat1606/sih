# /data

This folder intentionally starts empty.

Put real, consented documents and real bidder identity details here as you
collect them from your team/family/willing volunteers -- for example:

```
/data/consented_bidders/bidder_A/pan.jpg
/data/consented_bidders/bidder_A/details.json   (director_name, address, phone, bank_account)
/data/consented_bidders/bidder_B/pan.jpg
/data/consented_bidders/bidder_B/details.json
```

Nothing in this repository generates or ships synthetic bidder data --
see the conversation notes and the prompt file
(`SIH26100_CodeEditor_Prompts.md`) for why, and for how to pick two real,
consenting entities that genuinely share an attribute (address/phone/etc.)
for the collusion-detection demo case.

Do not commit real PAN/GST/Aadhaar-linked documents or personal details to
a public GitHub repo -- keep this folder in `.gitignore` (already set up)
and share it within the team through a private channel instead.
