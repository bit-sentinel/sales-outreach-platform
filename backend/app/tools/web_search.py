"""
Web search tool — wraps Tavily and Firecrawl with a unified interface.

Both providers are run in parallel when available:
  - Tavily  (AI-summarised search results, best for broad queries)
  - Firecrawl  (full-page content extraction, best for deep page scraping)

`search_web(query)` runs both providers concurrently, merges, and deduplicates
results by URL.  Individual provider failures are swallowed so the pipeline
continues with partial results.

`scrape_url(url)` extracts full-page markdown for a single URL via Firecrawl.
"""

import logging

from app.tools.search_types import SearchResult

logger = logging.getLogger(__name__)


# ── Tavily ────────────────────────────────────────────────────────────────────

async def _search_tavily(query: str, api_key: str, max_results: int = 5) -> list[SearchResult]:
    """Search using Tavily AI search API."""
    try:
        from tavily import AsyncTavilyClient
        client = AsyncTavilyClient(api_key=api_key)
        response = await client.search(
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=False,
            include_raw_content=False,
        )
        results = []
        for r in response.get("results", []):
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
                source="tavily",
                raw=r,
            ))
        return results
    except Exception as e:
        logger.warning("Tavily search failed for %r: %s", query, e)
        return []


# ── Firecrawl ─────────────────────────────────────────────────────────────────

async def _search_firecrawl(query: str, api_key: str, max_results: int = 5) -> list[SearchResult]:
    """Search using Firecrawl's search endpoint."""
    try:
        import asyncio
        from firecrawl import FirecrawlApp
        app = FirecrawlApp(api_key=api_key)
        # firecrawl-py is sync; run in thread pool to stay async-friendly
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: app.search(query, params={"limit": max_results}),
        )
        # firecrawl-py returns a list directly or {"data": [...]} depending on version
        items = response if isinstance(response, list) else (response.get("data") or [])
        results = []
        for r in items:
            results.append(SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("markdown") or r.get("description") or "",
                source="firecrawl",
                raw=r,
            ))
        return results
    except Exception as e:
        logger.warning("Firecrawl search failed for %r: %s", query, e)
        return []


async def scrape_url(url: str, api_key: str) -> str:
    """Scrape a single URL to markdown via Firecrawl.  Returns empty string on failure."""
    try:
        import asyncio
        from firecrawl import FirecrawlApp
        app = FirecrawlApp(api_key=api_key)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: app.scrape_url(url, params={"formats": ["markdown"]}),
        )
        return response.get("markdown", "")
    except Exception as e:
        logger.warning("Firecrawl scrape failed for %s: %s", url, e)
        return ""


# ── Public API ────────────────────────────────────────────────────────────────

async def search_web(
    query: str,
    *,
    tavily_api_key: str = "",
    firecrawl_api_key: str = "",
    max_results: int = 5,
) -> list[SearchResult]:
    """
    Run a web search using Tavily AND Firecrawl in parallel, then merge results.
    Results are deduplicated by URL and sorted by relevance score.
    Returns a list of SearchResult objects, or [] if no provider is configured.
    """
    import asyncio

    tasks = []
    if tavily_api_key:
        tasks.append(_search_tavily(query, tavily_api_key, max_results))
    if firecrawl_api_key:
        tasks.append(_search_firecrawl(query, firecrawl_api_key, max_results))

    if not tasks:
        logger.debug("No search provider configured for %r", query)
        return []

    results_list = await asyncio.gather(*tasks, return_exceptions=False)

    # Merge and deduplicate by URL; prefer higher-scored entry when URL duplicates
    seen_urls: dict[str, SearchResult] = {}
    no_url: list[SearchResult] = []
    for results in results_list:
        for r in results:
            if not r.url:
                no_url.append(r)
            elif r.url in seen_urls:
                # Keep the entry with the higher score (Tavily usually wins)
                if r.score > seen_urls[r.url].score:
                    seen_urls[r.url] = r
            else:
                seen_urls[r.url] = r

    combined = list(seen_urls.values()) + no_url
    combined.sort(key=lambda r: r.score, reverse=True)
    return combined
