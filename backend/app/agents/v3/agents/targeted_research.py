"""
TargetedResearchAgent — the cost-optimization layer.

The pipeline overuses Perplexity + Firecrawl because it researches every lead
the same way. This agent does the opposite: it researches NOTHING by default,
inspects upstream confidence, and spends only on the specific gaps that are
(a) below threshold and (b) worth the money — cheapest provider first, under
a per-lead cap and a global daily circuit breaker.

  decision tree     -> _build_directives()
  cost optimization -> tiered providers, budget cap, circuit breaker, neg-cache
  fallback logic    -> _execute_with_fallback() provider ladder
  queue handling    -> Stage 6 routed to enrich.research, rate-limited
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.agents.v3.base import BaseIntelligenceAgent
from app.agents.v3.contracts import (
    AgentContext, AgentResult, AgentStatus, EvidenceItem, PipelineStage,
    SignalType, SourceType,
)
from app.agents.v3.registry import register_agent

logger = logging.getLogger(__name__)


# ── Tunable thresholds & cost knobs ────────────────────────────────────────
@dataclass(frozen=True)
class ResearchPolicy:
    cvent_conf_threshold: float = 0.60        # below -> deep cvent research
    cvent_ambiguous_band: tuple = (0.0, 0.5)  # value in this open band == uncertain
    volume_conf_threshold: float = 0.50
    budget_conf_threshold: float = 0.50
    hiring_conf_threshold: float = 0.50

    per_lead_budget_usd: float = 0.08         # hard cap per lead
    daily_budget_usd: float = 25.0            # global circuit breaker
    min_score_impact: float = 0.05            # skip gaps that barely move the score

    neg_cache_ttl_s: int = 86_400             # remember "found nothing" for 24h


POLICY = ResearchPolicy()

# Provider cost (USD). Cheapest is always tried first.
_PROVIDER_COST = {"tavily": 0.005, "serpapi": 0.010,
                  "perplexity": 0.012, "firecrawl": 0.011}


@dataclass
class ResearchDirective:
    """One planned research action emitted by the decision tree."""
    signal: SignalType
    query: str
    reason: str
    score_impact: float                       # 0..1 — how much closing this gap matters
    provider_ladder: list[str] = field(default_factory=list)

    @property
    def min_cost(self) -> float:
        return min((_PROVIDER_COST[p] for p in self.provider_ladder), default=0.01)

    @property
    def value_ratio(self) -> float:
        """Impact per dollar — drives prioritization under the cap."""
        return self.score_impact / max(self.min_cost, 1e-4)


@register_agent
class TargetedResearchAgent(BaseIntelligenceAgent):
    signal_type = SignalType.TARGETED_RESEARCH
    stage = PipelineStage.INTELLIGENCE.value
    cache_ttl_hours = 72
    timeout_s = 90.0
    max_attempts = 2

    # ── 1. DECISION TREE ───────────────────────────────────────────────────
    def _build_directives(self, ctx: AgentContext) -> list[ResearchDirective]:
        """
        Inspect upstream confidence and emit research directives only for gaps.
        Each branch is a documented rule; no branch fires => zero spend.
        """
        directives: list[ResearchDirective] = []
        company = ctx.company.name

        cvent = ctx.upstream_result(SignalType.CVENT)
        volume = ctx.upstream_result(SignalType.EVENT_VOLUME)
        budget = ctx.upstream_result(SignalType.BUDGET)
        hiring = ctx.upstream_result(SignalType.HIRING)
        outsourcing = ctx.upstream_result(SignalType.OUTSOURCING)

        lo, hi = POLICY.cvent_ambiguous_band

        # Branch 1 — Cvent uncertain: low confidence OR value in the ambiguous band.
        if cvent and (cvent.confidence < POLICY.cvent_conf_threshold
                      or lo < cvent.value < hi):
            directives.append(ResearchDirective(
                signal=SignalType.CVENT,
                query=(f"Does {company} use Cvent for event registration and "
                       f"management? Find registration pages and upcoming events."),
                reason=f"cvent confidence {cvent.confidence:.2f} < "
                       f"{POLICY.cvent_conf_threshold} or value ambiguous",
                score_impact=0.30,                        # cvent is the heaviest signal
                provider_ladder=["perplexity", "tavily"],
            ))

        # Branch 2 — event volume uncertain or unknown.
        vol_p = ctx.upstream_payload(SignalType.EVENT_VOLUME)
        if volume and (volume.confidence < POLICY.volume_conf_threshold
                       or vol_p.get("estimated_events_per_year") is None):
            directives.append(ResearchDirective(
                signal=SignalType.EVENT_VOLUME,
                query=(f"{company} annual conferences events webinars schedule — "
                       f"how many events per year"),
                reason="event volume uncertain / unknown",
                score_impact=0.20,
                provider_ladder=["tavily", "serpapi"],    # cheap is enough here
            ))

        # Branch 3 — budget estimate low-confidence.
        if budget and budget.confidence < POLICY.budget_conf_threshold:
            directives.append(ResearchDirective(
                signal=SignalType.BUDGET,
                query=f"{company} event marketing budget sponsorship spend",
                reason="budget confidence below threshold",
                score_impact=0.07,
                provider_ladder=["tavily"],
            ))

        # Branch 4 — hiring weak BUT outsourcing looks promising: confirm the
        # capacity gap before paying for Stage-6 outreach generation.
        if (hiring and hiring.confidence < POLICY.hiring_conf_threshold
                and outsourcing and outsourcing.value >= 0.5):
            directives.append(ResearchDirective(
                signal=SignalType.HIRING,
                query=f"{company} hiring event manager coordinator cvent jobs",
                reason="hiring signal weak but outsourcing propensity high",
                score_impact=0.13,
                provider_ladder=["serpapi", "tavily"],
            ))

        # Cost optimization: drop low-impact gaps entirely.
        return [d for d in directives if d.score_impact >= POLICY.min_score_impact]

    # ── 2. EXECUTION with cost cap + circuit breaker ───────────────────────
    async def _collect(self, ctx: AgentContext) -> AgentResult:
        directives = self._build_directives(ctx)

        # Common cheap path: every signal already confident -> spend $0.
        if not directives:
            return AgentResult(
                signal_type=self.signal_type, status=AgentStatus.SKIPPED,
                value=0.0, confidence=1.0,
                payload={"gaps": 0, "reason": "all signals above threshold"},
            )

        # Global daily circuit breaker — protect the monthly API bill.
        if await self._daily_budget_exhausted():
            logger.warning("[targeted_research] daily research budget exhausted")
            return AgentResult(
                signal_type=self.signal_type, status=AgentStatus.PARTIAL,
                value=0.0, confidence=0.3,
                payload={"gaps": len(directives), "reason": "daily_circuit_breaker"},
            )

        # Prioritize by impact-per-dollar; run within the per-lead cap.
        directives.sort(key=lambda d: d.value_ratio, reverse=True)

        spent = 0.0
        evidence: list[EvidenceItem] = []
        providers: set[str] = set()
        findings: list[dict] = []

        for d in directives:
            if spent + d.min_cost > POLICY.per_lead_budget_usd:
                findings.append({"signal": d.signal.value, "skipped": "per_lead_cap"})
                continue

            items, used, cost = await self._execute_with_fallback(d, ctx)
            spent += cost
            providers.update(used)
            evidence.extend(items)
            findings.append({
                "signal": d.signal.value, "reason": d.reason,
                "providers_used": used, "results": len(items),
                "cost_usd": round(cost, 4),
            })

        await self._record_spend(spent)

        return AgentResult(
            signal_type=self.signal_type, status=AgentStatus.OK,
            value=min(1.0, len(evidence) / 6),
            confidence=0.8 if evidence else 0.4,
            payload={"gaps": len(directives), "findings": findings,
                     "research_cost_usd": round(spent, 4)},
            evidence=evidence, providers=sorted(providers),
            cost_usd=round(spent, 4),
        )

    # ── 3. FALLBACK LADDER ─────────────────────────────────────────────────
    async def _execute_with_fallback(
        self, d: ResearchDirective, ctx: AgentContext,
    ) -> tuple[list[EvidenceItem], list[str], float]:
        """
        Walk the provider ladder cheapest-first. Stop at the first provider that
        returns usable evidence. Empty/failed providers fall through to the next.
        Negative results are cached so a re-run within TTL spends nothing.
        """
        used: list[str] = []
        cost = 0.0

        neg_key = f"v3:negcache:{d.signal.value}:{_norm(d.query)}"
        if await self._neg_cache_hit(neg_key):
            return [], ["neg_cache"], 0.0

        ladder = sorted(d.provider_ladder, key=lambda p: _PROVIDER_COST.get(p, 1.0))
        for provider in ladder:
            if not self._provider_available(provider):
                continue
            try:
                items = await self._call_provider(provider, d, ctx)
            except Exception as exc:                       # provider error -> next
                logger.warning("[targeted_research] %s failed (%s) -> fallback",
                                provider, exc)
                continue

            used.append(provider)
            cost += _PROVIDER_COST.get(provider, 0.01)
            if items:                                      # success — stop the ladder
                return items, used, cost
            # empty result -> try the next (more capable) provider

        await self._neg_cache_set(neg_key)                 # ladder exhausted, nothing
        return [], used or ["none"], cost

    def _provider_available(self, provider: str) -> bool:
        s = self.settings
        return {
            "tavily": bool(s.tavily_api_key),
            "serpapi": bool(s.serpapi_api_key),
            "perplexity": bool(s.perplexity_api_key),
            "firecrawl": bool(s.firecrawl_api_key),
        }.get(provider, False)

    async def _call_provider(
        self, provider: str, d: ResearchDirective, ctx: AgentContext,
    ) -> list[EvidenceItem]:
        """Each call goes through CallCache -> duplicate calls never re-hit the API."""
        if provider == "perplexity":
            from app.tools.perplexity import research_deep
            data = await self.call(
                provider="perplexity", dedup_key=d.query,
                factory=lambda: research_deep(d.query, self.settings.perplexity_api_key,
                                              model="sonar-pro"),
                ttl_s=86_400,
            )
            ans = (data or {}).get("answer") or ""
            if not ans:
                return []
            citations = (data.get("citations") or [])
            return [EvidenceItem(
                claim=ans[:500], signal_type=d.signal,
                source_type=SourceType.LLM_INFERENCE, source_provider="perplexity",
                source_url=citations[0] if citations else None,
                raw_snippet=ans[:1000], confidence=0.75,
                raw_data={"citations": citations},
            )]

        if provider in ("tavily", "serpapi"):
            from app.tools.web_search import search_web
            results = await self.call(
                provider=provider, dedup_key=d.query,
                factory=lambda: search_web(
                    d.query, tavily_api_key=self.settings.tavily_api_key,
                    firecrawl_api_key="", max_results=4),
                ttl_s=43_200,
            )
            return [EvidenceItem(
                claim=(getattr(r, "title", "") or d.query)[:500], signal_type=d.signal,
                source_type=SourceType.SEARCH, source_provider=provider,
                source_url=getattr(r, "url", None),
                raw_snippet=(getattr(r, "content", "") or "")[:1000], confidence=0.65,
            ) for r in (results or [])[:4] if getattr(r, "url", None)]

        if provider == "firecrawl":
            from app.tools.web_search import scrape_url
            md = await self.call(
                provider="firecrawl", dedup_key=d.query,
                factory=lambda: scrape_url(d.query, self.settings.firecrawl_api_key),
                ttl_s=86_400,
            )
            return [EvidenceItem(
                claim=f"Scraped page for {d.signal.value}", signal_type=d.signal,
                source_type=SourceType.SCRAPE, source_provider="firecrawl",
                source_url=d.query, raw_snippet=md[:1000], confidence=0.7,
            )] if md else []
        return []

    # ── budget tracking via Redis (best-effort) ────────────────────────────
    async def _daily_budget_exhausted(self) -> bool:
        r = self.call_cache._redis
        if not r:
            return False
        try:
            spent = float(await r.get(self._daily_key()) or 0.0)
            return spent >= POLICY.daily_budget_usd
        except Exception:
            return False

    async def _record_spend(self, amount: float) -> None:
        r = self.call_cache._redis
        if not r or amount <= 0:
            return
        try:
            key = self._daily_key()
            await r.incrbyfloat(key, amount)
            await r.expire(key, 172_800)
        except Exception:
            pass

    async def _neg_cache_hit(self, key: str) -> bool:
        r = self.call_cache._redis
        if not r:
            return False
        try:
            return bool(await r.get(key))
        except Exception:
            return False

    async def _neg_cache_set(self, key: str) -> None:
        r = self.call_cache._redis
        if not r:
            return
        try:
            await r.setex(key, POLICY.neg_cache_ttl_s, "1")
        except Exception:
            pass

    @staticmethod
    def _daily_key() -> str:
        return f"v3:research:spend:{datetime.now(timezone.utc):%Y%m%d}"


def _norm(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())[:48]
