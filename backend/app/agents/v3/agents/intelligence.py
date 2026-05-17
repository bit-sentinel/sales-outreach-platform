"""
Stage 6 — TargetedResearchAgent + OutreachIntelligenceAgent.

TargetedResearchAgent is the cost-optimization layer: it does NOT do generic
research. It inspects upstream confidence, builds a gap list, and spends the
cheapest provider that can close each gap — under a hard per-lead budget cap.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.agents.v3.base import BaseIntelligenceAgent
from app.agents.v3.contracts import (
    AgentContext, AgentResult, AgentStatus, CacheScope, EvidenceItem,
    PipelineStage, SignalType, SourceType,
)
from app.agents.v3.registry import register_agent

logger = logging.getLogger(__name__)

# ── Cost-optimization knobs ────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.6          # below this, a signal is a research gap
MAX_RESEARCH_BUDGET_USD = 0.08      # hard per-lead cap for Stage 6 research

# Rough per-call costs (USD) — cheapest tier is tried first.
_PROVIDER_COST = {"tavily": 0.005, "serpapi": 0.010,
                  "perplexity": 0.012, "firecrawl": 0.011}


@dataclass
class ResearchTask:
    signal: SignalType
    query: str
    provider: str          # tavily | perplexity | firecrawl
    reason: str

    @property
    def cost(self) -> float:
        return _PROVIDER_COST.get(self.provider, 0.01)


@register_agent
class TargetedResearchAgent(BaseIntelligenceAgent):
    signal_type = SignalType.TARGETED_RESEARCH
    stage = PipelineStage.INTELLIGENCE.value
    cache_ttl_hours = 72
    timeout_s = 90.0
    max_attempts = 2

    # ── decision tree: which gaps justify spend ────────────────────────────
    def _plan(self, ctx: AgentContext) -> list[ResearchTask]:
        tasks: list[ResearchTask] = []
        company = ctx.company.name

        cvent = ctx.upstream_result(SignalType.CVENT)
        volume = ctx.upstream_result(SignalType.EVENT_VOLUME)
        budget = ctx.upstream_result(SignalType.BUDGET)

        # Gap 1 — Cvent uncertain: confidence low OR value in the ambiguous band.
        if cvent and (cvent.confidence < CONFIDENCE_THRESHOLD
                      or 0.0 < cvent.value < 0.5):
            tasks.append(ResearchTask(
                SignalType.CVENT,
                f"Does {company} use Cvent for event registration and management? "
                f"Find their event registration pages and upcoming events.",
                provider="perplexity",
                reason=f"cvent confidence {cvent.confidence:.2f} < {CONFIDENCE_THRESHOLD}",
            ))

        # Gap 2 — event volume uncertain or unknown.
        vol_payload = ctx.upstream_payload(SignalType.EVENT_VOLUME)
        if volume and (volume.confidence < 0.5
                       or vol_payload.get("estimated_events_per_year") is None):
            tasks.append(ResearchTask(
                SignalType.EVENT_VOLUME,
                f"{company} annual conferences events webinars schedule how many per year",
                provider="tavily",
                reason="event volume uncertain / unknown",
            ))

        # Gap 3 — budget estimate low-confidence.
        if budget and budget.confidence < 0.5:
            tasks.append(ResearchTask(
                SignalType.BUDGET,
                f"{company} event marketing budget spend sponsorship conference investment",
                provider="tavily",
                reason="budget confidence below threshold",
            ))

        return tasks

    async def _collect(self, ctx: AgentContext) -> AgentResult:
        plan = self._plan(ctx)

        # No gaps -> spend nothing. This is the common, cheap path.
        if not plan:
            return AgentResult(
                signal_type=self.signal_type, status=AgentStatus.SKIPPED,
                value=0.0, confidence=1.0,
                payload={"gaps": 0, "skipped_reason": "all signals above threshold"},
            )

        # cheapest-first so the budget cap protects the expensive providers
        plan.sort(key=lambda t: t.cost)

        spent = 0.0
        evidence: list[EvidenceItem] = []
        providers: list[str] = []
        findings: list[dict] = []

        for task in plan:
            if spent + task.cost > MAX_RESEARCH_BUDGET_USD:
                logger.info("[targeted_research] budget cap hit, skipping %s", task.signal.value)
                findings.append({"signal": task.signal.value, "skipped": "budget_cap"})
                continue

            try:
                items = await self._execute(task, ctx)
            except Exception as exc:                       # fallback: never fatal
                logger.warning("[targeted_research] %s failed: %s", task.provider, exc)
                items = []

            # Fallback ladder: if the chosen provider returned nothing, try Tavily.
            if not items and task.provider != "tavily" and self.settings.tavily_api_key:
                try:
                    items = await self._execute(
                        ResearchTask(task.signal, task.query, "tavily", task.reason), ctx
                    )
                    spent += _PROVIDER_COST["tavily"]
                    providers.append("tavily")
                except Exception:
                    pass

            spent += task.cost
            providers.append(task.provider)
            evidence.extend(items)
            findings.append({
                "signal": task.signal.value, "provider": task.provider,
                "reason": task.reason, "results": len(items),
            })

        confidence = 0.8 if evidence else 0.4
        return AgentResult(
            signal_type=self.signal_type, status=AgentStatus.OK,
            value=min(1.0, len(evidence) / 6),
            confidence=confidence,
            payload={"gaps": len(plan), "findings": findings,
                     "research_cost_usd": round(spent, 4)},
            evidence=evidence, providers=sorted(set(providers)),
            cost_usd=round(spent, 4),
        )

    # ── provider execution (each call deduped via CallCache) ───────────────
    async def _execute(self, task: ResearchTask, ctx: AgentContext) -> list[EvidenceItem]:
        if task.provider == "perplexity" and self.settings.perplexity_api_key:
            from app.tools.perplexity import research_deep
            data = await self.call(
                provider="perplexity", dedup_key=task.query,
                factory=lambda: research_deep(task.query, self.settings.perplexity_api_key,
                                              model="sonar-pro"),
                ttl_s=86_400,
            )
            answer = (data or {}).get("answer") or ""
            if not answer:
                return []
            return [EvidenceItem(
                claim=answer[:500], signal_type=task.signal,
                source_type=SourceType.LLM_INFERENCE, source_provider="perplexity",
                source_url=(data.get("citations") or [None])[0],
                raw_snippet=answer[:1000], confidence=0.75,
                raw_data={"citations": data.get("citations", [])},
            )]

        if task.provider == "tavily" and self.settings.tavily_api_key:
            from app.tools.web_search import search_web
            results = await self.call(
                provider="tavily", dedup_key=task.query,
                factory=lambda: search_web(task.query,
                                           tavily_api_key=self.settings.tavily_api_key,
                                           firecrawl_api_key="", max_results=4),
                ttl_s=43_200,
            )
            return [EvidenceItem(
                claim=(getattr(r, "title", "") or task.query)[:500],
                signal_type=task.signal, source_type=SourceType.SEARCH,
                source_provider="tavily", source_url=getattr(r, "url", None),
                raw_snippet=(getattr(r, "content", "") or "")[:1000],
                confidence=0.65,
            ) for r in (results or [])[:4] if getattr(r, "url", None)]

        if task.provider == "firecrawl" and self.settings.firecrawl_api_key:
            from app.tools.web_search import scrape_url
            md = await self.call(
                provider="firecrawl", dedup_key=task.query,
                factory=lambda: scrape_url(task.query, self.settings.firecrawl_api_key),
                ttl_s=86_400,
            )
            if not md:
                return []
            return [EvidenceItem(
                claim=f"Scraped page for {task.signal.value}", signal_type=task.signal,
                source_type=SourceType.SCRAPE, source_provider="firecrawl",
                source_url=task.query, raw_snippet=md[:1000], confidence=0.7,
            )]
        return []


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

        # compact, evidence-grounded context for the model
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
