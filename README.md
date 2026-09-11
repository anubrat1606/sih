# SATYAPRAMĀṆA (SIH26100) — AI-Powered Bid Compliance Verification Platform

Read [`CLAUDE.md`](CLAUDE.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md) first,
then [`docs/STATUS.md`](docs/STATUS.md) for exactly what's built and what's
next. This file is a map, not the source of truth — those three are.

## What this actually is now

The prototype was rebuilt against the architecture charter in
[`docs/satyapramana.md`](docs/satyapramana.md): an append-only, hash-chained
event log; four-state verdicts (`PASS`/`FAIL`/`PARTIAL`/`UNKNOWN`, never a
boolean); three orthogonal metrics, never blended into one score; and a
verification adapter layer where a missing integration honestly reports
`UNAVAILABLE` rather than faking coverage. **No mock, sample, or
sandbox-placeholder data exists anywhere in this codebase, on purpose** — see
`CLAUDE.md`'s non-negotiable principle.

`backend/`, `services/extraction/`, `services/verification/`, and
`services/collusion/` are the **retired** first-pass scaffold, kept for
history. Don't build on them.

## What's built and where

| Path | Owner | Role |
|---|---|---|
| `services/core` | Anubrat, **frozen** | Pure domain layer — verdict algebra, the three metrics, risk classification, rule pack validation. No database, no framework. 182 tests. |
| `services/orchestrator` | shared, see below | FastAPI app: the event log, projections, the verification adapters, DECIDE, and reporting. PostgreSQL is the event store, the projection store, and the queue — nothing else is added. |
| `services/orchestrator/.../adapters` | Anubrat | Verification adapters. PAN/GST/CIN are live against Sandbox.co.in given real credentials (`services/orchestrator/.env`, gitignored); Udyam has no aggregator anywhere and EPFO/ESIC have no lawful source — both honestly `UNAVAILABLE`. |
| `services/orchestrator/.../extract` | Suhani | Deterministic PDF-text-layer extraction — no model, structural validation, exact page/region provenance. |
| `services/orchestrator/.../reporting` | Rishika | Bid Autopsy (why a bid would fail, with a counterfactual) and Compliance Repair (the actionable inverse). |
| `frontend` | Anubrat | Rebuilt against the real orchestrator API: capability status, bidder registration/upload/verify, tender dashboard, bidder detail, audit log. Minimal styling by design — the charter's design-system pass (section 2.3) hasn't happened yet. |
| `rulepacks/`, `data/` | Paridhi | Both intentionally empty — a rule pack needs a real tender to decompose, demo bidders need real consent. See each folder's README. |
| `schemas/*.schema.json` | Anubrat, **frozen** | The contract every payload crossing a service boundary must match. |

## Running everything locally

```bash
# PostgreSQL must be running.
createdb satyapramana_dev

cd services/core
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python -m pytest tests/ -q          # expect 182 passed

cd ../orchestrator
python3 -m venv venv
./venv/bin/pip install -r requirements.txt -e ../core
cp .env.example .env   # fill in real Sandbox.co.in credentials to go live; leave blank otherwise
export DATABASE_URL=postgresql://localhost/satyapramana_dev
./venv/bin/python -m pytest tests/ -q          # expect ~162 passed (179 once PAN/GST/CIN + reporting are both in)
export SATYAPRAMANA_MIGRATE_ON_START=1
./venv/bin/uvicorn satyapramana_store.app:app --port 4000

cd ../../frontend
npm install && npm run dev     # http://localhost:5173
```

Open `http://localhost:4000/docs` for the live API and `GET /capabilities`
for the honest current verification status. `http://localhost:5173` is the
officer UI.

## Before the demo

1. Get PAN holder name/DOB and CIN into extraction (`services/orchestrator/.../extract`) so PAN and CIN verification can actually fire, not just report `MALFORMED`.
2. Collect real, consented bidder documents and identity details into `/data` (see `data/README.md`) — at least three bidders on one tender, two genuinely sharing an attribute, for the collusion case.
3. Write a real rule pack against a real tender document into `/rulepacks` (see `rulepacks/README.md`); validate it locally with `rulepacks/validate.py` before adopting it via the API.
4. Run the whole path end to end with that real data: register → upload → verify → adopt rule pack → evaluate → read the dashboard and provenance trail.
