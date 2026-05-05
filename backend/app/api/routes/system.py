"""System health endpoint – checks Redis, Celery workers, and DB."""

import asyncio
import time

import redis as sync_redis
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.config import get_settings
from app.db import get_db
from app.schemas.common import APIResponse

router = APIRouter()

# Queue → human label mapping (mirrors docker-compose queues)
_QUEUE_LABELS: dict[str, str] = {
    "default":     "Import worker",
    "enrichment":  "Enrichment worker",
    "ai":          "AI worker",
    "email":       "Email worker",
    "campaign":    "Campaign worker",
}

# Cache celery inspect result — it's slow (2 s timeout) and called frequently
_worker_cache: dict = {"result": None, "ts": 0.0}
_WORKER_CACHE_TTL = 30.0  # seconds


def _check_celery_workers() -> dict:
    """
    Run celery inspect in a thread-safe way (sync redis call).
    Returns per-queue worker info and an overall health score.
    Result is cached for 30 s to avoid blocking every health request.
    """
    now = time.monotonic()
    if _worker_cache["result"] is not None and now - _worker_cache["ts"] < _WORKER_CACHE_TTL:
        return _worker_cache["result"]

    try:
        inspect = celery_app.control.inspect(timeout=1.0)
        active_queues: dict | None = inspect.active_queues()

        if not active_queues:
            result = {
                "online": False,
                "worker_count": 0,
                "queues": {q: {"online": False, "workers": 0, "label": lbl} for q, lbl in _QUEUE_LABELS.items()},
            }
        else:
            queue_workers: dict[str, int] = {q: 0 for q in _QUEUE_LABELS}
            for _worker_name, queues in active_queues.items():
                for q in queues:
                    name = q.get("name", "")
                    if name in queue_workers:
                        queue_workers[name] += 1

            total_workers = sum(queue_workers.values())
            result = {
                "online": total_workers > 0,
                "worker_count": total_workers,
                "queues": {
                    q: {"online": queue_workers[q] > 0, "workers": queue_workers[q], "label": label}
                    for q, label in _QUEUE_LABELS.items()
                },
            }
    except Exception:
        result = {
            "online": False,
            "worker_count": 0,
            "queues": {
                q: {"online": False, "workers": 0, "label": label}
                for q, label in _QUEUE_LABELS.items()
            },
        }

    _worker_cache["result"] = result
    _worker_cache["ts"] = now
    return result


@router.get("/health")
async def system_health(db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    start = time.monotonic()

    # ── 1. Database ─────────────────────────────────────
    db_ok = False
    try:
        await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=2.0)
        db_ok = True
    except Exception:
        pass

    # ── 2. Redis ─────────────────────────────────────────
    redis_ok = False
    redis_latency_ms: float | None = None
    try:
        r = sync_redis.from_url(str(settings.redis_url), socket_connect_timeout=1)
        t0 = time.monotonic()
        redis_ok = r.ping()
        redis_latency_ms = round((time.monotonic() - t0) * 1000, 1)
        r.close()
    except Exception:
        pass

    # ── 3. Celery workers (cached blocking inspect) ──────
    workers = await asyncio.get_event_loop().run_in_executor(None, _check_celery_workers)

    # ── 4. Compute overall health score (0–100) ─────────
    score = 0
    if db_ok:
        score += 25
    if redis_ok:
        score += 25
    if workers["online"]:
        queues_online = sum(1 for q in workers["queues"].values() if q["online"])
        total_queues = len(_QUEUE_LABELS)
        score += int(50 * queues_online / total_queues)

    elapsed_ms = round((time.monotonic() - start) * 1000, 1)

    return APIResponse(data={
        "score": score,
        "status": "healthy" if score >= 75 else "degraded" if score >= 40 else "unhealthy",
        "latency_ms": elapsed_ms,
        "components": {
            "database": {"online": db_ok},
            "redis": {"online": redis_ok, "latency_ms": redis_latency_ms},
            "workers": workers,
        },
    })
