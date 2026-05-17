"""Stage 3 — EventTeamAgent + HiringPressureAgent."""
from __future__ import annotations

from app.agents.v3.agents._adapter import PortedV2Agent
from app.agents.v3.contracts import AgentContext, AgentResult, CacheScope, PipelineStage, SignalType
from app.agents.v3.registry import register_agent


@register_agent
class EventTeamAgent(PortedV2Agent):
    """
    Contact + org fit (ported org_fit) plus an under-resourced heuristic:
    a small team running a high event volume signals outsourcing pressure.
    """
    signal_type = SignalType.EVENT_TEAM
    stage = PipelineStage.PRESSURE.value
    cache_scope = CacheScope.CONTACT
    cache_ttl_hours = 720
    depends_on = (SignalType.IDENTITY,)

    @staticmethod
    def v2_factory():
        from app.agents.signals.org_fit_signal import OrgFitSignalAgent
        return OrgFitSignalAgent()

    async def _collect(self, ctx: AgentContext) -> AgentResult:  # type: ignore[override]
        result = await super()._collect(ctx)

        emp = ctx.company.employee_count
        events = ctx.upstream_payload(SignalType.EVENT_VOLUME).get("estimated_events_per_year")
        # crude proxy: assume ~1 event-team head per 8 events/yr; flag if implied team is tiny
        implied_team = None
        under_resourced = None
        if events:
            implied_team = max(1, round(events / 8))
            under_resourced = events >= 12 and (emp is None or emp < 5000)

        payload = dict(result.payload)
        payload.update({
            "event_team_size": implied_team,
            "event_team_under_resourced": under_resourced,
            "company_employee_count": emp,
        })
        result.payload = payload
        return result


@register_agent
class HiringPressureAgent(PortedV2Agent):
    signal_type = SignalType.HIRING
    stage = PipelineStage.PRESSURE.value
    cache_scope = CacheScope.COMPANY
    cache_ttl_hours = 72           # 3d — job posts move fast
    timeout_s = 50.0

    @staticmethod
    def v2_factory():
        from app.agents.signals.hiring_signal import HiringSignalAgent
        return HiringSignalAgent()

    async def _collect(self, ctx: AgentContext) -> AgentResult:  # type: ignore[override]
        result = await super()._collect(ctx)
        ev = result.payload
        result.payload = {
            "open_event_reqs": ev.get("match_count", 0),
            "matched_keywords": ev.get("matched_keywords", []),
            "roles": [
                {"title": j.get("title"), "url": j.get("url"),
                 "is_event_related": True, "keywords": ev.get("matched_keywords", [])}
                for j in ev.get("job_snippets", [])
            ],
            "_raw": ev,
        }
        return result
