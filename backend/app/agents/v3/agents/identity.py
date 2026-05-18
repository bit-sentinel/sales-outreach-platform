"""Stage 1 — IdentityAgent + OrgGraphAgent."""
from __future__ import annotations

from app.agents.v3.agents._adapter import PortedV2Agent, adapt_v2
from app.agents.v3.base import BaseIntelligenceAgent
from app.agents.v3.contracts import (
    AgentContext, AgentResult, AgentStatus, CacheScope, EvidenceItem,
    PipelineStage, SignalType, SourceType,
)


# ── IdentityAgent — Apollo -> PDL contact/company resolution ───────────────
from app.agents.v3.registry import register_agent


@register_agent
class IdentityAgent(BaseIntelligenceAgent):
    signal_type = SignalType.IDENTITY
    stage = PipelineStage.IDENTITY.value
    cache_scope = CacheScope.CONTACT
    cache_ttl_hours = 720          # 30d — identity is stable
    timeout_s = 30.0

    async def _collect(self, ctx: AgentContext) -> AgentResult:
        email = ctx.contact.email if ctx.contact else None
        if not email:
            return AgentResult(
                signal_type=self.signal_type, status=AgentStatus.SKIPPED,
                value=0.0, confidence=0.0, error="no contact email",
            )

        profile: dict = {}
        provider = ""

        # Apollo first
        if self.settings.apollo_api_key:
            from app.tools.apollo import enrich_person_by_email as apollo_enrich
            profile = await self.call(
                provider="apollo", dedup_key=f"match:{email}",
                factory=lambda: apollo_enrich(email, self.settings.apollo_api_key),
                ttl_s=86_400,
            )
            if profile:
                provider = "apollo"

        # PDL fallback
        if not profile and self.settings.pdl_api_key:
            from app.tools.pdl import enrich_person_by_email as pdl_enrich
            profile = await self.call(
                provider="pdl", dedup_key=f"enrich:{email}",
                factory=lambda: pdl_enrich(email, self.settings.pdl_api_key),
                ttl_s=86_400,
            )
            if profile:
                provider = "pdl"

        if not profile:
            return AgentResult(
                signal_type=self.signal_type, status=AgentStatus.PARTIAL,
                value=0.0, confidence=0.3,
                payload={"resolved": False, "profile": {}},
                evidence=[EvidenceItem(
                    claim=f"No identity match for {email}",
                    signal_type=self.signal_type, source_type=SourceType.API,
                    confidence=0.3,
                )],
            )

        org = profile.get("organization") or {}
        payload = {
            "resolved": True,
            "profile": profile,                       # consumed by ported agents
            "title": profile.get("title"),
            "seniority": profile.get("seniority"),
            "department": profile.get("department"),
            "linkedin_url": profile.get("linkedin_url"),
            "twitter_url": profile.get("twitter_url"),
            "phone": profile.get("phone"),
            "location": profile.get("location"),
            "skills": profile.get("skills") or [],
            "interests": profile.get("interests") or [],
            "company_domain": org.get("domain"),
            "company_employee_count": org.get("employee_count"),
            "company_employee_range": org.get("employee_range"),
            "company_founded_year": org.get("founded_year"),
        }
        evidence = [EvidenceItem(
            claim=f"Identity resolved via {provider}: "
                  f"{profile.get('title') or 'unknown title'} at {org.get('name') or ctx.company.name}",
            signal_type=self.signal_type, source_type=SourceType.API,
            source_provider=provider,
            source_url=profile.get("linkedin_url"),
            confidence=1.0, raw_data={"organization": org},
        )]
        return AgentResult(
            signal_type=self.signal_type, status=AgentStatus.OK,
            value=1.0, confidence=0.95 if provider == "apollo" else 0.85,
            payload=payload, evidence=evidence, providers=[provider],
        )


# ── OrgGraphAgent — industry fit (ported) + org structure ─────────────────
@register_agent
class OrgGraphAgent(PortedV2Agent):
    signal_type = SignalType.ORG_GRAPH
    stage = PipelineStage.IDENTITY.value
    cache_scope = CacheScope.COMPANY
    cache_ttl_hours = 720
    # No depends_on: runs concurrently with IdentityAgent in Stage 1. It
    # augments from the identity profile when present and degrades to
    # company.industry / company.employee_count when it is not.

    @staticmethod
    def v2_factory():
        from app.agents.signals.industry_fit_signal import IndustryFitSignalAgent
        return IndustryFitSignalAgent()

    async def _collect(self, ctx: AgentContext) -> AgentResult:
        # Industry-fit value via the ported v2 agent
        result = await super()._collect(ctx)

        # Augment payload with org structure from the resolved identity profile
        identity = ctx.upstream_payload(SignalType.IDENTITY)
        org = (identity.get("profile") or {}).get("organization") or {}
        emp = org.get("employee_count") or ctx.company.employee_count
        payload = dict(result.payload)
        payload.update({
            "headcount_total": emp,
            "headcount_band": _band(emp),
            "departments": {},
            "has_events_org": None,
            "has_marketing_org": None,
            "industry": org.get("industry") or ctx.company.industry,
        })
        result.payload = payload
        return result


def _band(emp: int | None) -> str:
    if emp is None:
        return "unknown"
    if emp < 200:
        return "smb"
    if emp < 1000:
        return "mid"
    if emp < 5000:
        return "enterprise"
    return "global"
