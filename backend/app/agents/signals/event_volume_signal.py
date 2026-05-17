"""
EventVolumeSignalAgent — estimates the annual event program scale for a company.

Data flow:
  1. Tavily → "{company} annual events conference webinar schedule"
  2. Perplexity (if key available) → "How many events does {company} run per year?"
  3. Haiku LLM → extract events_per_year estimate and program_complexity

Scoring (rule-based, deterministic):
  - >20 events/year OR multi-track / expo: 1.00
  - 12-20 events/year OR complex Flex program: 0.80
  -  6-12 events/year:  0.60
  -  2-5  events/year:  0.40
  -  1    event/year :  0.25
  - No evidence found:  0.10  (assumption: some event activity exists since they use Cvent)
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.signals.base_signal import BaseSignalAgent, SignalResult

logger = logging.getLogger(__name__)

_COMPLEXITY_BOOST = {"complex": 0.15, "medium": 0.05, "simple": 0.0}


def _score_volume(events_per_year: int | None, complexity: str) -> float:
    boost = _COMPLEXITY_BOOST.get((complexity or "").lower(), 0.0)
    if events_per_year is None:
        return 0.10

    if events_per_year > 20:
        base = 1.00
    elif events_per_year >= 12:
        base = 0.80
    elif events_per_year >= 6:
        base = 0.60
    elif events_per_year >= 2:
        base = 0.40
    else:
        base = 0.25

    return min(1.0, base + boost)


class EventVolumeSignalAgent(BaseSignalAgent):
    signal_type = "event_volume"

    async def collect(
        self,
        company_name: str,
        domain: str | None = None,
        cvent_evidence: dict | None = None,
        **kwargs: Any,
    ) -> SignalResult:
        settings = self.settings
        snippets: list[str] = []
        providers_used: list[str] = []

        # Seed: if CventSignalAgent already found N confirmed events, that's
        # a floor for the volume estimate (don't re-query if we already have data).
        cvent_confirmed = (cvent_evidence or {}).get("total_pages_found", 0)

        # ── Tavily general search ─────────────────────────────────────────────
        if settings.tavily_api_key and company_name:
            try:
                from app.tools.web_search import search_web
                results = await search_web(
                    f"{company_name} annual events conference webinar schedule calendar",
                    tavily_api_key=settings.tavily_api_key,
                    firecrawl_api_key=None,
                    max_results=5,
                )
                for r in results:
                    content = getattr(r, "content", "") or ""
                    if content:
                        snippets.append(f"[tavily] {getattr(r, 'title', '')}\n{content[:400]}")
                providers_used.append("tavily")
            except Exception as exc:
                logger.warning("[event_volume] Tavily failed: %s", exc)

        # ── Perplexity deep research (optional) ──────────────────────────────
        if settings.perplexity_api_key and company_name:
            try:
                from app.tools.perplexity import research_deep
                query = (
                    f"How many events does {company_name} run per year? "
                    f"Include conferences, webinars, roadshows, user groups, and virtual events. "
                    f"Estimate annual event volume and describe the complexity of their event program."
                )
                deep = await research_deep(query, settings.perplexity_api_key, model="sonar")
                if deep.get("answer"):
                    snippets.append(f"[perplexity] {deep['answer'][:600]}")
                providers_used.append("perplexity")
            except Exception as exc:
                logger.warning("[event_volume] Perplexity failed: %s", exc)

        # ── Haiku extraction ─────────────────────────────────────────────────
        events_per_year: int | None = cvent_confirmed if cvent_confirmed else None
        complexity = "simple"

        if snippets and settings.anthropic_api_key:
            try:
                llm = self.get_haiku(temperature=0.0)
                context = "\n\n".join(snippets[:6])
                prompt = (
                    f"Based on the research below about {company_name}, estimate their annual event program.\n"
                    "Return JSON only: {\"events_per_year\": <integer or null>, "
                    "\"complexity\": \"simple|medium|complex\", "
                    "\"event_types\": [<list of strings>], "
                    "\"reasoning\": \"<one sentence>\"}\n\n"
                    f"Research:\n{context}"
                )
                from langchain_core.messages import HumanMessage
                import json, re
                response = await llm.ainvoke([HumanMessage(content=prompt)])
                raw = response.content or ""
                json_match = re.search(r"\{.*\}", raw, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    raw_epy = parsed.get("events_per_year")
                    if raw_epy is not None:
                        try:
                            events_per_year = max(int(raw_epy), cvent_confirmed or 0)
                        except (ValueError, TypeError):
                            pass
                    complexity = str(parsed.get("complexity", "simple")).lower()
                    event_types = parsed.get("event_types", [])
                    reasoning = parsed.get("reasoning", "")
                else:
                    event_types, reasoning = [], ""
            except Exception as exc:
                logger.warning("[event_volume] Haiku extraction failed: %s", exc)
                event_types, reasoning = [], ""
        else:
            event_types, reasoning = [], ""

        value = _score_volume(events_per_year, complexity)

        evidence = {
            "events_per_year": events_per_year,
            "complexity": complexity,
            "event_types": event_types[:8],
            "reasoning": reasoning,
            "cvent_pages_seeded": cvent_confirmed,
            "snippet_count": len(snippets),
        }

        return SignalResult(
            signal_type=self.signal_type,
            value=value,
            evidence=evidence,
            provider=",".join(providers_used) if providers_used else "none",
            confidence=0.8 if events_per_year is not None else 0.3,
        )
