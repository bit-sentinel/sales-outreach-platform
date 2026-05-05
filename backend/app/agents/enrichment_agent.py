"""
Enrichment Agent – enriches lead data with company and contact details.
"""

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent


class CompanyEnrichment(BaseModel):
    employee_count_range: str = Field(description="e.g., '51-200'")
    revenue_range: str = Field(description="e.g., '$10M-$50M'")
    industry: str = Field(description="Primary industry")
    sub_industry: str | None = Field(description="Sub-industry if identifiable")
    founded_year: int | None = Field(description="Year founded")
    headquarters: str | None = Field(description="HQ location")
    description: str = Field(description="1-2 sentence description")
    technologies: list[str] = Field(description="Key technologies used")


class ContactEnrichment(BaseModel):
    seniority: str = Field(description="C-level, VP, Director, Manager, etc.")
    department: str = Field(description="Sales, Marketing, IT, Events, etc.")
    likely_responsibilities: list[str] = Field(description="Key responsibilities")
    decision_maker: bool = Field(description="Whether they're likely a decision maker")
    buyer_persona: str = Field(description="Buyer persona category")


ENRICHMENT_SYSTEM_PROMPT = """You are a B2B data enrichment specialist. Given raw lead data and 
research findings, extract and structure key company and contact attributes.

Focus on:
1. Company firmographics (size, revenue, industry)
2. Contact demographics (seniority, department, decision-making authority)
3. Technology usage indicators
4. Buying signals and intent data
5. Fit scoring factors

Be precise and conservative – only include data you have reasonable confidence in.
"""


class EnrichmentAgent(BaseAgent):
    """Enriches leads with structured company and contact data."""

    async def run(
        self,
        lead_id: str,
        tenant_id: str,
        raw_data: dict | None = None,
        research_data: dict | None = None,
    ) -> dict[str, Any]:
        import asyncio
        from app.tools.web_search import search_web, scrape_url

        llm = self.get_llm(temperature=0.2)
        parser = JsonOutputParser()
        settings = self.settings

        # ── Live web lookups for firmographic data ────────────────────────────
        company_name: str = (raw_data or {}).get("company_name") or ""
        domain: str = (raw_data or {}).get("domain") or ""
        contact_name: str = (raw_data or {}).get("contact_name") or ""

        web_context = ""
        if company_name and (settings.tavily_api_key or settings.firecrawl_api_key):
            enrichment_queries = [
                f"{company_name} company size employees headcount",
                f"{company_name} funding investors raise series",
                f"{company_name} technology stack software tools integrations",
            ]
            if contact_name:
                enrichment_queries.append(f"{contact_name} {company_name} LinkedIn profile title role")

            results_per_query = await asyncio.gather(*[
                search_web(
                    q,
                    tavily_api_key=settings.tavily_api_key,
                    firecrawl_api_key=settings.firecrawl_api_key,
                    max_results=3,
                )
                for q in enrichment_queries
            ])
            all_results = [r for results in results_per_query for r in results]

            # Deep-scrape top URLs with Firecrawl for richer content
            if settings.firecrawl_api_key and all_results:
                top_urls = list({r.url for r in all_results if r.source == "tavily" and r.url})[:2]
                if domain:
                    homepage = f"https://{domain}" if not domain.startswith("http") else domain
                    if homepage not in top_urls:
                        top_urls.append(homepage)
                if top_urls:
                    scraped = await asyncio.gather(*[
                        scrape_url(u, settings.firecrawl_api_key) for u in top_urls
                    ])
                    for url, md in zip(top_urls, scraped):
                        if md:
                            all_results.append(
                                type("_R", (), {
                                    "title": f"Full page: {url}",
                                    "url": url,
                                    "content": md[:2000],
                                    "source": "firecrawl_scrape",
                                })()
                            )

            if all_results:
                web_context = "Live web research:\n" + "\n\n".join(
                    f"[{r.source}] {r.title}\nURL: {r.url}\n{r.content[:400]}"
                    for r in all_results
                ) + "\n\n"

        context = ""
        if raw_data:
            context += f"Raw lead data:\n{raw_data}\n\n"
        if research_data:
            context += f"Research findings:\n{research_data}\n\n"
        if web_context:
            context += web_context

        messages = [
            SystemMessage(content=ENRICHMENT_SYSTEM_PROMPT),
            HumanMessage(content=f"""
Enrich the following lead data:

{context}

Return a JSON object with two keys:
- "company": company enrichment data (employee count, revenue, industry, technologies, etc.)
- "contact": contact enrichment data (seniority, department, decision-maker status, etc.)
- "confidence": overall confidence score 0-1
"""),
        ]

        result = await self.invoke_with_retry(llm, messages)
        try:
            return parser.parse(result.content)
        except Exception:
            return {"raw_response": result.content, "parse_error": True}
