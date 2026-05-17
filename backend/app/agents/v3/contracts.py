"""
v3 Event Intelligence — agent contracts.

Every agent consumes an AgentContext and returns an AgentResult.
These schemas are the stable boundary between agents, caching, persistence
and the scoring engine.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Enumerations ───────────────────────────────────────────────────────────
class SignalType(str, Enum):
    IDENTITY = "identity"
    ORG_GRAPH = "org_graph"
    CVENT = "cvent"
    EVENT_VOLUME = "event_volume"
    EVENT_TEAM = "event_team"
    HIRING = "hiring"
    BUDGET = "budget"
    OUTSOURCING = "outsourcing"
    TARGETED_RESEARCH = "targeted_research"
    OUTREACH = "outreach"


class AgentStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    CACHED = "cached"
    SKIPPED = "skipped"
    FAILED = "failed"


class SourceType(str, Enum):
    SEARCH = "search"
    SCRAPE = "scrape"
    API = "api"
    LLM_INFERENCE = "llm_inference"
    IMPORT = "import"
    CACHE = "cache"
    DERIVED = "derived"


class CacheScope(str, Enum):
    COMPANY = "company"
    CONTACT = "contact"


class PipelineStage(str, Enum):
    IDENTITY = "stage1_identity"
    EVENT_FIT = "stage2_event_fit"
    PRESSURE = "stage3_pressure"
    SYNTHESIS = "stage4_synthesis"
    SCORE = "stage5_score"
    INTELLIGENCE = "stage6_intelligence"


# ── Evidence ───────────────────────────────────────────────────────────────
class EvidenceItem(BaseModel):
    """One atomic, traceable fact. Maps 1:1 to a signal_evidence row."""
    model_config = ConfigDict(frozen=True)

    claim: str
    signal_type: SignalType
    source_type: SourceType
    source_provider: str | None = None
    source_url: str | None = None
    raw_snippet: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    observed_at: datetime | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)
    agent: str | None = None

    @property
    def content_hash(self) -> str:
        basis = f"{self.signal_type.value}|{self.claim}|{self.source_url or ''}"
        return hashlib.sha256(basis.encode()).hexdigest()


# ── Agent result ───────────────────────────────────────────────────────────
class AgentResult(BaseModel):
    """Uniform structured output for every intelligence agent."""

    signal_type: SignalType
    status: AgentStatus = AgentStatus.OK
    # Normalized signal strength 0..1. Weighting/combination is the scoring
    # engine's job — agents only self-report their own normalized strength.
    value: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    error: str | None = None
    attempts: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    cache_hit: bool = False
    cache_age_s: int | None = None

    @field_validator("value", "confidence")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    def is_usable(self) -> bool:
        return self.status in (AgentStatus.OK, AgentStatus.PARTIAL, AgentStatus.CACHED)


# ── Agent input context ────────────────────────────────────────────────────
class CompanyContext(BaseModel):
    company_id: UUID
    tenant_id: UUID
    name: str
    domain: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    location: str | None = None


class ContactContext(BaseModel):
    contact_id: UUID | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    email: str | None = None
    title: str | None = None
    department: str | None = None
    seniority: str | None = None
    linkedin_url: str | None = None


class AgentContext(BaseModel):
    """Immutable per-run input. `upstream` carries earlier agents' results."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    lead_id: UUID
    company: CompanyContext
    contact: ContactContext | None = None
    upstream: dict[SignalType, AgentResult] = Field(default_factory=dict)
    force_refresh: bool = False

    def upstream_payload(self, signal: SignalType) -> dict[str, Any]:
        r = self.upstream.get(signal)
        return dict(r.payload) if r and r.is_usable() else {}

    def upstream_result(self, signal: SignalType) -> AgentResult | None:
        return self.upstream.get(signal)
