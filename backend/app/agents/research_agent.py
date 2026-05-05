"""
Web Research Agent – gathers intelligence about companies and contacts.

Uses SerpAPI, Firecrawl, and Tavily to find relevant web data.
"""

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
    events_attended: list[EventAttended] = Field(
        description="Events the company has attended, hosted, or sponsored — include both past (with year) and upcoming/recurring industry events"
    )
    competitor_info: list[str] = Field(description="Known competitors")
    relevance_score: float = Field(description="0-1 relevance score for outreach")


RESEARCH_SYSTEM_PROMPT = """You are an expert B2B sales research analyst. Your job is to gather 
comprehensive intelligence about a company and its key decision-makers to support personalized 
sales outreach.

Given a company name and domain, you will:
1. Find the company's recent news, press releases, and announcements
2. Identify key decision-makers and their roles
3. Understand the company's technology stack and integrations
4. Discover events they have attended, hosted, or sponsored — including PAST events (with years) 
   and UPCOMING/RECURRING industry events they are likely to attend. For each event include: 
   the event name, year (integer), month or season if known, whether it is past or upcoming,  
   their role (attendee/sponsor/host/speaker/unknown), and whether it is confirmed.
5. Identify buying signals (hiring, expansion, new products, funding)
6. Assess relevance for outreach

Be thorough but concise. Focus on actionable intelligence that helps craft personalized outreach.
Return your findings as structured JSON.
"""


class ResearchAgent(BaseAgent):
    """Conducts web research on companies and contacts."""

    async def run(
        self,
        lead_id: str,
        tenant_id: str,
        company_name: str | None = None,
        domain: str | None = None,
        contact_name: str | None = None,
    ) -> dict[str, Any]:
        llm = self.get_llm(temperature=0.3)
        parser = JsonOutputParser(pydantic_object=ResearchOutput)

        # Build search queries
        queries = []
        if company_name:
            queries.append(f"{company_name} company news recent")
            queries.append(f"{company_name} events Cvent")
            queries.append(f"{company_name} technology stack")
        if domain:
            queries.append(f"site:{domain}")
        if contact_name and company_name:
            queries.append(f"{contact_name} {company_name} LinkedIn")

        # Execute all web searches in parallel (both Tavily + Firecrawl run per query)
        import asyncio
        from app.tools.web_search import search_web, scrape_url
        settings = self.settings

        if queries:
            results_per_query = await asyncio.gather(*[
                search_web(
                    q,
                    tavily_api_key=settings.tavily_api_key,
                    firecrawl_api_key=settings.firecrawl_api_key,
                    max_results=5,
                )
                for q in queries
            ])
            search_results = [r for results in results_per_query for r in results]
        else:
            search_results = []

        # Deep-scrape top Tavily URLs with Firecrawl for full-page content
        if settings.firecrawl_api_key:
            # Collect top unique URLs from Tavily results (max 3 to control latency)
            tavily_urls = []
            seen = set()
            for r in search_results:
                if r.source == "tavily" and r.url and r.url not in seen:
                    seen.add(r.url)
                    tavily_urls.append(r.url)
                    if len(tavily_urls) >= 3:
                        break

            # Also include the homepage if domain is known
            if domain:
                homepage_url = f"https://{domain}" if not domain.startswith("http") else domain
                if homepage_url not in seen:
                    tavily_urls.append(homepage_url)

            if tavily_urls:
                scraped_pages = await asyncio.gather(*[
                    scrape_url(u, settings.firecrawl_api_key) for u in tavily_urls
                ])
                for url, md in zip(tavily_urls, scraped_pages):
                    if md:
                        search_results.append(
                            type("_R", (), {
                                "title": f"Full page: {url}",
                                "url": url,
                                "content": md[:3000],
                                "source": "firecrawl_scrape",
                            })()
                        )

        # Synthesize with LLM
        if search_results:
            research_context = "\n\n".join(
                f"[{r.source}] {r.title}\nURL: {r.url}\n{r.content[:500]}"
                for r in search_results
            )
        else:
            research_context = "No search results available. Synthesize from training knowledge only."

        messages = [
            SystemMessage(content=RESEARCH_SYSTEM_PROMPT),
            HumanMessage(content=f"""
Research the following company:
- Company: {company_name or 'Unknown'}
- Domain: {domain or 'Unknown'}
- Contact: {contact_name or 'Unknown'}

Web search results:
{research_context}

{parser.get_format_instructions()}
"""),
        ]

        result = await self.invoke_with_retry(llm, messages)
        try:
            parsed = parser.parse(result.content)
        except Exception:
            parsed = {"raw_response": result.content, "parse_error": True}

        return parsed
