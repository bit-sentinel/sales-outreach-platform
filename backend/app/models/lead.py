"""
OutreachAI – SQLAlchemy Models: Companies, Contacts, Leads, Enrichment.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Company(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    industry: Mapped[str | None] = mapped_column(String(100))
    employee_count: Mapped[int | None] = mapped_column(Integer)
    revenue_range: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    website_url: Mapped[str | None] = mapped_column(String(500))
    tags: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    custom_fields: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")

    contacts: Mapped[list["Contact"]] = relationship(back_populates="company", lazy="selectin")
    leads: Mapped[list["Lead"]] = relationship(back_populates="company", lazy="selectin")


class Contact(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "contacts"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), index=True
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(30))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str | None] = mapped_column(String(50))
    tags: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    custom_fields: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")

    company: Mapped["Company | None"] = relationship(back_populates="contacts", lazy="selectin")


class Lead(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "leads"

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), server_default="new", nullable=False, index=True
    )  # new, enriching, enriched, scored, campaign_active, replied, converted, disqualified
    source: Mapped[str | None] = mapped_column(String(100))
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tags: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    custom_fields: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")
    enrichment_status: Mapped[str] = mapped_column(String(50), server_default="pending")
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped["Company | None"] = relationship(back_populates="leads", lazy="selectin")
    contact: Mapped["Contact | None"] = relationship(lazy="selectin")
    activities: Mapped[list["LeadActivity"]] = relationship(back_populates="lead", lazy="selectin")
    scores: Mapped[list["LeadScore"]] = relationship(back_populates="lead", lazy="selectin")


class LeadActivity(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "lead_activities"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lead: Mapped["Lead"] = relationship(back_populates="activities")


class ImportBatch(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "import_batches"

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(50), server_default="pending")
    total_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    processed_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    success_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    error_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    column_mapping: Mapped[dict | None] = mapped_column(JSONB)
    errors: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EnrichmentJob(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "enrichment_jobs"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), server_default="pending")
    provider: Mapped[str | None] = mapped_column(String(50))
    input_data: Mapped[dict | None] = mapped_column(JSONB)
    output_data: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchData(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "research_data"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000))
    title: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str | None] = mapped_column(Text)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, server_default="{}")


class EnrichmentData(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "enrichment_data"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    version: Mapped[int] = mapped_column(Integer, server_default="1")


class AIInsight(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "ai_insights"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    insight_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    source_data: Mapped[dict | None] = mapped_column(JSONB)
    model_used: Mapped[str | None] = mapped_column(String(50))
    tokens_used: Mapped[int | None] = mapped_column(Integer)


class LeadScore(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "lead_scores"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)  # hot, warm, cold
    signal_scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # New: per-signal breakdown (value, weight, evidence) from signal pipeline
    signal_breakdown: Mapped[dict | None] = mapped_column(JSONB)
    explanation: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(50))
    # "v1" = legacy LLM scorer, "v2" = signal-centric engine
    pipeline_version: Mapped[str] = mapped_column(String(10), server_default="v1")
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lead: Mapped["Lead"] = relationship(back_populates="scores")


class LeadSignal(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """One row per signal type per lead. Written by signal agents, read by scoring engine."""
    __tablename__ = "lead_signals"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)     # 0.0 – 1.0 normalized strength
    weight: Mapped[float] = mapped_column(Float, nullable=False)    # scoring weight for this signal type
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)   # structured evidence for explainability
    provider: Mapped[str | None] = mapped_column(String(100))       # which tool(s) sourced this signal
    confidence: Mapped[float | None] = mapped_column(Float)
    # When this signal expires and should be re-collected (NULL = never re-collect)
    cached_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SignalCache(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Company-level signal cache keyed by (signal_type, domain_hash).
    Allows multiple contacts from the same company to share signal data.
    No tenant_id: signals are company facts, not tenant-specific.
    """
    __tablename__ = "signal_cache"

    cache_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[float | None] = mapped_column(Float)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
