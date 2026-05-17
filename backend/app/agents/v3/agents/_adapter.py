"""Adapter that wraps a proven v2 SignalResult-producing agent in the v3 contract."""
from __future__ import annotations

from typing import Any, Callable

from app.agents.v3.base import BaseIntelligenceAgent
from app.agents.v3.contracts import (
    AgentContext, AgentResult, AgentStatus, EvidenceItem, SignalType, SourceType,
)


def adapt_v2(sr: Any, signal_type: SignalType,
             source: SourceType = SourceType.SEARCH) -> AgentResult:
    """Convert a v2 SignalResult into a v3 AgentResult + EvidenceItems."""
    ev: dict = getattr(sr, "evidence", {}) or {}
    items: list[EvidenceItem] = []

    # URL-bearing sub-items become atomic evidence rows
    for key, val in ev.items():
        if not isinstance(val, list):
            continue
        for item in val:
            if isinstance(item, dict) and item.get("url"):
                items.append(EvidenceItem(
                    claim=str(item.get("title") or item.get("snippet") or key)[:500],
                    signal_type=signal_type, source_type=source,
                    source_url=item.get("url"),
                    raw_snippet=(item.get("snippet") or item.get("note") or "")[:1000],
                    confidence=getattr(sr, "confidence", 1.0),
                    raw_data=item,
                ))

    # one derived summary item, always present for traceability
    reason = ev.get("reason") or ev.get("reasoning") or f"{signal_type.value} signal collected"
    items.append(EvidenceItem(
        claim=str(reason)[:500], signal_type=signal_type,
        source_type=SourceType.DERIVED,
        confidence=getattr(sr, "confidence", 1.0), raw_data=ev,
    ))

    providers = [
        p for p in (getattr(sr, "provider", "") or "").split(",")
        if p and p not in ("none", "")
    ]
    return AgentResult(
        signal_type=signal_type, status=AgentStatus.OK,
        value=float(getattr(sr, "value", 0.0)),
        confidence=float(getattr(sr, "confidence", 0.0)),
        payload=ev, evidence=items, providers=providers,
    )


class PortedV2Agent(BaseIntelligenceAgent):
    """Base for agents that delegate collection to a v2 signal agent."""

    v2_factory: Callable[[], Any]          # set by subclass: () -> v2 agent

    def _v2_kwargs(self, ctx: AgentContext) -> dict[str, Any]:
        identity = ctx.upstream_payload(SignalType.IDENTITY)
        return {
            "company_name": ctx.company.name,
            "domain": ctx.company.domain,
            "company": ctx.company,
            "contact": ctx.contact,
            "identity_profile": identity.get("profile") or {},
        }

    async def _collect(self, ctx: AgentContext) -> AgentResult:
        v2 = type(self).v2_factory()
        sr = await v2.collect(**self._v2_kwargs(ctx))
        return adapt_v2(sr, self.signal_type)
