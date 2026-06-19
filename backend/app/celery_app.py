"""
Celery application configuration.

Defines the Celery app, task routing, rate limits, and beat schedule.
"""

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "outreachai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,

    # Result backend
    result_expires=3600,

    # Task routing – separate queues for different workload types
    task_routes={
        "app.tasks.enrichment_tasks.*": {"queue": "enrichment"},
        "app.tasks.signal_tasks.*":     {"queue": "enrichment"},
        "app.tasks.v3.*":               {"queue": "enrichment"},
        "app.tasks.email_tasks.*":      {"queue": "email"},
        "app.tasks.campaign_tasks.*":   {"queue": "campaign"},
        "app.tasks.ai_tasks.*":         {"queue": "ai"},
        "app.tasks.orchestrator_tasks.*": {"queue": "ai"},
        "app.tasks.import_tasks.*":     {"queue": "default"},
    },

    # Rate limits per task
    task_annotations={
        "app.tasks.email_tasks.send_email": {"rate_limit": "2/s"},
        "app.tasks.enrichment_tasks.run_enrichment": {"rate_limit": "5/s"},
        "app.tasks.ai_tasks.generate_personalization": {"rate_limit": "10/s"},
    },

    # Beat schedule – periodic tasks
    beat_schedule={
        "process-follow-ups": {
            "task": "app.tasks.campaign_tasks.process_follow_ups",
            "schedule": crontab(minute="*"),  # every minute
        },
        "check-replies": {
            "task": "app.tasks.email_tasks.check_replies",
            "schedule": crontab(minute="*/2"),
        },
        "sender-health-check": {
            "task": "app.tasks.email_tasks.check_sender_health",
            "schedule": crontab(minute=0, hour="*/4"),
        },
        "reset-daily-send-counts": {
            "task": "app.tasks.email_tasks.reset_daily_counts",
            "schedule": crontab(minute=0, hour=0),
        },
        "refresh-materialized-views": {
            "task": "app.tasks.analytics_tasks.refresh_views",
            "schedule": crontab(minute="*/15"),
        },
        "cleanup-old-events": {
            "task": "app.tasks.maintenance_tasks.cleanup_events",
            "schedule": crontab(minute=0, hour=2),
        },
        # ── E2E Automation Loop ──────────────────────────────────────────────
        # Fires daily at 14:00 UTC (9 AM ET). The task itself checks the toggle
        # and day-of-week guard so it's safe to schedule every day.
        "e2e-automation-loop": {
            "task": "app.tasks.orchestrator_tasks.run_automation_loop",
            "schedule": crontab(minute=0, hour=14),
        },
        # System health check every 4 hours (offset 30 min to avoid clash)
        "system-health-monitor": {
            "task": "app.tasks.orchestrator_tasks.run_health_monitor",
            "schedule": crontab(minute=30, hour="*/4"),
        },
        # Weekly performance digest — Monday 08:00 UTC
        "weekly-performance-analysis": {
            "task": "app.tasks.orchestrator_tasks.run_performance_analysis",
            "schedule": crontab(minute=0, hour=8, day_of_week="monday"),
        },
    },
)

# Explicitly import task modules so they register with the Celery app
import app.tasks.enrichment_tasks   # noqa: F401
import app.tasks.signal_tasks       # noqa: F401
import app.tasks.v3.stage_tasks     # noqa: F401
import app.tasks.campaign_tasks     # noqa: F401
import app.tasks.email_tasks        # noqa: F401
import app.tasks.orchestrator_tasks # noqa: F401
