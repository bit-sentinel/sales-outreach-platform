"""
OutreachAI – v3 Event Operations Intelligence schema.

All entities are ADDITIVE. v1/v2 pipelines and their tables are untouched.
Company-level tables are tenant-scoped (FK -> companies, itself tenant-scoped);
cross-tenant signal reuse continues at the signal_cache layer.

signal_evidence and lead_score_breakdown are RANGE-partitioned by created_at
(monthly). Links into signal_evidence are soft UUID[] references — Postgres
cannot cleanly accept FKs into a partitioned table.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index,
    Integer, PrimaryKeyConstraint, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


# ── 1. CompanyEventProfile — canonical company-level rollup (1 per company) ──
class CompanyEventProfile(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "company_event_profiles"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_company_event_profile_company"),
        Index("ix_cep_tenant_tier", "tenant_id", "outsourcing_tier", "overall_fit_score"),
        Index("ix_cep_refresh_due", "next_refresh_due"),
        CheckConstraint("data_completeness BETWEEN 0 AND 1", name="ck_cep_completeness"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    cvent_status: Mapped[str] = mapped_column(String(20), server_default="unknown")
    cvent_confidence: Mapped[float | None] = mapped_column(Float)
    event_volume_tier: Mapped[str] = mapped_column(String(20), server_default="unknown")
    estimated_events_per_year: Mapped[int | None] = mapped_column(Integer)
    attendee_scale: Mapped[str | None] = mapped_column(String(20))
    event_complexity_score: Mapped[float | None] = mapped_column(Float)
    event_team_size: Mapped[int | None] = mapped_column(Integer)
    event_team_under_resourced: Mapped[bool | None] = mapped_column(Boolean)
    estimated_budget_band: Mapped[str | None] = mapped_column(String(30))
    budget_confidence: Mapped[float | None] = mapped_column(Float)
    outsourcing_propensity: Mapped[float | None] = mapped_column(Float)
    outsourcing_tier: Mapped[str] = mapped_column(String(20), server_default="unknown")
    overall_fit_score: Mapped[float | None] = mapped_column(Float)
    icp_fit: Mapped[bool | None] = mapped_column(Boolean)
    data_completeness: Mapped[float] = mapped_column(Float, server_default="0")
    enrichment_version: Mapped[str] = mapped_column(String(10), server_default="v3")
    last_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_refresh_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)
    raw_rollup: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")


# ── 2. OrgGraph — company org structure (1 per company, update-in-place) ────
class OrgGraph(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "org_graphs"
    __table_args__ = (
        UniqueConstraint("company_id", name="uq_org_graph_company"),
        Index("ix_org_graph_tenant", "tenant_id"),
        Index("ix_org_graph_departments_gin", "departments", postgresql_using="gin"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    parent_company: Mapped[str | None] = mapped_column(String(255))
    parent_domain: Mapped[str | None] = mapped_column(String(255))
    subsidiaries: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    headcount_total: Mapped[int | None] = mapped_column(Integer)
    headcount_band: Mapped[str | None] = mapped_column(String(30))
    location_count: Mapped[int | None] = mapped_column(Integer)
    locations: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    departments: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")
    has_events_org: Mapped[bool | None] = mapped_column(Boolean)
    has_marketing_org: Mapped[bool | None] = mapped_column(Boolean)
    events_org_path: Mapped[dict | None] = mapped_column(JSONB)
    key_people: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    structure_raw: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")
    evidence_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default="{}")


# ── 3. CventEvidence — Cvent detection detail (append; is_current flagged) ──
class CventEvidence(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "cvent_evidence"
    __table_args__ = (
        Index("ix_cvent_company_current", "company_id", "is_current"),
        Index("ix_cvent_tenant", "tenant_id"),
        Index("ix_cvent_detected_at", "detected_at"),
        Index("ix_cvent_products_gin", "products", postgresql_using="gin"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detection_method: Mapped[str | None] = mapped_column(String(30))
    products: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    cvent_subdomain: Mapped[str | None] = mapped_column(String(255))
    registration_urls: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    confidence: Mapped[float | None] = mapped_column(Float)
    is_current: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(String(1000))
    evidence_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default="{}")
    detail: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")


# ── 4. EventHistory — one row per known/historical event (append-only) ─────
class EventHistory(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "event_history"
    __table_args__ = (
        Index("ix_event_history_company_date", "company_id", "event_date"),
        Index("ix_event_history_tenant", "tenant_id"),
        Index("ix_event_history_upcoming", "company_id", "is_upcoming"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    event_name: Mapped[str | None] = mapped_column(String(500))
    event_type: Mapped[str | None] = mapped_column(String(30))
    event_date: Mapped[date | None] = mapped_column(Date)
    recurrence: Mapped[str | None] = mapped_column(String(20))
    attendee_estimate: Mapped[int | None] = mapped_column(Integer)
    session_count: Mapped[int | None] = mapped_column(Integer)
    platform: Mapped[str | None] = mapped_column(String(30))
    location: Mapped[str | None] = mapped_column(String(255))
    is_upcoming: Mapped[bool] = mapped_column(Boolean, server_default="false")
    source_url: Mapped[str | None] = mapped_column(String(1000))
    evidence_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default="{}")
    detail: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")


# ── 5. HiringSignals — event-related open reqs (append; status lifecycle) ──
class HiringSignal(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "hiring_signals"
    __table_args__ = (
        Index("ix_hiring_company_status", "company_id", "status"),
        Index("ix_hiring_tenant", "tenant_id"),
        Index("ix_hiring_observed_at", "observed_at"),
        Index("ix_hiring_keywords_gin", "role_keywords", postgresql_using="gin"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    role_title: Mapped[str | None] = mapped_column(String(300))
    role_category: Mapped[str | None] = mapped_column(String(40))
    seniority: Mapped[str | None] = mapped_column(String(30))
    job_url: Mapped[str | None] = mapped_column(String(1000))
    posted_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), server_default="open")
    is_event_related: Mapped[bool] = mapped_column(Boolean, server_default="true")
    role_keywords: Mapped[list | None] = mapped_column(ARRAY(String), server_default="{}")
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    evidence_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default="{}")
    detail: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")


# ── 6. BuyingIntentSignals — time-decaying intent signals (append-only) ────
class BuyingIntentSignal(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "buying_intent_signals"
    __table_args__ = (
        Index("ix_intent_company_type", "company_id", "intent_type"),
        Index("ix_intent_tenant", "tenant_id"),
        Index("ix_intent_detected_at", "detected_at"),
        Index("ix_intent_decay_at", "decay_at"),
        CheckConstraint("strength BETWEEN 0 AND 1", name="ck_intent_strength"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    intent_type: Mapped[str] = mapped_column(String(40), nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), server_default="positive")
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decay_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default="{}")
    detail: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")


# ── 7. SignalEvidence — immutable atomic provenance ledger (PARTITIONED) ───
class SignalEvidence(Base):
    __tablename__ = "signal_evidence"
    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at"),
        Index("ix_sigev_company_signal", "company_id", "signal_type"),
        Index("ix_sigev_tenant", "tenant_id"),
        Index("ix_sigev_content_hash", "content_hash"),
        Index("ix_sigev_created_at", "created_at"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    signal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_provider: Mapped[str | None] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    raw_snippet: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")
    confidence: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    agent: Mapped[str | None] = mapped_column(String(50))


# ── 8. LeadScoreBreakdown — per-signal contribution rows (PARTITIONED) ─────
class LeadScoreBreakdown(Base):
    __tablename__ = "lead_score_breakdown"
    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at"),
        Index("ix_lsb_score", "score_id"),
        Index("ix_lsb_lead", "lead_id"),
        Index("ix_lsb_signal_type", "signal_type"),
        Index("ix_lsb_created_at", "created_at"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    score_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lead_scores.id", ondelete="CASCADE"), nullable=False
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    signal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_value: Mapped[float] = mapped_column(Float, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    contribution: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), server_default="{}")
    rationale: Mapped[str | None] = mapped_column(Text)
