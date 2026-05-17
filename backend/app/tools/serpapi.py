"""SerpAPI helpers for targeted Google result collection."""

import logging

import httpx

from app.tools.search_types import SearchResult

logger = logging.getLogger(__name__)

SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"


def build_cvent_query(company_name: str, domain: str | None = None) -> str:
    """Build the Google query used to locate public Cvent event pages."""
    company_part = f'"{company_name}"' if company_name else "Cvent"
    if domain:
        return f'site:cvent.com ({company_part} OR "{domain}")'
    return f"site:cvent.com {company_part}"


async def search_google(query: str, api_key: str, num_results: int = 5) -> list[SearchResult]:
    """Run a Google query via SerpAPI and normalize the organic results."""
    if not api_key or not query:
        return []

    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": max(1, min(num_results, 10)),
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(SERPAPI_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("SerpAPI search failed for %r: %s", query, exc)
        return []

    results: list[SearchResult] = []
    for item in payload.get("organic_results") or []:
        position = item.get("position") or len(results) + 1
        score = 1.0 / float(position)
        results.append(
            SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                content=item.get("snippet", ""),
                source="serpapi",
                score=score,
                raw=item,
            )
        )
    return results


async def search_cvent_pages(
    company_name: str,
    api_key: str,
    *,
    domain: str | None = None,
    num_results: int = 5,
) -> list[SearchResult]:
    """Find public Cvent pages tied to a company."""
    query = build_cvent_query(company_name, domain)
    return await search_google(query, api_key, num_results=num_results)