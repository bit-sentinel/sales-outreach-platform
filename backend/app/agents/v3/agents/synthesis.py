"""Stage 4 — BudgetEstimatorAgent + OutsourcingPressureAgent (deterministic synthesis)."""
from __future__ import annotations

from app.agents.v3.base import BaseIntelligenceAgent
from app.agents.v3.contracts import (
    AgentContext, AgentResult, AgentStatus, EvidenceItem, PipelineStage,
    SignalType, SourceType,
)
from app.agents.v3.registry import register_agent

# Per-event cost bands (USD) used to size an annual budget.
_PER_EVENT_COST = {"enterprise": 180_000, "mid": 60_000, "small": 18_000}
_COMPLEXITY_MULT = {"complex": 1.4, "medium": 1.0, "simple": 0.7}


def _budget_band(annual_usd: float) -> str:
    if annual_usd >= 1_000_000:
        return ">1M"
    if annual_usd >= 250_000:
        return "250k-1M"
    return "<250k"


@register_agent
class BudgetEstimatorAgent(BaseIntelligenceAgent):
    """Estimate annual event budget from volume × scale × complexity. No LLM."""
    signal_type = SignalType.BUDGET
    stage = PipelineStage.SYNTHESIS.value
    cache_ttl_hours = 336
    depends_on = (SignalType.EVENT_VOLUME,)
    timeout_s = 15.0

    async def _collect(self, ctx: AgentContext) -> AgentResult:
        vol = ctx.upstream_payload(SignalType.EVENT_VOLUME)
        events = vol.get("estimated_events_per_year") or 0
        complexity = (vol.get("complexity_tier") or "simple").lower()

        emp = ctx.company.employee_count or 0
        scale = "enterprise" if emp >= 5000 else "mid" if emp >= 500 else "small"

        per_event = _PER_EVENT_COST[scale] * _COMPLEXITY_MULT.get(complexity, 1.0)
        annual = per_event * max(events, 1)
        band = _budget_band(annual)

        # value: budget materiality as a 0..1 normalized signal
        value = min(1.0, annual / 1_000_000)
        confidence = 0.7 if events else 0.3

        evidence = [EvidenceItem(
            claim=f"Estimated annual event budget ~${annual:,.0f} ({band}) "
                  f"from {events} events/yr at {scale} scale, {complexity} complexity",
            signal_type=self.signal_type, source_type=SourceType.DERIVED,
            confidence=confidence,
            raw_data={"annual_usd": annual, "per_event": per_event, "scale": scale},
        )]
        return AgentResult(
            signal_type=self.signal_type, status=AgentStatus.OK,
            value=value, confidence=confidence,
            payload={
                "estimated_budget_band": band,
                "estimated_annual_usd": round(annual),
                "attendee_scale": scale,
                "per_event_usd": round(per_event),
            },
            evidence=evidence, providers=["heuristic_model"],
        )


@register_agent
class OutsourcingPressureAgent(BaseIntelligenceAgent):
    """
    Blend team gap + hiring pressure + event volume + Cvent presence into an
    outsourcing-propensity score. Deterministic; reasons are explainable.
    """
    signal_type = SignalType.OUTSOURCING
    stage = PipelineStage.SYNTHESIS.value
    cache_ttl_hours = 168
    depends_on = (SignalType.EVENT_VOLUME,)
    timeout_s = 15.0

    async def _collect(self, ctx: AgentContext) -> AgentResult:
        cvent = ctx.upstream_result(SignalType.CVENT)
        volume = ctx.upstream_result(SignalType.EVENT_VOLUME)
        hiring = ctx.upstream_result(SignalType.HIRING)
        team = ctx.upstream_payload(SignalType.EVENT_TEAM)

        reasons: list[str] = []
        score = 0.0

        # 1. event volume — more events => more operational load
        vol_v = volume.value if volume and volume.is_usable() else 0.0
        score += vol_v * 0.35
        if vol_v >= 0.6:
            reasons.append("high annual event volume")

        # 2. team under-resourced — small team vs. high volume
        if team.get("event_team_under_resourced"):
            score += 0.25
            reasons.append("event team appears under-resourced for its volume")

        # 3. hiring pressure — actively hiring event roles = capacity gap
        hire_v = hiring.value if hiring and hiring.is_usable() else 0.0
        score += hire_v * 0.25
        if hire_v >= 0.6:
            reasons.append("actively hiring multiple event-ops roles")

        # 4. Cvent in use — they already run a real platform => real ops
        cvent_v = cvent.value if cvent and cvent.is_usable() else 0.0
        score += cvent_v * 0.15
        if cvent_v >= 0.5:
            reasons.append("confirmed active Cvent program")

        score = max(0.0, min(1.0, score))
        tier = "high" if score >= 0.66 else "medium" if score >= 0.4 else "low"
        if not reasons:
            reasons.append("limited operational-pressure evidence")

        confidence = 0.4 + 0.5 * min(
            1.0,
            sum(1 for r in (cvent, volume, hiring) if r and r.is_usable()) / 3,
        )
        evidence = [EvidenceItem(
            claim=f"Outsourcing propensity {tier} ({score:.2f}): " + "; ".join(reasons),
            signal_type=self.signal_type, source_type=SourceType.DERIVED,
            confidence=confidence,
            raw_data={"score": score, "reasons": reasons},
        )]
        return AgentResult(
            signal_type=self.signal_type, status=AgentStatus.OK,
            value=score, confidence=confidence,
            payload={"outsourcing_propensity": score, "outsourcing_tier": tier,
                     "reasons": reasons},
            evidence=evidence, providers=["heuristic_model"],
        )
