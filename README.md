# SATYAPRAMĀṆA (SIH26100) — AI-Powered Bid Compliance Verification Platform

Read [`CLAUDE.md`](CLAUDE.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md) first,
then [`docs/STATUS.md`](docs/STATUS.md) for exactly what's built and what's
next. This file is a map, not the source of truth — those three are, and this
one had gone stale before this pass (checked and rewritten 2026-09-28
against the real deployment, not memory — the same discipline `docs/STATUS.md`
now documents).

## Live deployment

A real instance runs continuously — nobody needs a local setup just to see
the product:

- **Officer/admin UI:** https://sih26100-frontend.onrender.com
- **Bidder portal:** same URL, `/portal` — a bidder account is separate from
  an officer account (see `CLAUDE.md`, no self-signup)
- **Backend API:** https://sih26100-orchestrator.onrender.com —
  `GET /capabilities` (needs a login token) shows the honest, current
  verification status; `GET /health` needs none
- Backed by a shared Neon Postgres, deployed via `render.yaml`; see
  `docs/DEPLOYMENT.md`

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
| `services/orchestrator` | shared, see below | FastAPI app: the event log, projections, the verification adapters, DECIDE, and reporting. PostgreSQL is the event store, the projection store, and the queue — nothing else is added. 514 tests. |
| `services/orchestrator/.../adapters` | Anubrat | Five live capabilities on one Sandbox.co.in account: `PAN_STATUS`, `GST_STATUS`, `CIN_STATUS`, `GST_RETURN_STATUS`, and `DIGILOCKER_DOCUMENT` (a real bidder-consent redirect flow, round 10). Udyam, EPFO, ESIC, and ITR are each confirmed `UNAVAILABLE` for a specific, checked reason (no aggregator offers it, no lawful source exists, or it needs a business/legal registration this deployment doesn't have) — see `docs/ADAPTERS.md` section 11. |
| `services/orchestrator/.../extract` | Suhani | Deterministic PDF-text-layer extraction (GSTIN/PAN/CIN/Udyam, PAN holder name/DOB, financial-statement turnover/net worth) — no model, structural validation, exact page/region provenance. |
| `services/orchestrator/.../reporting` | Rishika | Bid Autopsy (why a bid would fail, with a counterfactual), Compliance Repair (the actionable inverse), the Compliance Dossier, the Tender Compliance Report. |
| `frontend` | shared, see below | Real design tokens and dual theme, the evidence-native primitives from charter section 2.3, the Evidence Graph, a guided rule-pack builder, an admin console, and a real bidder self-service portal — wired against the real orchestrator API throughout, not a mock. |
| `rulepacks/` | Anubrat, Kevin | Not empty: a real, adopted rule pack against a real GeM tender (BHEL, Enquiry No. T7J1Z68239 — see `docs/STATUS.md`), plus a demo fixture pack. See `rulepacks/README.md`. |
| `data/` | Anubrat | Real, consented documents exist for two real people (`data/consented_bidders/`, gitignored) — see `docs/STATUS.md`'s outstanding-gaps section for exactly what's still needed (a genuine shared attribute between two real bidders, for the collusion case). |
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
./venv/bin/python -m pytest tests/ -q          # expect 514 passed
export SATYAPRAMANA_MIGRATE_ON_START=1
./venv/bin/uvicorn satyapramana_store.app:app --port 4000

cd ../../frontend
npm install && npm run dev     # http://localhost:5173
```

Open `http://localhost:4000/docs` for the live API and `GET /capabilities`
for the honest current verification status. `http://localhost:5173` is the
officer UI.

## What's actually still open

Checked live, not assumed — full detail and reasoning in
[`docs/STATUS.md`](docs/STATUS.md)'s "Outstanding" section:

1. **Collusion has never fired on real data.** Three real bidders exist on
   the live deployment with real evaluated verdicts, but none currently
   share a real attribute with another — needs a real, consenting person,
   not code.
2. **The Gemini key isn't configured on the live deployment** — EXPLAIN and
   Tender Intelligence both correctly degrade to unavailable there rather
   than fabricating anything, but neither has narrated a real dossier live
   yet.
3. **`EXPERIENCE`, `SIMILAR_WORK`, and `CERTIFICATION`** have no extraction
   or verification path — a real ISO-certificate API exists (IAF
   CertSearch) but needs a new paid vendor account, a cost decision, not a
   build task.
