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

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from app.tools.search_types import SearchResult

logger = logging.getLogger(__name__)

# Firecrawl free-plan limits
_FC_RATE_LIMITS = {"scrape": 10, "search": 5}  # requests per minute
_FC_MAX_CONCURRENT = 2                           # concurrent browser sessions


@asynccontextmanager
async def _fc_throttle(endpoint: str):
    """Acquire a Firecrawl rate-limit slot before making an API call.

    Enforces two constraints via Redis so limits are shared across all Celery
    workers (not just within a single process):
      - Per-minute request cap (10 for /scrape, 5 for /search)
      - Max 2 concurrent browser sessions for /scrape
    Blocks until both constraints are satisfied, then yields.
    """
    try:
        import redis.asyncio as aioredis
        from app.config import get_settings
        r = aioredis.from_url(str(get_settings().redis_url), decode_responses=True)
    except Exception as exc:
        logger.warning("Firecrawl throttle: cannot connect to Redis (%s) — proceeding unthrottled", exc)
        yield
        return

    rate_limit = _FC_RATE_LIMITS.get(endpoint, 10)
    concur_acquired = False

    # Lua: atomically increment only when under the per-minute cap.
    # Returns new count on success, 0 when already at limit.
    _RATE_LUA = (
        "local c=redis.call('INCR',KEYS[1]) "
        "if c==1 then redis.call('EXPIRE',KEYS[1],70) end "
        "if c<=tonumber(ARGV[1]) then return c "
        "else redis.call('DECR',KEYS[1]) return 0 end"
    )
    # Lua: atomically increment concurrency counter only when under the cap.
    _CONCUR_LUA = (
        "local c=tonumber(redis.call('GET',KEYS[1]) or '0') "
        "if c<tonumber(ARGV[1]) then "
        "redis.call('INCR',KEYS[1]) redis.call('EXPIRE',KEYS[1],300) return 1 "
        "end return 0"
    )

    try:
        # ── 1. Per-minute rate limit ───────────────────────────────────────────
        while True:
            window = int(time.time()) // 60
            rate_key = f"fc:rate:{endpoint}:{window}"
            count = await r.eval(_RATE_LUA, 1, rate_key, rate_limit)
            if count:
                break
            wait = 60 - (int(time.time()) % 60) + 1
            logger.warning(
                "Firecrawl /%s at rate limit (%d req/min), waiting %ds for next window",
                endpoint, rate_limit, wait,
            )
            await asyncio.sleep(wait)

        # ── 2. Concurrency cap (scrape only, browsers are the bottleneck) ─────
        if endpoint == "scrape":
            while True:
                acquired = await r.eval(_CONCUR_LUA, 1, "fc:concurrent", _FC_MAX_CONCURRENT)
                if acquired:
                    concur_acquired = True
                    break
                logger.debug("Firecrawl: %d concurrent browser slots full, waiting 2s", _FC_MAX_CONCURRENT)
                await asyncio.sleep(2)

        yield

    finally:
        if concur_acquired:
            await r.decr("fc:concurrent")
        await r.aclose()


# ── Tavily ────────────────────────────────────────────────────────────────────

async def _search_tavily(query: str, api_key: str, max_results: int = 5) -> list[SearchResult]:
    """Search using Tavily AI search API."""
    try:
        from tavily import AsyncTavilyClient
        async with AsyncTavilyClient(api_key=api_key) as client:
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
        from firecrawl import FirecrawlApp
        app = FirecrawlApp(api_key=api_key)
        loop = asyncio.get_event_loop()
        async with _fc_throttle("search"):
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
        from firecrawl import FirecrawlApp
        app = FirecrawlApp(api_key=api_key)
        loop = asyncio.get_event_loop()
        async with _fc_throttle("scrape"):
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
