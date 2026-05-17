"""
Stage 6 — OutreachIntelligenceAgent.

TargetedResearchAgent lives in its own module (targeted_research.py) — the
cost-optimization layer is large enough to warrant separation.
"""
from __future__ import annotations

import json
import logging
import re

from app.agents.v3.base import BaseIntelligenceAgent
from app.agents.v3.contracts import (
    AgentContext, AgentResult, AgentStatus, CacheScope, EvidenceItem,
    PipelineStage, SignalType, SourceType,
)
from app.agents.v3.registry import register_agent

logger = logging.getLogger(__name__)


@register_agent
class OutreachIntelligenceAgent(BaseIntelligenceAgent):
    """Generate evidence-tied outreach angles for top-tier leads (Sonnet)."""
    signal_type = SignalType.OUTREACH
    stage = PipelineStage.INTELLIGENCE.value
    cache_scope = CacheScope.CONTACT
    cache_ttl_hours = 168
    timeout_s = 60.0
    max_attempts = 2

    async def _collect(self, ctx: AgentContext) -> AgentResult:
        if not self.settings.anthropic_api_key:
            return AgentResult(
                signal_type=self.signal_type, status=AgentStatus.SKIPPED,
                value=0.0, confidence=0.0, error="no anthropic key",
            )

        facts = []
        for sig in (SignalType.CVENT, SignalType.EVENT_VOLUME, SignalType.HIRING,
                    SignalType.BUDGET, SignalType.OUTSOURCING):
            r = ctx.upstream_result(sig)
            if r and r.is_usable():
                facts.append(f"- {sig.value}: value={r.value:.2f} conf={r.confidence:.2f} "
                             f"{json.dumps(r.payload, default=str)[:300]}")
        contact = ctx.contact
        prompt = (
            f"You write B2B outreach intelligence for a firm that provides outsourced "
            f"Cvent event-operations services.\n\n"
            f"Company: {ctx.company.name} ({ctx.company.industry or 'industry n/a'})\n"
            f"Contact: {contact.full_name if contact else 'n/a'} — "
            f"{contact.title if contact else 'n/a'}\n\n"
            f"Signals:\n" + "\n".join(facts) + "\n\n"
            f"Return JSON only: {{\"recommended_contact_role\": str, "
            f"\"angles\": [str, str, str], \"hooks\": [str, str], "
            f"\"timing\": str, \"objections\": [str]}}"
        )
        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import HumanMessage
        llm = ChatAnthropic(model=self.settings.anthropic_model, temperature=0.4,
                            api_key=self.settings.anthropic_api_key, max_retries=2)
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = resp.content if isinstance(resp.content, str) else str(resp.content)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        intel = json.loads(match.group(0)) if match else {"angles": [], "hooks": []}

        evidence = [EvidenceItem(
            claim=f"Outreach angle: {a}", signal_type=self.signal_type,
            source_type=SourceType.LLM_INFERENCE, source_provider="claude",
            confidence=0.7,
        ) for a in intel.get("angles", [])[:3]]

        return AgentResult(
            signal_type=self.signal_type, status=AgentStatus.OK,
            value=1.0 if intel.get("angles") else 0.3,
            confidence=0.7, payload=intel, evidence=evidence, providers=["claude"],
        )
