# Remote Deployment Runbook — Signal Pipeline v2

**Commit:** `d7fbe09`  
**Branch:** `main`  
**Date:** 2026-05-17

Run every step in order. If any step fails, **stop and fix before continuing**.

---

## What this deployment includes

- Signal-centric v2 enrichment pipeline (6 parallel signal agents, deterministic scoring, Haiku explanation)
- New DB tables: `lead_signals`, `signal_cache`; new columns on `lead_scores`
- Updated lead import format: Name · Customer Name · Customer Email · Named Acct · Success Experience · Country Region
- Feature flag `USE_SIGNAL_PIPELINE=true` to route new leads to v2 (v1 preserved unchanged)
- Frontend Scoring tab shows per-signal evidence from `signal_breakdown`

---

## Step 1 — Pull the latest code

```bash
cd /path/to/sales-outreach-platform
git pull origin main
```

Expected: fast-forward to `d7fbe09`, 32 files changed.

---

## Step 2 — Set the feature flag

Add or update in your `.env` (or server environment / Docker secrets):

```
USE_SIGNAL_PIPELINE=true
```

If you use a `docker-compose.override.yml` or environment block in the compose file, add it there too.

---

## Step 3 — Run the database migration

Creates two new tables (`lead_signals`, `signal_cache`) and adds three columns to `lead_scores` (`signal_breakdown`, `pipeline_version`, `scored_at`).

```bash
docker compose exec api alembic upgrade head
```

Expected output ending with:
```
Running upgrade f1a2b3c4d5e6 -> a1b2c3d4e5f6, add_signal_tables
```

> If the `api` container is not running yet, complete step 4 first, then run this step.

---

## Step 4 — Rebuild Docker images

```bash
docker compose build api celery-worker celery-beat frontend
```

Bakes in all new Python modules (`signals/`, `scoring_engine.py`, `signal_tasks.py`, `signal_cache.py`, etc.) and the updated Next.js frontend.

---

## Step 5 — Restart all affected services

```bash
docker compose up -d api celery-worker celery-beat frontend
```

| Service | Why |
|---|---|
| `api` | Picks up `use_signal_pipeline=True`; serves `signal_breakdown` in score responses |
| `celery-worker` | Must auto-discover `run_signal_pipeline` task registered in `celery_app.py` |
| `celery-beat` | Picks up refreshed app module (same image as worker) |
| `frontend` | Serves updated Scoring tab with per-signal evidence bars |

---

## Step 6 — Verify containers are healthy

```bash
docker compose ps
```

All services should show `Up` / `healthy`. Then check logs:

```bash
docker compose logs api --tail 30
docker compose logs celery-worker --tail 30
```

**Look for:** no `ModuleNotFoundError`, no `ImportError`. Worker log should register `run_signal_pipeline` without errors.

---

## Step 7 — Smoke-test the config

```bash
docker compose exec api python -c "
from app.config import get_settings
s = get_settings()
print('use_signal_pipeline:', s.use_signal_pipeline)
"
```

Expected: `use_signal_pipeline: True`

```bash
docker compose exec api python -c "
from app.models.lead import LeadSignal, SignalCache
print('Models OK')
"
```

Expected: `Models OK`

---

## Step 8 — End-to-end smoke test

Upload a small XLSX with the new columns via the UI:

```
Name | Customer Name | Customer Email | Named Acct | Success Experience | Country Region
```

Then watch the worker log:

```bash
docker compose logs celery-worker -f | grep -E "signal|score|pipeline"
```

You should see the 6 signal agents fire and a `LeadScore(pipeline_version=v2)` persisted. The lead detail Scoring tab will show per-signal evidence bars.

---

## Rollback (if needed)

To revert to v1 without touching the DB:

1. Set `USE_SIGNAL_PIPELINE=false` in `.env`
2. `docker compose up -d api celery-worker celery-beat`

The v1 `run_enrichment_pipeline` task is unchanged and will resume immediately. The `lead_signals` / `signal_cache` tables are inert when v2 is disabled.

To fully revert the DB migration:

```bash
docker compose exec api alembic downgrade f1a2b3c4d5e6
```
