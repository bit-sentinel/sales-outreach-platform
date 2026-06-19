"""Add automation_configs, strategy_insights, and health_alerts tables.

Revision ID: e3f4a5b6c7d8
Revises: 2f516ea3e0b8
Create Date: 2026-06-18

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("loop_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("max_leads_per_run", sa.Integer(), server_default="10", nullable=False),
        sa.Column("max_emails_per_account_daily", sa.Integer(), server_default="15", nullable=False),
        sa.Column(
            "alert_emails",
            sa.String(500),
            server_default="snehdeep@launchhouse.events,cto@launchhouse.events",
            nullable=False,
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_summary", postgresql.JSONB(), nullable=True),
        sa.Column("run_hour_utc", sa.Integer(), server_default="14", nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_automation_configs_tenant_id", "automation_configs", ["tenant_id"])

    op.create_table(
        "strategy_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("insight_type", sa.String(50), nullable=False),
        sa.Column("insight_data", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_strategy_insights_tenant_id", "strategy_insights", ["tenant_id"])
    op.create_index("ix_strategy_insights_type", "strategy_insights", ["insight_type"])

    op.create_table(
        "health_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), server_default="warning", nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("alerted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_health_alerts_tenant_id", "health_alerts", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("health_alerts")
    op.drop_table("strategy_insights")
    op.drop_table("automation_configs")
