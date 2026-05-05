"""Pydantic schemas for leads, companies, contacts, enrichment."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# ── Shared ──────────────────────────────────────────

class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Company ─────────────────────────────────────────

class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    revenue_range: str | None = None
    location: str | None = None
    description: str | None = None
    linkedin_url: str | None = None
    website_url: str | None = None
    tags: list[str] = []
    custom_fields: dict | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    revenue_range: str | None = None
    location: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    custom_fields: dict | None = None


class CompanyResponse(BaseModel):
    id: uuid.UUID
    name: str
    domain: str | None
    industry: str | None
    employee_count: int | None
    revenue_range: str | None
    location: str | None
    description: str | None
    tags: list | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Contact ─────────────────────────────────────────

class ContactCreate(BaseModel):
    company_id: uuid.UUID | None = None
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    title: str | None = None
    department: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    location: str | None = None
    timezone: str | None = None
    tags: list[str] = []
    custom_fields: dict | None = None


class ContactResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID | None
    first_name: str
    last_name: str
    email: str
    title: str | None
    department: str | None
    tags: list | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Lead ────────────────────────────────────────────

class LeadCreate(BaseModel):
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    source: str | None = None
    tags: list[str] = []
    custom_fields: dict | None = None


class LeadUpdate(BaseModel):
    status: str | None = None
    assigned_to: uuid.UUID | None = None
    tags: list[str] | None = None
    custom_fields: dict | None = None


class LeadResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    status: str
    source: str | None
    enrichment_status: str
    enriched_at: datetime | None
    tags: list | None
    created_at: datetime
    updated_at: datetime
    company: CompanyResponse | None = None
    contact: ContactResponse | None = None
    score_tier: str | None = None
    score_value: float | None = None
    active_campaign_id: uuid.UUID | None = None
    active_campaign_name: str | None = None

    model_config = {"from_attributes": True}


class LeadDetailResponse(LeadResponse):
    company: CompanyResponse | None = None
    contact: ContactResponse | None = None
    scores: list["LeadScoreResponse"] = []


# ── Lead Score ──────────────────────────────────────

class LeadScoreResponse(BaseModel):
    id: uuid.UUID
    overall_score: float
    tier: str
    signal_scores: dict
    explanation: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Import ──────────────────────────────────────────

class ImportBatchResponse(BaseModel):
    id: uuid.UUID
    file_name: str
    status: str
    total_rows: int
    processed_rows: int
    success_rows: int
    error_rows: int
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ── Enrichment ──────────────────────────────────────

class EnrichmentRequest(BaseModel):
    lead_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    enrichment_types: list[str] = ["web_research", "company", "scoring"]


class EnrichmentJobResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str | None = None
    job_type: str
    status: str
    error: str | None = None
    duration_ms: int | None
    tokens_used: int | None
    cost_usd: float | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
