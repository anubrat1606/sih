# Contributing — Satyapramāṇa (SIH26100)

Five people push to one repository this week. This document is the whole reason
that works without a merge conflict: **each workstream owns its own
directories outright, and nobody edits anybody else's files.** If your work
seems to need a change outside your own paths, message that file's owner and
let them make it — it costs them two minutes and saves everyone an afternoon.

Read [`CLAUDE.md`](CLAUDE.md) and [`docs/satyapramana.md`](docs/satyapramana.md)
(the architecture charter) before your first change.

## Workstreams and file ownership

| Path | Owner | Rule |
|---|---|---|
| `frontend/` | Kevindeep | Sole owner |
| `services/orchestrator/satyapramana_store/adapters/` | Anubrat | Sole owner |
| `services/orchestrator/satyapramana_store/extract/` | Suhani | Sole owner |
| `services/orchestrator/satyapramana_store/reporting/` (new) | Rishika | Sole owner |
| `rulepacks/` · `data/` (new) | Paridhi | Sole owner |
| `services/orchestrator/satyapramana_store/*.py` (app, decide, rulepacks, evidence) | Anubrat | Ask before editing |
| `services/core/` | Anubrat | Frozen — the algebra is exhaustively verified; changes need review |
| `schemas/*.schema.json` | Anubrat | Frozen — these are the contract between services |
| `docs/*.md` | Shared | Append to your own workstream's section only |
| `backend/`, `services/extraction/`, `services/verification/`, `services/collusion/` | Anubrat (retiring) | Old scaffold — being replaced, don't build on it |

See the [full build plan and per-workstream detail](https://claude.ai/code/artifact/19c88304-da04-42c5-8a99-7f48adb471cd) for scope, rationale, and "done when" criteria per workstream.

## Setup

You need PostgreSQL running locally.

```bash
git clone https://github.com/anubrat1606/sih.git
cd sih
git checkout main
git pull origin main
```

Confirm the suite passes on your machine before you change anything — if it
doesn't, that's a setup problem, not your code:

```bash
# core domain logic — no database needed
cd services/core
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python -m pytest tests/ -q          # expect 182 passed

# orchestrator — needs PostgreSQL
cd ../orchestrator
python3 -m venv venv
./venv/bin/pip install -r requirements.txt -e ../core
createdb satyapramana_dev
export DATABASE_URL=postgresql://localhost/satyapramana_dev
./venv/bin/python -m pytest tests/ -q          # expect 145 passed

# start the API
export SATYAPRAMANA_MIGRATE_ON_START=1
./venv/bin/uvicorn satyapramana_store.app:app --port 4000
```

Open `http://localhost:4000/docs` for the live API, and `/capabilities` to see
exactly what the system can and cannot verify right now.

## Branch, commit, push

1. **One branch per piece of work**, named `feat/<your-name>-<topic>`. Never
   commit to `main` directly, and never push to somebody else's branch.

   ```bash
   git checkout main
   git pull origin main
   git checkout -b feat/suhani-ocr-boxes
   ```

2. **Rebase onto `main` daily, and always before you push.** Because you only
   touch your own directories, this should apply cleanly every time — if it
   doesn't, you've probably edited outside your own paths.

   ```bash
   git fetch origin
   git rebase origin/main
   ```

3. **Stage explicit paths, never the whole tree.** `git add -A` from the repo
   root is exactly how a stray edit to someone else's file gets pushed without
   anyone noticing.

   ```bash
   git add services/orchestrator/satyapramana_store/extract/
   git commit -m "Read word boxes from OCR for scanned pages"
   git status     # confirm nothing else crept in
   ```

4. **Push your branch and open a PR against `main`.** State in one line what
   changed and how to check it. Two reviewers, then it merges.

   ```bash
   git push -u origin feat/suhani-ocr-boxes
   ```

## Five rules that hold everywhere

1. **No mock, sample, or simulated data — anywhere, including tests that
   double as demos.** If a check can't be performed, it returns `UNKNOWN` with
   the real reason. A fabricated `PASS` is the one thing that sinks this
   project in front of a panel that knows the domain.
2. **No model ever makes a final determination.** Models may read, classify,
   and propose. Arithmetic, dates, thresholds, eligibility, and verdicts are
   computed by deterministic code, always.
3. **Nothing changes state except by appending an event.** If you find
   yourself writing `UPDATE` against a verdict table, stop and ask.
   Projections are rebuilt, never patched.
4. **Every change ships with a test, and the suite stays green.** 327 tests
   pass today. If your branch drops that number, it isn't ready.
5. **Secrets live in `.env`, never in a commit.** If a key ever reaches the
   archive or the event log, it cannot be removed — both are immutable by
   design.
