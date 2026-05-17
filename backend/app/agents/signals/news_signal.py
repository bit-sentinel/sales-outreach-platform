"""
NewsSignalAgent — detects recent news that creates event-related urgency.

Data flow:
  1. Tavily → "{company} events news 2026"
  2. Keyword classification on snippets (fast, no LLM)
  3. Haiku LLM only if ambiguous / non-event result mix is high

Scoring (rule-based, deterministic):
  - Event news < 30 days:  1.00
  - Event news 30-90 days: 0.65
  - Non-event positive news < 30 days (growth/funding): 0.35
  - No relevant news:      0.00
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.agents.signals.base_signal import BaseSignalAgent, SignalResult

logger = logging.getLogger(__name__)

_EVENT_KEYWORDS = re.compile(
    r"\b(event|conference|summit|expo|webinar|symposium|forum|convention|"
    r"trade.?show|roadshow|seminar|workshop|launch|gala|award)\b",
    re.IGNORECASE,
)
_GROWTH_KEYWORDS = re.compile(
    r"\b(funding|raises|acquired|merger|expansion|launch|IPO|partnership|"
    r"new.?office|headcount|hire|growth|record.?revenue)\b",
    re.IGNORECASE,
)


def _classify_snippet(title: str, content: str) -> str:
    text = f"{title} {content}"
    if _EVENT_KEYWORDS.search(text):
        return "event"
    if _GROWTH_KEYWORDS.search(text):
        return "growth"
    return "other"


def _score_news(items: list[dict]) -> tuple[float, str]:
    event_items = [i for i in items if i.get("category") == "event"]
    growth_items = [i for i in items if i.get("category") == "growth"]

    def _min_age(subset: list[dict]) -> int | None:
        ages = [i["age_days"] for i in subset if i.get("age_days") is not None]
        return min(ages) if ages else None

    event_age = _min_age(event_items)
    growth_age = _min_age(growth_items)

    if event_age is not None and event_age < 30:
        return 1.00, f"event_news_{event_age}d_ago"
    if event_age is not None and event_age < 90:
        return 0.65, f"event_news_{event_age}d_ago"
    if growth_age is not None and growth_age < 30:
        return 0.35, f"growth_news_{growth_age}d_ago"
    if event_age is not None:
        return 0.20, f"event_news_{event_age}d_ago"
    return 0.00, "no_relevant_news"


class NewsSignalAgent(BaseSignalAgent):
    signal_type = "news_signal"

    async def collect(
        self,
        company_name: str,
        domain: str | None = None,
        **kwargs: Any,
    ) -> SignalResult:
        settings = self.settings
        news_items: list[dict] = []

        if settings.tavily_api_key and company_name:
            try:
                from app.tools.web_search import search_web
                results = await search_web(
                    f"{company_name} news events 2026",
                    tavily_api_key=settings.tavily_api_key,
                    firecrawl_api_key=None,
                    max_results=6,
                )
                now = datetime.now(timezone.utc)
                for r in results:
                    title = getattr(r, "title", "") or ""
                    content = getattr(r, "content", "") or ""
                    url = getattr(r, "url", "") or ""
                    raw = getattr(r, "raw", {}) or {}
                    # Tavily includes a published_date field
                    pub_date_str = raw.get("published_date") or raw.get("date")
                    age_days: int | None = None
                    if pub_date_str:
                        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
                                    "%Y-%m-%d", "%B %d, %Y"):
                            try:
                                pub_dt = datetime.strptime(pub_date_str[:19], fmt[:len(pub_date_str)]).replace(tzinfo=timezone.utc)
                                age_days = (now - pub_dt).days
                                break
                            except ValueError:
                                continue

                    category = _classify_snippet(title, content)
                    news_items.append({
                        "title": title,
                        "url": url,
                        "snippet": content[:200],
                        "age_days": age_days,
                        "category": category,
                    })
            except Exception as exc:
                logger.warning("[news_signal] Tavily failed: %s", exc)

        value, reason = _score_news(news_items)

        evidence = {
            "reason": reason,
            "total_articles": len(news_items),
            "event_articles": sum(1 for i in news_items if i["category"] == "event"),
            "growth_articles": sum(1 for i in news_items if i["category"] == "growth"),
            "top_items": [
                {"title": i["title"], "url": i["url"], "age_days": i["age_days"],
                 "category": i["category"]}
                for i in sorted(news_items, key=lambda x: x.get("age_days") or 9999)[:3]
            ],
        }

        return SignalResult(
            signal_type=self.signal_type,
            value=value,
            evidence=evidence,
            provider="tavily",
            confidence=0.80 if news_items else 0.3,
        )
