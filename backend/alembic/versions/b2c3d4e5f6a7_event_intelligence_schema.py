"""event_intelligence_schema (v3)

Adds 8 entities for the Event Operations Intelligence Engine.
signal_evidence + lead_score_breakdown are RANGE-partitioned monthly.
Purely additive — v1/v2 tables and pipelines unaffected.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-17 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
UUIDARR = postgresql.ARRAY(sa.UUID())


def _company_table(name, *extra_cols, **extra):
    op.create_table(
        name,
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        *extra_cols,
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        **extra,
    )


def upgrade() -> None:
    # ── 1. company_event_profiles ────────────────────────────────────────
    _company_table(
        "company_event_profiles",
        sa.Column("cvent_status", sa.String(20), server_default="unknown"),
        sa.Column("cvent_confidence", sa.Float()),
        sa.Column("event_volume_tier", sa.String(20), server_default="unknown"),
        sa.Column("estimated_events_per_year", sa.Integer()),
        sa.Column("attendee_scale", sa.String(20)),
        sa.Column("event_complexity_score", sa.Float()),
        sa.Column("event_team_size", sa.Integer()),
        sa.Column("event_team_under_resourced", sa.Boolean()),
        sa.Column("estimated_budget_band", sa.String(30)),
        sa.Column("budget_confidence", sa.Float()),
        sa.Column("outsourcing_propensity", sa.Float()),
        sa.Column("outsourcing_tier", sa.String(20), server_default="unknown"),
        sa.Column("overall_fit_score", sa.Float()),
        sa.Column("icp_fit", sa.Boolean()),
        sa.Column("data_completeness", sa.Float(), server_default="0"),
        sa.Column("enrichment_version", sa.String(10), server_default="v3"),
        sa.Column("last_enriched_at", sa.DateTime(timezone=True)),
        sa.Column("next_refresh_due", sa.DateTime(timezone=True)),
        sa.Column("summary", sa.Text()),
        sa.Column("raw_rollup", JSONB, server_default="{}"),
        sa.UniqueConstraint("company_id", name="uq_company_event_profile_company"),
        sa.CheckConstraint("data_completeness BETWEEN 0 AND 1", name="ck_cep_completeness"),
    )
    op.create_index("ix_cep_tenant_tier", "company_event_profiles",
                    ["tenant_id", "outsourcing_tier", "overall_fit_score"])
    op.create_index("ix_cep_refresh_due", "company_event_profiles", ["next_refresh_due"])

    # ── 2. org_graphs ────────────────────────────────────────────────────
    _company_table(
        "org_graphs",
        sa.Column("parent_company", sa.String(255)),
        sa.Column("parent_domain", sa.String(255)),
        sa.Column("subsidiaries", JSONB, server_default="[]"),
        sa.Column("headcount_total", sa.Integer()),
        sa.Column("headcount_band", sa.String(30)),
        sa.Column("location_count", sa.Integer()),
        sa.Column("locations", JSONB, server_default="[]"),
        sa.Column("departments", JSONB, server_default="{}"),
        sa.Column("has_events_org", sa.Boolean()),
        sa.Column("has_marketing_org", sa.Boolean()),
        sa.Column("events_org_path", JSONB),
        sa.Column("key_people", JSONB, server_default="[]"),
        sa.Column("structure_raw", JSONB, server_default="{}"),
        sa.Column("evidence_ids", UUIDARR, server_default="{}"),
        sa.UniqueConstraint("company_id", name="uq_org_graph_company"),
    )
    op.create_index("ix_org_graph_tenant", "org_graphs", ["tenant_id"])
    op.create_index("ix_org_graph_departments_gin", "org_graphs", ["departments"],
                    postgresql_using="gin")

    # ── 3. cvent_evidence ────────────────────────────────────────────────
    _company_table(
        "cvent_evidence",
        sa.Column("detected", sa.Boolean(), nullable=False),
        sa.Column("detection_method", sa.String(30)),
        sa.Column("products", JSONB, server_default="[]"),
        sa.Column("cvent_subdomain", sa.String(255)),
        sa.Column("registration_urls", JSONB, server_default="[]"),
        sa.Column("confidence", sa.Float()),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("evidence_ids", UUIDARR, server_default="{}"),
        sa.Column("detail", JSONB, server_default="{}"),
    )
    op.create_index("ix_cvent_company_current", "cvent_evidence", ["company_id", "is_current"])
    op.create_index("ix_cvent_tenant", "cvent_evidence", ["tenant_id"])
    op.create_index("ix_cvent_detected_at", "cvent_evidence", ["detected_at"])
    op.create_index("ix_cvent_products_gin", "cvent_evidence", ["products"], postgresql_using="gin")

    # ── 4. event_history ─────────────────────────────────────────────────
    _company_table(
        "event_history",
        sa.Column("event_name", sa.String(500)),
        sa.Column("event_type", sa.String(30)),
        sa.Column("event_date", sa.Date()),
        sa.Column("recurrence", sa.String(20)),
        sa.Column("attendee_estimate", sa.Integer()),
        sa.Column("session_count", sa.Integer()),
        sa.Column("platform", sa.String(30)),
        sa.Column("location", sa.String(255)),
        sa.Column("is_upcoming", sa.Boolean(), server_default="false"),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("evidence_ids", UUIDARR, server_default="{}"),
        sa.Column("detail", JSONB, server_default="{}"),
    )
    op.create_index("ix_event_history_company_date", "event_history", ["company_id", "event_date"])
    op.create_index("ix_event_history_tenant", "event_history", ["tenant_id"])
    op.create_index("ix_event_history_upcoming", "event_history", ["company_id", "is_upcoming"])

    # ── 5. hiring_signals ────────────────────────────────────────────────
    _company_table(
        "hiring_signals",
        sa.Column("role_title", sa.String(300)),
        sa.Column("role_category", sa.String(40)),
        sa.Column("seniority", sa.String(30)),
        sa.Column("job_url", sa.String(1000)),
        sa.Column("posted_date", sa.Date()),
        sa.Column("location", sa.String(255)),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("is_event_related", sa.Boolean(), server_default="true"),
        sa.Column("role_keywords", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("evidence_ids", UUIDARR, server_default="{}"),
        sa.Column("detail", JSONB, server_default="{}"),
    )
    op.create_index("ix_hiring_company_status", "hiring_signals", ["company_id", "status"])
    op.create_index("ix_hiring_tenant", "hiring_signals", ["tenant_id"])
    op.create_index("ix_hiring_observed_at", "hiring_signals", ["observed_at"])
    op.create_index("ix_hiring_keywords_gin", "hiring_signals", ["role_keywords"],
                    postgresql_using="gin")

    # ── 6. buying_intent_signals ─────────────────────────────────────────
    _company_table(
        "buying_intent_signals",
        sa.Column("contact_id", sa.UUID()),
        sa.Column("intent_type", sa.String(40), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(10), server_default="positive"),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decay_at", sa.DateTime(timezone=True)),
        sa.Column("summary", sa.Text()),
        sa.Column("evidence_ids", UUIDARR, server_default="{}"),
        sa.Column("detail", JSONB, server_default="{}"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        sa.CheckConstraint("strength BETWEEN 0 AND 1", name="ck_intent_strength"),
    )
    op.create_index("ix_intent_company_type", "buying_intent_signals", ["company_id", "intent_type"])
    op.create_index("ix_intent_tenant", "buying_intent_signals", ["tenant_id"])
    op.create_index("ix_intent_detected_at", "buying_intent_signals", ["detected_at"])
    op.create_index("ix_intent_decay_at", "buying_intent_signals", ["decay_at"])

    # ── 7. signal_evidence — PARTITIONED monthly by created_at ───────────
    op.execute("""
        CREATE TABLE signal_evidence (
            id              UUID        NOT NULL DEFAULT gen_random_uuid(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            tenant_id       UUID        NOT NULL,
            company_id      UUID        NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            signal_type     VARCHAR(40) NOT NULL,
            claim           TEXT        NOT NULL,
            source_type     VARCHAR(20) NOT NULL,
            source_provider VARCHAR(40),
            source_url      VARCHAR(1000),
            raw_snippet     TEXT,
            raw_data        JSONB       DEFAULT '{}',
            confidence      DOUBLE PRECISION,
            observed_at     TIMESTAMPTZ,
            content_hash    VARCHAR(64),
            agent           VARCHAR(50),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)
    op.execute("CREATE INDEX ix_sigev_company_signal ON signal_evidence (company_id, signal_type);")
    op.execute("CREATE INDEX ix_sigev_tenant        ON signal_evidence (tenant_id);")
    op.execute("CREATE INDEX ix_sigev_content_hash  ON signal_evidence (content_hash);")
    op.execute("CREATE INDEX ix_sigev_created_at    ON signal_evidence (created_at);")

    # ── 8. lead_score_breakdown — PARTITIONED monthly by created_at ──────
    op.execute("""
        CREATE TABLE lead_score_breakdown (
            id            UUID             NOT NULL DEFAULT gen_random_uuid(),
            created_at    TIMESTAMPTZ      NOT NULL DEFAULT now(),
            tenant_id     UUID             NOT NULL,
            score_id      UUID             NOT NULL REFERENCES lead_scores(id) ON DELETE CASCADE,
            lead_id       UUID             NOT NULL REFERENCES leads(id)       ON DELETE CASCADE,
            signal_type   VARCHAR(40)      NOT NULL,
            raw_value     DOUBLE PRECISION NOT NULL,
            weight        DOUBLE PRECISION NOT NULL,
            contribution  DOUBLE PRECISION NOT NULL,
            confidence    DOUBLE PRECISION,
            evidence_ids  UUID[]           DEFAULT '{}',
            rationale     TEXT,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)
    op.execute("CREATE INDEX ix_lsb_score       ON lead_score_breakdown (score_id);")
    op.execute("CREATE INDEX ix_lsb_lead        ON lead_score_breakdown (lead_id);")
    op.execute("CREATE INDEX ix_lsb_signal_type ON lead_score_breakdown (signal_type);")
    op.execute("CREATE INDEX ix_lsb_created_at  ON lead_score_breakdown (created_at);")

    # ── Initial partitions: current month + next 2 + a DEFAULT catch-all ──
    for tbl in ("signal_evidence", "lead_score_breakdown"):
        op.execute(f"""
            DO $$
            DECLARE m DATE := date_trunc('month', now())::date;
            BEGIN
              FOR i IN 0..2 LOOP
                EXECUTE format(
                  'CREATE TABLE %I PARTITION OF {tbl} FOR VALUES FROM (%L) TO (%L);',
                  '{tbl}_' || to_char(m + (i||' month')::interval, 'YYYY_MM'),
                  (m + (i||' month')::interval)::text,
                  (m + ((i+1)||' month')::interval)::text);
              END LOOP;
              EXECUTE format('CREATE TABLE %I PARTITION OF {tbl} DEFAULT;', '{tbl}_default');
            END $$;
        """)

    # ── lead_scores: 4 additive nullable columns (v3 explainability) ─────
    op.add_column("lead_scores", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("lead_scores", sa.Column("completeness", sa.Float(), nullable=True))
    op.add_column("lead_scores", sa.Column("disqualified_reason", sa.String(100), nullable=True))
    op.add_column("lead_scores", sa.Column("gate_passed", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("lead_scores", "gate_passed")
    op.drop_column("lead_scores", "disqualified_reason")
    op.drop_column("lead_scores", "completeness")
    op.drop_column("lead_scores", "confidence")
    op.execute("DROP TABLE IF EXISTS lead_score_breakdown CASCADE;")
    op.execute("DROP TABLE IF EXISTS signal_evidence CASCADE;")
    for t in ("buying_intent_signals", "hiring_signals", "event_history",
              "cvent_evidence", "org_graphs", "company_event_profiles"):
        op.drop_table(t)
