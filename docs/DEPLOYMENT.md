# Deployment — one reachable deployment, no Docker

Decided 2026-09-12, alongside the Docker decline and the shared Neon
database (`STATUS.md`). This is the actual fix for "my network/machine
can't run the stack" that Docker was originally proposed for: instead of
everyone needing a working local Postgres and Docker daemon, the whole
app runs once, on Render, reachable over HTTPS from anywhere.

## What's live

`render.yaml` at the repo root is a Render Blueprint defining two free
services:

- **`sih26100-orchestrator`** — the FastAPI app, run directly with
  `uvicorn` (no container). Applies every SQL migration automatically on
  boot (`SATYAPRAMANA_MIGRATE_ON_START=1`, the same flag `CONTRIBUTING.md`
  already documents for local dev) against the shared Neon database.
- **`sih26100-frontend`** — the Vite build, served as a static site.

## One-time setup (whoever does this first)

1. Render dashboard -> **New** -> **Blueprint** -> connect the
   `anubrat1606/sih` GitHub repo. Render reads `render.yaml` and proposes
   both services.
2. When prompted for the env vars marked `sync: false` in `render.yaml`:
   - `DATABASE_URL` on the orchestrator service — the team's shared Neon
     connection string (ask Anubrat, shared over a private channel, never
     committed).
   - `SATYAPRAMANA_BOOTSTRAP_ADMIN_USERNAME` / `_PASSWORD` — pick a shared
     team login; whoever deploys first has it bootstrap into the shared
     database, everyone else just logs in with it afterward.
   - `SATYAPRAMANA_SANDBOX_API_KEY` / `_SECRET` / `_ENV`, and
     `SATYAPRAMANA_GEMINI_API_KEY` — optional. Leave unset and the
     dependent features honestly report unavailable rather than faking a
     result; fill in later if/when the team has real credentials to share.
   - `SATYAPRAMANA_JWT_SECRET` needs nothing from you — Render generates it.
3. Deploy. Render builds both services and gives each a URL, normally
   `https://sih26100-orchestrator.onrender.com` and
   `https://sih26100-frontend.onrender.com` — exactly what `render.yaml`
   already cross-references each service with. **If Render had to pick
   different names** (yours were taken), edit the two hardcoded URLs in
   `render.yaml` to match what it actually assigned, commit, and redeploy.
4. Open the frontend URL. Sign in with the bootstrap admin login from
   step 2.

## What everyone else does

Nothing to install. Open the frontend URL in a browser. That's the whole
setup — no `.env`, no local Postgres, no venv, no npm install, unless
you're actually changing code (see `CONTRIBUTING.md`).

## The one real limitation — stated plainly, not hidden

Render's free tier has **no persistent disk**. Every real, hash-chained
event lives safely in Neon regardless of this — the audit log, tenders,
bidders, verdicts, all of it survive a redeploy. But an uploaded
**document file itself** (a bidder's PAN/GST PDF, a tender notice) is
written to local disk (`SATYAPRAMANA_DOCUMENT_DIR`, default `documents/`)
and is lost on the next deploy or restart. `GET /documents/{sha256}`
would then honestly 404 for a document uploaded before the last restart,
even though the event log still correctly shows it was once ingested.

This is a genuine, known gap, not a bug to silently work around:
re-upload documents after a redeploy if you need to view them again, and
don't treat this deployment as a permanent document store yet. If it
becomes a real blocker, the fix is a Render persistent Disk (a paid
add-on) or S3-compatible object storage — worth deciding only once it
actually matters, not speculatively now.

## Free-tier cold starts

Render's free web services spin down after 15 minutes idle and take
~30-50 seconds to wake back up on the next request. Not a bug — just
expect the first request after a break to be slow.
