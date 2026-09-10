# SIH26100 — AI-Powered Bid Compliance Verification Platform

Working prototype scaffold. Every service here has been built and smoke-tested
in isolation with **real logic — no mock, sample, or sandbox-placeholder data
anywhere in the code.** Where a live external check isn't wired up yet
(Udyam; the exact GST/EPFO request shape), the code says so explicitly and
returns `UNVERIFIED` rather than a fabricated result. See
`SIH26100_CodeEditor_Prompts.md` for the reasoning and the exact prompts
used to generate each service, and for what's still open.

## What's built and verified

| Service | Port | Status |
|---|---|---|
| `services/extraction` (Python/FastAPI, real Tesseract OCR) | 8001 | Built + tested: real OCR correctly extracts a PAN from a clean image, correctly returns null on an unclear one. |
| `services/collusion` (Python/FastAPI, networkx) | 8003 | Built + tested: shared-attribute matching correctly flagged two linked bidders and cleared an unrelated one. |
| `services/verification` (Python/FastAPI) | 8002 | Built + tested for correct honest fallback behavior. Live PAN check needs a real KYC provider's credentials (see below). GST/EPFO calls are written against the portals' known public URLs but **could not be live-tested from this build environment** — its network policy blocks those domains entirely (proxy returned no response, not a real answer from the sites). Test from a normal internet connection before the demo. |
| `backend` (Node/Express + MongoDB, orchestration + hash-chained audit log) | 4000 | Built + boots correctly; degrades gracefully (logs a clear error, doesn't crash) when MongoDB isn't reachable. Needs a real local MongoDB to exercise the DB-backed routes — not available in this build sandbox either. |
| `frontend` (React/Vite: upload, dashboard, evidence trail, collusion graph) | 5173 (dev) | Builds cleanly with `npm run build`. Not yet run against a live backend end to end — do that first thing when you pick this up. |

## What's genuinely not done yet (be upfront about these, don't fake them)

- **Udyam verification**: no confirmed real public verify URL yet. Confirm one on udyamregistration.gov.in before writing this check — see `services/verification/main.py`, it's deliberately left out.
- **GST/EPFO exact request shape**: written against the portals' known URLs, but the real request (and whether a CAPTCHA blocks programmatic access) needs confirming with browser devtools on a real network. There's a `"captcha"` string-match fallback already in place that reports this honestly as `UNVERIFIED` if it happens.
- **Live PAN KYC provider**: pick one (Setu, Sandbox.co.in, Decentro, etc.), get a real sandbox key, put it in `services/verification/.env`.
- **EPFO establishment code regex**: not implemented in the extraction service — the format wasn't confirmed, so it's deliberately left as `null` rather than guessed.

## Running everything locally

```bash
# Extraction service
cd services/extraction
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/uvicorn main:app --port 8001

# Collusion service (separate terminal)
cd services/collusion
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/uvicorn main:app --port 8003

# Verification service (separate terminal)
cd services/verification
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in real PAN KYC provider credentials
./venv/bin/uvicorn main:app --port 8002

# Backend (separate terminal) -- needs MongoDB running locally
cd backend
npm install
cp .env.example .env
npm start

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Then open the frontend (usually http://localhost:5173), go to `/upload`,
and run a real document through the whole chain.

## Team ownership (matches the original 6-way split)

- `services/extraction` — OCR/extraction owner
- `services/verification` — verification/API-integration owner
- `services/collusion` — graph owner
- `backend` — backend owner
- `frontend` — the two frontend owners
- data collection, pitch, and end-to-end QA — research/pitch owner

## Before the demo

1. Confirm the Udyam verify URL and the real GST/EPFO request shape on an unrestricted network (not this build sandbox).
2. Get real PAN KYC provider credentials into `services/verification/.env`.
3. Collect real, consented documents and identity details for your demo bidders into `/data` (see `data/README.md`) — including two that genuinely share an attribute, for the collusion case.
4. Run `scripts/e2e_test.js` against the full real stack with those real bidders filled in.
5. Get MongoDB running locally (`mongodb://localhost:27017` by default) so the backend's DB-backed routes work.
