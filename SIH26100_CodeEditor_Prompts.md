# SIH26100 — Code Editor Prompts, Split Into Bits

How to use this file: paste **BIT 0** first, in a shared session, before anyone splits up — it creates the schemas every other bit depends on. After that, each team member opens their own service folder in their own editor session and pastes only their bit. Do not paste two bits into the same session back to back without testing the first one — that's exactly the situation where the model starts inventing things to reconcile inconsistent context.

Before every bit, paste this preamble once at the top of the session (most editors let you pin it as a system/rules message — do that if available, so you don't retype it):

```
Rules for this session:
- Only create or edit files inside the folder I specify below. Do not touch anything outside it.
- Use exactly the JSON schema I give you. Do not add, rename, or remove fields.
- If a name, endpoint, library, or version isn't given below, ask me — do not guess or invent one.
- Do not add authentication, logging frameworks, or extra dependencies I didn't ask for.
- After you finish, list every file you created or changed and give me one command to run to verify it works.
- If something in this prompt is ambiguous, stop and ask before writing code.
```

---

## BIT 0 — Project scaffold and shared schemas (do this together, first)

```
Create a monorepo with this exact folder structure and nothing more:

/services/extraction        (Python FastAPI)
/services/verification      (Python FastAPI)
/services/collusion         (Python FastAPI)
/backend                    (Node.js + Express)
/frontend                   (React, created with Vite)
/schemas                    (shared JSON schema files, no code)
/data                       (synthetic bidder dataset, JSON files)

Inside /schemas, create these four files, each containing exactly the JSON structure below as a JSON Schema (draft-07). Do not add extra fields or change field names.

extraction_output.schema.json:
{
  "bidder_id": "string",
  "document_type": "PAN | GST | UDYAM | EPFO",
  "extracted_fields": {
    "pan_number": "string or null",
    "name": "string or null",
    "gstin": "string or null",
    "udyam_number": "string or null",
    "epfo_number": "string or null",
    "date_of_issue": "string or null (ISO 8601)",
    "date_of_expiry": "string or null (ISO 8601)"
  },
  "confidence": { "<field_name>": "number 0-1" },
  "raw_ocr_text": "string",
  "source_s3_key": "string"
}

verification_result.schema.json:
{
  "bidder_id": "string",
  "checks": [
    {
      "field": "string",
      "value_extracted": "string",
      "matched_against": "LIVE_KYC_PROVIDER | GST_PUBLIC_PORTAL | EPFO_PUBLIC_PORTAL | UDYAM_PUBLIC_PORTAL",
      "status": "PASS | FAIL | MISMATCH | UNVERIFIED",
      "confidence": "number 0-1",
      "details": "string"
    }
  ],
  "sub_score": "number 0-100"
}

Note: every matched_against value here is a real, live external source. UNVERIFIED means the live call failed or the field couldn't be extracted — it is never used to mean "not implemented" or to hide a fabricated value. There is no mock/sandbox status in this schema on purpose.

collusion_result.schema.json:
{
  "bidder_id": "string",
  "tender_id": "string",
  "flagged": "boolean",
  "cluster_id": "string or null",
  "shared_with": [
    {
      "bidder_id": "string",
      "shared_attribute": "director_name | address | phone | bank_account",
      "value": "string"
    }
  ]
}

final_score.schema.json:
{
  "bidder_id": "string",
  "tender_id": "string",
  "compliance_score": "number 0-100",
  "risk_level": "LOW | MEDIUM | HIGH",
  "verification_breakdown": "array, same shape as verification_result.checks",
  "collusion_flag": "object, same shape as collusion_result",
  "ai_recommendation": "string",
  "timestamp": "string (ISO 8601)"
}

audit_log_entry.schema.json:
{
  "entry_id": "string",
  "prev_hash": "string",
  "hash": "string",
  "bidder_id": "string",
  "tender_id": "string",
  "officer_id": "string",
  "decision": "QUALIFY | DISQUALIFY",
  "score_snapshot": "object, same shape as final_score",
  "timestamp": "string (ISO 8601)"
}

Also create a root README.md listing these five folders and one sentence each on what runs where. Do not write any implementation code yet — this bit only creates folders, schema files, and the README.
```

---

## BIT 1 — Extraction service (owner: OCR/extraction person)

```
Work only inside /services/extraction. This is a Python FastAPI service.

Read /schemas/extraction_output.schema.json — every response from this service must match it exactly.

Build one endpoint: POST /extract, accepting a multipart file upload plus a document_type field (PAN, GST, UDYAM, or EPFO).

For every document_type, run real OCR using pytesseract (assume Tesseract is installed on the system) on the uploaded image — do not use any placeholder, sample, or pre-filled response for any document type, there is no mock data anywhere in this service.

Extract the identifying number using these exact regexes, and only these — do not invent a regex for one I haven't given you:
- PAN: [A-Z]{5}[0-9]{4}[A-Z]{1}
- GST: [0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}
- UDYAM: UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}
- EPFO establishment code: I have not confirmed a single format for this — ask me for it rather than guessing, or leave epfo_number null until I provide it.

Extract name as the next non-empty line of OCR text below the relevant number's label, where applicable.

If a regex does not match the OCR text, set that field to null and its confidence to 0 — never fabricate a plausible-looking value to fill the response. If the regex does match, set confidence to 0.9.

Store the uploaded file locally under /services/extraction/uploads/<bidder_id>/<filename> and put that path in source_s3_key — do not implement actual S3 upload in this bit, a local path is fine for now.

Do not add a database. Do not add authentication. Do not create any file under /data/sandbox_samples or similar — this service produces only real OCR output. Give me the exact pip install command and the exact uvicorn command to run this.
```

---

## BIT 2 — Verification and scoring service (owner: verification/API-integration person)

```
Work only inside /services/verification. This is a Python FastAPI service.

Read /schemas/verification_result.schema.json and /schemas/final_score.schema.json — every response must match these exactly.

Build one endpoint: POST /verify, accepting a body matching /schemas/extraction_output.schema.json.

Every check below must call a real, live external source. If a field in the input is null, or a live call fails or times out, set that check's status to UNVERIFIED — never fabricate a PASS, a FAIL, or a plausible-looking value to fill a gap.

pan_number: call [NAME THE LIVE KYC PROVIDER'S SANDBOX ENDPOINT AND AUTH METHOD HERE — paste it in from the provider's actual docs, do not guess]. matched_against: LIVE_KYC_PROVIDER. status PASS if the provider confirms the PAN is valid and active, FAIL otherwise.

gstin: call the GST portal's public Search Taxpayer service. [Paste the exact request method, URL, headers, and body here — inspect the real network request the page at https://services.gst.gov.in/services/searchtp makes in a browser and replicate it exactly. Do not let the model guess this request shape.] matched_against: GST_PUBLIC_PORTAL. status PASS if the portal returns an active registration matching the extracted GSTIN, FAIL if it returns cancelled/invalid, UNVERIFIED if the request itself fails.

epfo_number: call the EPFO Unified Portal's public Establishment Search. [Paste the exact request shape here after inspecting https://unifiedportal-emp.epfindia.gov.in/publicPortal/no-auth/misReport/home/loadEstSearchHome in a browser — do not guess it.] matched_against: EPFO_PUBLIC_PORTAL.

udyam_number: [Paste the confirmed public verification URL and request shape on udyamregistration.gov.in once your team has located and manually tested it — do not write this check until that URL is confirmed real. If not confirmed yet, skip this check entirely rather than faking it, and I will add it in a later prompt.] matched_against: UDYAM_PUBLIC_PORTAL.

If date_of_expiry is present and earlier than today's date, add a separate check with field "expiry" and status FAIL regardless of what the registry says.

Compute sub_score as: (number of PASS checks / total checks) * 100, rounded to the nearest integer. Checks with status UNVERIFIED count in the denominator but not the numerator — do not silently drop them from the count.

Wrap every external call in a try/except with a 5-second timeout. On failure, set that check's status to UNVERIFIED and details to the actual error message — never let one failed call crash the whole response, and never substitute a default or sample value when a call fails.

Do not add a database. Give me the exact pip install command and the exact uvicorn command to run this.
```

---

## BIT 3 — Collusion graph service (owner: graph person)

```
Work only inside /services/collusion. This is a Python FastAPI service using networkx — do not use Neo4j for this build.

Read /schemas/collusion_result.schema.json — every response must match it exactly.

Maintain an in-memory networkx graph for the lifetime of the process (no database in this bit). Build two endpoints:

POST /bidders — accepts { "bidder_id": string, "tender_id": string, "director_name": string, "address": string, "phone": string, "bank_account": string }. Adds this bidder as a node. For every existing bidder in the same tender_id, if any of director_name, address, phone, or bank_account match exactly (case-insensitive, whitespace-trimmed), add an edge between them labeled with which attribute matched.

GET /collusion/{bidder_id} — returns collusion_result.schema.json for that bidder. flagged is true if the bidder's node has degree >= 1. cluster_id is a stable string identifier for the connected component the bidder belongs to (e.g. "cluster_" plus the sorted, joined bidder_ids in that component). shared_with lists every neighboring bidder and which attribute matched.

Also build GET /graph/{tender_id} returning the full graph for that tender as { "nodes": [...bidder_ids], "edges": [{"from": id, "to": id, "shared_attribute": string}] } — this is for the frontend visualization, it is not part of the four schemas, keep it separate and simple.

Do not add persistence. Give me the exact pip install command and the exact uvicorn command to run this.
```

---

## BIT 4 — Node backend orchestrator (owner: backend person)

```
Work only inside /backend. This is Node.js with Express and Mongoose (MongoDB).

This service does not do any AI or verification logic itself — it only orchestrates calls to the three Python services and stores results. The three services run at these URLs [paste the actual local ports each teammate's service is running on, e.g. http://localhost:8001 for extraction, 8002 for verification, 8003 for collusion — do not let the model guess ports].

Build these endpoints:

POST /bidders/:bidderId/documents — accepts a file upload, forwards it to the extraction service's /extract endpoint, stores the returned extraction_output in MongoDB in a collection called extractions, keyed by bidder_id.

POST /bidders/:bidderId/verify — takes the stored extraction_output for this bidder, forwards it to the verification service's /verify endpoint, stores the returned final_score in MongoDB in a collection called scores. Also forwards the bidder's identifying fields to the collusion service's POST /bidders endpoint, then calls GET /collusion/:bidderId on the collusion service and merges that into the stored final_score's collusion_flag field before saving.

GET /bidders/:bidderId — returns the stored extraction_output and final_score for one bidder, matching final_score.schema.json.

GET /tenders/:tenderId/bidders — returns an array of all bidders' final_score objects for that tender.

POST /bidders/:bidderId/decision — accepts { "officer_id": string, "decision": "QUALIFY" | "DISQUALIFY" }. Create a new audit log entry matching /schemas/audit_log_entry.schema.json: prev_hash is the hash field of the most recent entry in the audit_logs collection (or "genesis" if none exists), hash is SHA-256 of (prev_hash + JSON.stringify of this entry's other fields), score_snapshot is the bidder's current final_score. Save it to a MongoDB collection called audit_logs. Never allow an update or delete on this collection — insert only.

GET /audit/:bidderId — returns all audit log entries for that bidder, in order, matching audit_log_entry.schema.json.

Use MongoDB running locally on the default port. Give me the exact npm install command and the exact command to run this.
```

---

## BIT 5 — React frontend: upload flow and officer dashboard shell (owner: frontend person 1)

```
Work only inside /frontend. This is React, built with Vite, using plain fetch for API calls — do not add a state management library, this app is small enough not to need one.

The backend runs at http://localhost:[paste the actual port] — do not guess this.

Build three routes using react-router:

/upload — a form where a bidder enters a bidder_id and tender_id, picks a document_type from a dropdown (PAN, GST, UDYAM, EPFO), and uploads a file. On submit, POST to /bidders/:bidderId/documents, then POST to /bidders/:bidderId/verify, then redirect to /dashboard/:tenderId.

/dashboard/:tenderId — fetches GET /tenders/:tenderId/bidders and renders one card per bidder showing bidder_id, compliance_score, and risk_level (color-coded: LOW green, MEDIUM amber, HIGH red). Each card is clickable and links to /bidder/:bidderId.

/bidder/:bidderId — fetches GET /bidders/:bidderId and shows the score and risk level at the top. Below that, two buttons: "Qualify" and "Disqualify", each of which POSTs to /bidders/:bidderId/decision with the appropriate decision and a hardcoded officer_id of "officer_demo" for now, then shows a confirmation message.

Keep styling minimal — plain CSS, no component library. This bit does not include the evidence trail or the collusion graph visualization, those are a separate bit. Leave a clearly marked placeholder <div> for each on the /bidder/:bidderId page.
```

---

## BIT 6 — React frontend: evidence trail and collusion graph view (owner: frontend person 2)

```
Work only inside /frontend/src. Do not modify routing or the pages built in the previous bit except to fill in the two placeholder divs on /bidder/:bidderId — ask me if you can't find them.

Evidence trail: render final_score.verification_breakdown as a list. Each row shows field, value_extracted, matched_against, status (color-coded PASS green / FAIL red / MISMATCH amber / UNVERIFIED gray), confidence as a percentage, and details in smaller text below.

Collusion graph: install react-force-graph-2d (or if unavailable, vis-network — try react-force-graph-2d first). Fetch GET /graph/:tenderId from the collusion service directly [paste its actual port]. Render nodes as circles labeled with bidder_id, colored gray normally and red if that node's bidder_id matches the current page's bidder. Render edges labeled with their shared_attribute. This should be a compact view, roughly 400px tall, embedded in the placeholder div, not a full-page graph.

Do not add filtering, zoom controls, or animation beyond whatever the library gives you by default — keep this to what's needed for the demo.
```

---

## BIT 7 — Integration test (whole team, end of day 2 / start of day 3)

```
I have five running services: extraction (port ___), verification (port ___), collusion (port ___), backend (port ___), frontend (port ___). [Fill in actual ports before pasting.]

Write a single Node.js script at /scripts/e2e_test.js, using plain fetch, that:
1. Registers three real bidders in the same tender_id — these correspond to real people/businesses who've consented to be used in this demo, with real document numbers, not invented ones. Bidder A and bidder B genuinely share a phone number or address (e.g. two real registrations belonging to the same family/individual); bidder C is unrelated. [Fill in the three real bidder_ids, tender_id, and their real shared attribute before running.]
2. Uploads a real PAN document image for each (paths to be provided by me — real scanned/photographed documents, not sample images) via POST /bidders/:bidderId/documents.
3. Calls POST /bidders/:bidderId/verify for each.
4. Fetches GET /tenders/:tenderId/bidders and prints each bidder's score, risk level, and whether they were flagged for collusion.
5. Asserts that bidder A and bidder B are both flagged and reference each other, and that bidder C is not flagged.
6. Calls POST /bidders/:bidderId/decision to disqualify bidder A, then fetches GET /audit/:bidderId and asserts exactly one entry exists with the correct hash chain (prev_hash is "genesis").

Print PASS or FAIL for each assertion clearly. Do not modify any of the five services — if something doesn't work, tell me which service and endpoint failed rather than working around it.
```

---

## Notes on the parts you must fill in yourself

There is no mock or sample data anywhere in this build — every bracketed placeholder below exists because it points at a real external source your team has to actually go find, not something a code editor should guess:

- BIT 2 needs: the live KYC provider's real sandbox endpoint and auth format (from their docs); the exact request GST's Search Taxpayer page makes (inspect it in browser devtools, replicate it); the exact request EPFO's Establishment Search page makes (same method); and — before that check is even written — a confirmed real public verification URL on udyamregistration.gov.in. If Udyam's isn't confirmed in time, the honest move is to leave that check out of the live demo entirely and say so, not to fake it.
- BIT 4, 5, and 6 need the real local ports each service ends up running on, once BIT 1–3 are actually running.
- BIT 7 needs real bidder identities (people/businesses who've consented to appear in the demo), real document images, and the final port list.

The one deliberately unverified value the schema allows for is UNVERIFIED itself — when a live call fails or a field can't be extracted, that's the correct, honest result to show a judge. It's a stronger answer than a fabricated PASS, and it's exactly the kind of thing your original strategy note already told you to be upfront about.
