"""Stage 2 — CventDetectionAgent + EventVolumeAgent."""
from __future__ import annotations

from typing import Any

from app.agents.v3.agents._adapter import PortedV2Agent
from app.agents.v3.contracts import AgentContext, CacheScope, PipelineStage, SignalType
from app.agents.v3.registry import register_agent


@register_agent
class CventDetectionAgent(PortedV2Agent):
    signal_type = SignalType.CVENT
    stage = PipelineStage.EVENT_FIT.value
    cache_scope = CacheScope.COMPANY
    cache_ttl_hours = 168          # 7d
    timeout_s = 60.0

    @staticmethod
    def v2_factory():
        from app.agents.signals.cvent_signal import CventSignalAgent
        return CventSignalAgent()

    async def _collect(self, ctx: AgentContext) -> AgentResult:  # type: ignore[override]
        result = await super()._collect(ctx)
        # Normalize payload into the v3 CventPayload shape
        ev = result.payload
        result.payload = {
            "detected": (ev.get("total_pages_found", 0) or 0) > 0,
            "detection_method": "site_search",
            "products": [],
            "registration_urls": [e.get("url") for e in ev.get("events", []) if e.get("url")],
            "upcoming_count": ev.get("upcoming_count", 0),
            "soonest_days": ev.get("soonest_days"),
            "_raw": ev,
        }
        return result


@register_agent
class EventVolumeAgent(PortedV2Agent):
    signal_type = SignalType.EVENT_VOLUME
    stage = PipelineStage.EVENT_FIT.value
    cache_scope = CacheScope.COMPANY
    cache_ttl_hours = 336          # 14d
    timeout_s = 60.0

    @staticmethod
    def v2_factory():
        from app.agents.signals.event_volume_signal import EventVolumeSignalAgent
        return EventVolumeSignalAgent()

    def _v2_kwargs(self, ctx: AgentContext) -> dict[str, Any]:
        kwargs = super()._v2_kwargs(ctx)
        # Soft seed from Cvent if it already ran (cross-stage cache may surface it)
        kwargs["cvent_evidence"] = ctx.upstream_payload(SignalType.CVENT).get("_raw") or {}
        return kwargs

    async def _collect(self, ctx: AgentContext) -> AgentResult:  # type: ignore[override]
        result = await super()._collect(ctx)
        ev = result.payload
        result.payload = {
            "estimated_events_per_year": ev.get("events_per_year"),
            "complexity_tier": ev.get("complexity"),
            "attendee_scale": None,
            "upcoming_events": [],
            "_raw": ev,
        }
        return result
