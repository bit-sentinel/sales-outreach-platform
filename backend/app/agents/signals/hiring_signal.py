"""
HiringSignalAgent — detects active event/ops team hiring as a workload pressure proxy.

Data flow:
  1. Tavily → "{company} jobs event manager coordinator site:linkedin.com"
  2. Keyword scan on job titles in snippets — NO LLM required

Scoring (pure rule-based, deterministic):
  - 4+ matching roles:  1.00
  - 3 matching roles:   0.80
  - 2 matching roles:   0.60
  - 1 matching role:    0.35
  - 0 matching roles:   0.00
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.signals.base_signal import BaseSignalAgent, SignalResult

logger = logging.getLogger(__name__)

# Keywords that indicate event/operations hiring pressure
_SIGNAL_KEYWORDS = [
    "event coordinator", "event manager", "events manager", "event specialist",
    "event planner", "event producer", "event operations", "event marketing",
    "field marketing manager", "field marketing coordinator",
    "conference manager", "conference coordinator",
    "meeting planner", "meeting coordinator",
    "virtual events", "cvent", "registration manager",
    "trade show", "tradeshow", "expo coordinator",
]
# Compile once
_KW_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in _SIGNAL_KEYWORDS),
    re.IGNORECASE,
)


def _count_matches(texts: list[str]) -> list[str]:
    matched: set[str] = set()
    for text in texts:
        for m in _KW_PATTERN.finditer(text):
            matched.add(m.group(0).lower())
    return sorted(matched)


def _score_from_matches(matches: list[str]) -> float:
    n = len(matches)
    if n >= 4:
        return 1.00
    if n == 3:
        return 0.80
    if n == 2:
        return 0.60
    if n == 1:
        return 0.35
    return 0.00


class HiringSignalAgent(BaseSignalAgent):
    signal_type = "hiring_signal"

    async def collect(
        self,
        company_name: str,
        domain: str | None = None,
        **kwargs: Any,
    ) -> SignalResult:
        settings = self.settings
        texts: list[str] = []
        job_snippets: list[dict] = []

        if settings.tavily_api_key and company_name:
            try:
                from app.tools.web_search import search_web
                # Two targeted queries to maximise coverage
                queries = [
                    f"{company_name} hiring event manager coordinator jobs",
                    f'"{company_name}" "event coordinator" OR "event manager" OR "cvent" jobs',
                ]
                import asyncio
                all_results = await asyncio.gather(*[
                    search_web(q, tavily_api_key=settings.tavily_api_key,
                               firecrawl_api_key=None, max_results=4)
                    for q in queries
                ])
                seen_urls: set[str] = set()
                for results in all_results:
                    for r in results:
                        url = getattr(r, "url", "") or ""
                        content = getattr(r, "content", "") or ""
                        title = getattr(r, "title", "") or ""
                        if url not in seen_urls:
                            seen_urls.add(url)
                            texts.append(f"{title} {content}")
                            job_snippets.append({"title": title, "url": url, "snippet": content[:200]})
            except Exception as exc:
                logger.warning("[hiring_signal] Tavily failed: %s", exc)

        matches = _count_matches(texts)
        value = _score_from_matches(matches)

        evidence = {
            "matched_keywords": matches,
            "match_count": len(matches),
            "job_snippets": job_snippets[:4],
            "queries_run": 2 if settings.tavily_api_key else 0,
        }

        return SignalResult(
            signal_type=self.signal_type,
            value=value,
            evidence=evidence,
            provider="tavily",
            confidence=0.85 if texts else 0.4,
        )
