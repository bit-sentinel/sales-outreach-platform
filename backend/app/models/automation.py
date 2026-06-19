"""
Automation models – configuration, run history, and strategy insights for the E2E loop.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AutomationConfig(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """One row per tenant — stores the E2E loop settings and last run state."""

    __tablename__ = "automation_configs"

    loop_enabled: Mapped[bool] = mapped_column(Boolean, server_default="false")

    # Operational limits
    max_leads_per_run: Mapped[int] = mapped_column(Integer, server_default="10")
    max_emails_per_account_daily: Mapped[int] = mapped_column(Integer, server_default="15")

    # Comma-separated alert recipients
    alert_emails: Mapped[str] = mapped_column(
        String(500),
        server_default="snehdeep@launchhouse.events,cto@launchhouse.events",
    )

    # Last run metadata
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_summary: Mapped[dict | None] = mapped_column(JSONB)

    # Hour (UTC) at which the daily loop fires — default 14 = 9 AM ET
    run_hour_utc: Mapped[int] = mapped_column(Integer, server_default="14")

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class StrategyInsight(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Learnings produced by the weekly performance analyst — fed back into the loop."""

    __tablename__ = "strategy_insights"

    # "angle_performance" | "timing_performance" | "industry_performance" | "weekly_summary"
    insight_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    insight_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # True once the insight has been surfaced in at least one orchestrator run
    applied: Mapped[bool] = mapped_column(Boolean, server_default="false")
    summary_text: Mapped[str | None] = mapped_column(Text)


class HealthAlert(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """Persisted health alert records so the UI can show current system status."""

    __tablename__ = "health_alerts"

    component: Mapped[str] = mapped_column(String(100), nullable=False)  # sendgrid, anthropic, imap, db
    severity: Mapped[str] = mapped_column(String(20), server_default="warning")  # warning | critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, server_default="false")
    alerted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
