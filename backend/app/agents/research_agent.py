"""Web research agent for Cvent-focused cold outreach."""

from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent


class EventAttended(BaseModel):
    event: str = Field(description="Name of the event")
    year: int | None = Field(default=None, description="Year the event occurred or is expected (e.g. 2024)")
    month: str | None = Field(default=None, description="Month or season (e.g. 'October', 'Spring')")
    date_label: str | None = Field(default=None, description="Human-readable date label e.g. 'Oct 2024', 'Spring 2025'")
    type: Literal["past", "upcoming", "recurring"] = Field(description="'past' for historical, 'upcoming' for future, 'recurring' for annual events")
    role: Literal["attendee", "sponsor", "host", "speaker", "unknown"] = Field(description="Company's role at the event")
    confirmed: bool = Field(description="True only if there is concrete evidence (press release, ticket, announcement); false if inferred")
    url: str | None = Field(default=None, description="URL to source or event page")
    description: str = Field(description="Brief description of the event and why it is relevant")


class ResearchOutput(BaseModel):
    company_summary: str = Field(description="2-3 sentence company summary")
    recent_news: list[dict] = Field(description="Recent news items with title, url, date, summary")
    key_people: list[dict] = Field(description="Key people with name, title, linkedin_url")
    technology_stack: list[str] = Field(description="Technologies used by the company")
    funding_info: dict | None = Field(description="Funding stage, amount, investors")
    industry_signals: list[str] = Field(description="Industry signals and triggers")
    buying_signals: list[str] = Field(description="Concrete signs that event work or outsourcing need may exist")
    events_attended: list[EventAttended] = Field(
        description="Events the company has attended, hosted, or sponsored — include both past (with year) and upcoming/recurring industry events"
    )
    cvent_event_pages: list[dict] = Field(
        description="Public Cvent event pages tied to the company with name, url, and a brief note"
    )
    personalization_hooks: list[str] = Field(
        description="Specific outreach hooks safe to use in cold email"
    )
    recommended_outreach_angle: str = Field(
        description="Best angle for a Cvent build-overflow outreach email"
    )
    competitor_info: list[str] = Field(description="Known competitors")
    relevance_score: float = Field(description="0-1 relevance score for outreach")


RESEARCH_SYSTEM_PROMPT = """You are an expert B2B sales research analyst supporting a cold outreach
program for Launch House Events, a firm that manages and builds events inside customers' existing
Cvent licenses.

Given a company name and domain, you will:
1. Find the company's recent news, press releases, and announcements
2. Identify key decision-makers and their roles
3. Understand the company's technology stack and integrations
4. Discover events they have attended, hosted, or sponsored — including PAST events (with years) 
   and UPCOMING/RECURRING industry events they are likely to attend. For each event include: 
   the event name, year (integer), month or season if known, whether it is past or upcoming,  
   their role (attendee/sponsor/host/speaker/unknown), and whether it is confirmed.
5. Identify buying signals that suggest the team may need Cvent build or event operations overflow
6. Extract 3-5 personalization hooks safe for cold email
7. Assess relevance for outreach

Be thorough but concise. Focus on actionable intelligence that helps craft personalized outreach.
Return your findings as structured JSON.
"""


def _unique_urls(results: list[Any], *, sources: set[str] | None = None, limit: int = 3) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for result in results:
        source = getattr(result, "source", None)
        url = getattr(result, "url", None)
        if not url or url in seen:
            continue
        if sources and source not in sources:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= limit:
            break
    return urls


class ResearchAgent(BaseAgent):
    """Conducts web research on companies and contacts."""

    async def run(
        self,
        lead_id: str,
        tenant_id: str,
        company_name: str | None = None,
        domain: str | None = None,
        contact_name: str | None = None,
        linkedin_url: str | None = None,
    ) -> dict[str, Any]:
        import asyncio

        llm = self.get_llm(temperature=0.3)
        parser = JsonOutputParser(pydantic_object=ResearchOutput)
        settings = self.settings

        queries = []
        if company_name:
            queries.append(f"{company_name} company news recent")
            queries.append(f"{company_name} event marketing team hiring")
            queries.append(f"{company_name} technology stack")
        if domain:
            queries.append(f"site:{domain}")
        if contact_name and company_name:
            queries.append(f"{contact_name} {company_name} LinkedIn")

        from app.tools.perplexity import research_deep
        from app.tools.serpapi import search_cvent_pages
        from app.tools.web_search import scrape_url, search_web

        search_tasks = [
            search_web(
                query,
                tavily_api_key=settings.tavily_api_key,
                firecrawl_api_key=settings.firecrawl_api_key,
                max_results=5,
            )
            for query in queries
        ]
        cvent_task = (
            search_cvent_pages(
                company_name,
                settings.serpapi_api_key,
                domain=domain,
                num_results=5,
            )
            if company_name and settings.serpapi_api_key
            else None
        )
        deep_query = None
        if company_name:
            deep_query = (
                f"Research {company_name} for a cold outreach program selling outsourced Cvent build "
                f"and event operations support. Find upcoming events, recurring event programs, hiring "
                f"signals, event team growth, recent news, and safe personalization hooks. Domain: {domain or 'unknown'}."
            )
        deep_task = (
            research_deep(deep_query, settings.perplexity_api_key)
            if deep_query and settings.perplexity_api_key
            else None
        )
        gathered = await asyncio.gather(
            asyncio.gather(*search_tasks) if search_tasks else asyncio.sleep(0, result=[]),
            cvent_task or asyncio.sleep(0, result=[]),
            deep_task or asyncio.sleep(0, result={}),
        )
        general_search_results = [
            result
            for per_query in gathered[0]
            for result in per_query
        ]
        cvent_results = gathered[1]
        deep_research = gathered[2]

        cvent_urls = _unique_urls(cvent_results, limit=3)
        general_urls = _unique_urls(general_search_results, sources={"tavily"}, limit=3)
        scrape_urls = cvent_urls + [url for url in general_urls if url not in cvent_urls]
        if domain:
            homepage_url = f"https://{domain}" if not domain.startswith("http") else domain
            if homepage_url not in scrape_urls:
                scrape_urls.append(homepage_url)

        scraped_pages: list[str] = []
        if settings.firecrawl_api_key and scrape_urls:
            scraped_pages = await asyncio.gather(*[
                scrape_url(url, settings.firecrawl_api_key) for url in scrape_urls
            ])

        combined_results = list(general_search_results) + list(cvent_results)
        cvent_pages: list[dict[str, Any]] = []
        for result, markdown in zip(cvent_results[: len(scraped_pages)], scraped_pages[: len(cvent_results)]):
            cvent_pages.append(
                {
                    "title": getattr(result, "title", ""),
                    "url": getattr(result, "url", ""),
                    "snippet": getattr(result, "content", "")[:300],
                    "page_excerpt": (markdown or "")[:1200],
                }
            )

        for url, markdown in zip(scrape_urls, scraped_pages):
            if markdown:
                combined_results.append(
                    type(
                        "_ScrapeResult",
                        (),
                        {
                            "title": f"Full page: {url}",
                            "url": url,
                            "content": markdown[:2500],
                            "source": "firecrawl_scrape",
                        },
                    )()
                )

        context_blocks = []
        if combined_results:
            context_blocks.append(
                "Web search results:\n" + "\n\n".join(
                    f"[{result.source}] {result.title}\nURL: {result.url}\n{result.content[:500]}"
                    for result in combined_results
                )
            )
        if cvent_pages:
            context_blocks.append(f"Public Cvent event pages:\n{cvent_pages}")
        if deep_research:
            context_blocks.append(f"Perplexity deep research:\n{deep_research}")

        research_context = "\n\n".join(context_blocks) or "No search results available."

        messages = [
            SystemMessage(content=RESEARCH_SYSTEM_PROMPT),
            HumanMessage(content=f"""
Research the following company:
- Company: {company_name or 'Unknown'}
- Domain: {domain or 'Unknown'}
- Contact: {contact_name or 'Unknown'}
- LinkedIn URL: {linkedin_url or 'Unknown'}

Research evidence:
{research_context}

{parser.get_format_instructions()}
"""),
        ]

        result = await self.invoke_with_retry(llm, messages)
        try:
            parsed = parser.parse(result.content)
        except Exception:
            parsed = {"raw_response": result.content, "parse_error": True}

        if not parsed.get("parse_error"):
            parsed["provider_context"] = {
                "deep_research": deep_research,
                "cvent_results": [
                    {
                        "title": getattr(result, "title", ""),
                        "url": getattr(result, "url", ""),
                        "content": getattr(result, "content", "")[:500],
                    }
                    for result in cvent_results
                ],
                "general_results": [
                    {
                        "title": getattr(result, "title", ""),
                        "url": getattr(result, "url", ""),
                        "source": getattr(result, "source", ""),
                    }
                    for result in general_search_results[:10]
                ],
            }

        return parsed
