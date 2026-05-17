"""
CventSignalAgent — detects confirmed public Cvent event pages for a company.

Data flow:
  1. SerpAPI → site:cvent.com query → list of event page URLs + Google snippets
  2. Date extraction from snippets via regex (free, instant)
  3. Firecrawl scrape of up to 2 pages whose dates couldn't be inferred from snippets
  4. Haiku LLM → parse scraped markdown → extract structured event records
     (only called if scraping was needed AND anthropic key is set)

Scoring (rule-based, deterministic):
  - Has confirmed upcoming event  0-30 days:   1.00
  - Has confirmed upcoming event 31-120 days:  0.85
  - Has confirmed upcoming event 121-365 days: 0.50
  - Has Cvent pages but dates unclear / past:  0.25
  - No Cvent pages found:                      0.00
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.agents.signals.base_signal import BaseSignalAgent, SignalResult

logger = logging.getLogger(__name__)

# ISO / common date patterns to try against Google snippets
_DATE_PATTERNS = [
    r"\b(\d{4})-(\d{2})-(\d{2})\b",                              # 2026-08-14
    r"\b(\w+ \d{1,2},?\s*\d{4})\b",                              # August 14, 2026
    r"\b(\d{1,2} \w+ \d{4})\b",                                  # 14 August 2026
    r"\b(\w{3,9} \d{1,2}(?:-\d{1,2})?,?\s*\d{4})\b",            # Aug 14-16, 2026
]
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _try_parse_date(text: str) -> datetime | None:
    """Best-effort date extraction from a snippet string. Returns UTC datetime or None."""
    now = datetime.now(timezone.utc)
    for pattern in _DATE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            raw = match.group(0).strip().rstrip(",")
            # Try standard formats
            for fmt in ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y",
                        "%d %B %Y", "%d %b %Y", "%B %d-%d, %Y", "%b %d-%d, %Y"):
                try:
                    dt = datetime.strptime(raw.split("-")[0].strip(), fmt.split("-")[0].strip())
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            # Word-based: "August 14, 2026"
            parts = re.split(r"[\s,]+", raw)
            if len(parts) >= 3:
                month_str = parts[0].lower()[:3]
                month = _MONTHS.get(month_str) or _MONTHS.get(parts[-1].lower()[:3])
                year_candidates = [p for p in parts if re.match(r"^\d{4}$", p)]
                day_candidates = [p for p in parts if re.match(r"^\d{1,2}$", p)]
                if month and year_candidates and day_candidates:
                    try:
                        return datetime(int(year_candidates[0]), month, int(day_candidates[0]),
                                        tzinfo=timezone.utc)
                    except ValueError:
                        continue
    return None


def _days_until(dt: datetime) -> int:
    return (dt - datetime.now(timezone.utc)).days


def _score_events(events: list[dict]) -> tuple[float, str]:
    """Deterministic score from a list of extracted event dicts (each may have 'date_dt')."""
    upcoming = [e for e in events if e.get("days_until") is not None and e["days_until"] >= 0]
    if not upcoming:
        if events:
            return 0.25, "cvent_pages_found_past_events_only"
        return 0.00, "no_cvent_pages"

    soonest = min(e["days_until"] for e in upcoming)
    if soonest <= 30:
        return 1.00, f"upcoming_event_within_30d (soonest={soonest}d)"
    if soonest <= 120:
        return 0.85, f"upcoming_event_31_120d (soonest={soonest}d)"
    if soonest <= 365:
        return 0.50, f"upcoming_event_121_365d (soonest={soonest}d)"
    return 0.30, f"upcoming_event_over_365d (soonest={soonest}d)"


class CventSignalAgent(BaseSignalAgent):
    signal_type = "cvent_events"

    async def collect(
        self,
        company_name: str,
        domain: str | None = None,
        **kwargs: Any,
    ) -> SignalResult:
        settings = self.settings
        events: list[dict] = []
        pages_found: list[dict] = []

        # ── Step 1: SerpAPI ──────────────────────────────────────────────────
        if settings.serpapi_api_key and company_name:
            try:
                from app.tools.serpapi import search_cvent_pages
                results = await search_cvent_pages(
                    company_name, settings.serpapi_api_key, domain=domain, num_results=6
                )
                for r in results:
                    snippet = getattr(r, "content", "") or ""
                    title = getattr(r, "title", "") or ""
                    url = getattr(r, "url", "") or ""
                    dt = _try_parse_date(snippet) or _try_parse_date(title)
                    event: dict[str, Any] = {
                        "title": title,
                        "url": url,
                        "snippet": snippet[:300],
                        "date_source": "snippet",
                    }
                    if dt:
                        event["date_str"] = dt.strftime("%Y-%m-%d")
                        event["days_until"] = _days_until(dt)
                    pages_found.append(event)
                self._log("SerpAPI found %d Cvent pages", len(pages_found))
            except Exception as exc:
                logger.warning("[cvent_events] SerpAPI failed: %s", exc)

        # ── Step 2: Firecrawl scrape for pages whose dates are still unclear ─
        pages_needing_scrape = [p for p in pages_found if "days_until" not in p][:2]
        if pages_needing_scrape and settings.firecrawl_api_key:
            try:
                from app.tools.web_search import scrape_url
                scraped = await asyncio.gather(*[
                    scrape_url(p["url"], settings.firecrawl_api_key)
                    for p in pages_needing_scrape
                ])
                for page, markdown in zip(pages_needing_scrape, scraped):
                    if not markdown:
                        continue
                    # Try regex extraction first (fast)
                    dt = _try_parse_date(markdown[:3000])
                    if dt:
                        page["date_str"] = dt.strftime("%Y-%m-%d")
                        page["days_until"] = _days_until(dt)
                        page["date_source"] = "firecrawl_regex"
                        page["page_excerpt"] = markdown[:800]
                    elif settings.anthropic_api_key:
                        # Fallback: Haiku LLM extraction
                        page["_markdown"] = markdown[:2000]
                self._log("Firecrawl scraped %d pages", len(pages_needing_scrape))
            except Exception as exc:
                logger.warning("[cvent_events] Firecrawl scrape failed: %s", exc)

        # ── Step 3: Haiku LLM for any pages still without dates ─────────────
        pages_for_llm = [p for p in pages_found if "days_until" not in p and p.get("_markdown")]
        if pages_for_llm and settings.anthropic_api_key:
            try:
                llm = self.get_haiku(temperature=0.0)
                prompt = (
                    "Extract structured event data from these Cvent registration page excerpts.\n"
                    "For each page return a JSON array item: {\"title\": str, \"url\": str, "
                    "\"event_date\": \"YYYY-MM-DD or null\", \"is_upcoming\": bool}.\n"
                    "Only include events from the year 2025 onward.\n\n"
                )
                for p in pages_for_llm:
                    prompt += f"URL: {p['url']}\nExcerpt:\n{p.get('_markdown', '')[:800]}\n---\n"
                from langchain_core.messages import HumanMessage
                response = await llm.ainvoke([HumanMessage(content=prompt)])
                raw = response.content or ""
                # Parse JSON array from response
                import json
                json_match = re.search(r"\[.*\]", raw, re.DOTALL)
                if json_match:
                    extracted = json.loads(json_match.group(0))
                    for item in extracted:
                        url = item.get("url", "")
                        date_str = item.get("event_date")
                        for p in pages_for_llm:
                            if p["url"] == url and date_str:
                                try:
                                    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                                    p["date_str"] = date_str
                                    p["days_until"] = _days_until(dt)
                                    p["date_source"] = "haiku_llm"
                                except ValueError:
                                    pass
            except Exception as exc:
                logger.warning("[cvent_events] Haiku extraction failed: %s", exc)

        # Clean up internal keys before storing
        for p in pages_found:
            p.pop("_markdown", None)

        events = [p for p in pages_found if "days_until" in p]
        value, reason = _score_events(events)

        evidence = {
            "reason": reason,
            "total_pages_found": len(pages_found),
            "events_with_dates": len(events),
            "upcoming_count": sum(1 for e in events if e.get("days_until", -1) >= 0),
            "soonest_days": min((e["days_until"] for e in events if e.get("days_until", -1) >= 0), default=None),
            "events": events[:5],
        }

        return SignalResult(
            signal_type=self.signal_type,
            value=value,
            evidence=evidence,
            provider="serpapi,firecrawl",
            confidence=0.9 if events else 0.5,
        )
