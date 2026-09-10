# CLAUDE.md — SIH26100

Context for Claude Code. Read this first, then `docs/STATUS.md` for what to work on next.

## What this is

**SIH26100 — AI-powered bid compliance verification platform** for GeM (the
Government e-Marketplace). A procurement officer uploads a bidder's registration
documents (PAN / GST / Udyam / EPFO); the system extracts the IDs by OCR,
verifies each against a real external source, checks the tender's bidders for
collusion (shared director / address / phone / bank account), produces a
compliance score + risk level, and records QUALIFY/DISQUALIFY decisions in a
hash-chained tamper-evident audit log.

This is a hackathon prototype scaffold. Every service is individually built and
smoke-tested. It has **never been run end to end as a full stack** — doing that
is the top priority (see `docs/STATUS.md`).

## Non-negotiable principle: no fabricated data

There is **no mock, sample, sandbox, or placeholder data anywhere in this
codebase, on purpose.** Every value a service returns either came from a real
operation (real OCR, a real external API call) or is explicitly:

- `null` with confidence `0` (extraction couldn't read the field), or
- status `UNVERIFIED` with the actual error in `details` (a live check failed,
  timed out, wasn't configured, or the field was missing).

`UNVERIFIED` **never** means "not implemented yet" and must never be used to
paper over a guessed value. When you can't do something for real, say so in the
response and leave it unverified. This is a deliberate design stance and a
selling point for judges — do not "helpfully" add fallback/demo values.

## Architecture

Monorepo. Five runnable pieces, each owned by one teammate:

| Path | Stack | Port | Role |
|---|---|---|---|
| `services/extraction` | Python / FastAPI, pytesseract | 8001 | `POST /extract` — real OCR on the uploaded image, regex out the ID number |
| `services/verification` | Python / FastAPI, requests | 8002 | `POST /verify` — one live external check per extracted field, compute `sub_score` |
| `services/collusion` | Python / FastAPI, networkx | 8003 | `POST /bidders`, `GET /collusion/{id}`, `GET /graph/{tender_id}` — in-memory graph, edges = shared attribute |
| `backend` | Node / Express / Mongoose | 4000 | Orchestrator only. Calls the three Python services, stores results in MongoDB, owns the hash-chained audit log. No AI/verification logic of its own. |
| `frontend` | React 19 / Vite 8 / react-router 7 | 5173 | Officer UI: `/upload` → `/dashboard/:tenderId` → `/bidder/:bidderId` (score, evidence trail, collusion force-graph, audit log) |

Data flow: frontend → backend → (extraction, then verification + collusion) →
Mongo → frontend reads back the stored `final_score`.

MongoDB: `mongodb://localhost:27017/sih26100` by default. The backend boots even
if Mongo is down (so `/health` works) but every DB route fails until it's up.

## The schema contract — `/schemas/*.json`

Five JSON Schema (draft-07) files define every payload that crosses a service
boundary:

- `extraction_output.schema.json` — extraction service response; also the
  `/verify` request body
- `verification_result.schema.json` — `{ bidder_id, checks[], sub_score }`
- `collusion_result.schema.json` — `{ bidder_id, tender_id, flagged, cluster_id, shared_with[] }`
- `final_score.schema.json` — what the backend stores and the frontend renders
- `audit_log_entry.schema.json` — one hash-chained decision record

**Do not add, rename, or remove fields in these schemas or in any payload that
must match them.** If a change seems necessary, stop and ask. `matched_against`
is one of `LIVE_KYC_PROVIDER | GST_PUBLIC_PORTAL | EPFO_PUBLIC_PORTAL |
UDYAM_PUBLIC_PORTAL`; check status is one of `PASS | FAIL | MISMATCH |
UNVERIFIED`.

Confirmed extraction regexes (in `services/extraction/main.py`) — do not invent
new ones:

- PAN: `[A-Z]{5}[0-9]{4}[A-Z]{1}`
- GST: `[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}`
- UDYAM: `UDYAM-[A-Z]{2}-[0-9]{2}-[0-9]{7}`
- EPFO establishment code: **format not confirmed — no regex.** `epfo_number`
  stays `null` until a real format is verified. Ask before adding one.

## Current real-vs-stub status

- **Collusion** — complete and correct. Leave it alone unless adding persistence.
- **Extraction** — real OCR works. Name extraction is a weak line-below-label
  heuristic. `date_of_issue` / `date_of_expiry` are never populated. EPFO regex missing.
- **Backend** — complete. Audit log is insert-only (no update/delete route
  exists). Averages `sub_score` across a bidder's documents.
- **Frontend** — builds clean (`npm run build`). Never run against a live
  backend.
- **Verification** — the weak point. GST/EPFO calls target unconfirmed gov
  portal URLs that are CAPTCHA-walled and have no public API; they currently
  always return `UNVERIFIED`. Udyam is deliberately omitted. PAN needs a real
  KYC provider sandbox key in `services/verification/.env` or it returns
  `UNVERIFIED`. **Decide the verification data-source strategy before building
  more here** — see `docs/STATUS.md`.

## Running locally

```bash
# Each service in its own terminal.

cd services/extraction
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/uvicorn main:app --port 8001

cd services/collusion
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/uvicorn main:app --port 8003

cd services/verification
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env          # fill in real PAN KYC provider credentials
./venv/bin/uvicorn main:app --port 8002

cd backend
npm install && cp .env.example .env
npm start                     # needs MongoDB on :27017

cd frontend
npm install && npm run dev     # http://localhost:5173
```

End-to-end smoke test: fill in real values at the top of `scripts/e2e_test.js`
(tender id, three bidders — two genuinely sharing an attribute — and real
document image paths), then `node scripts/e2e_test.js` with the full stack up.

## Working conventions

- Stay inside the service folder you're changing. The five pieces have separate
  owners; don't refactor across boundaries without asking.
- Use exactly the schema field names. No added fields.
- If a name, endpoint, library, or version isn't already established here, ask —
  don't guess or invent one.
- Don't add authentication, a logging framework, or dependencies that weren't
  asked for.
- Tesseract must be installed on the system for the extraction service.
- Secrets go in `.env` (gitignored). `.env.example` files hold only key names.
- After a change, say which files changed and give one command to verify it.

## Gotchas

- `backend` `/bidders/:bidderId/verify` only registers a bidder in the collusion
  graph when **all four** of `director_name`, `address`, `phone`,
  `bank_account` are present in the request body. Missing one → the bidder is
  never added → collusion silently never fires.
- Collusion graph is in-memory per process — restarting the service wipes it.
- `git`: the local main-line branch may be `master`; the GitHub default branch
  is `main`. Push with `git push origin HEAD:main` or align the names.
