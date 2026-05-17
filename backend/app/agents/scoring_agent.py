"""
Lead Scoring Agent – AI-powered lead scoring with signal-by-signal breakdown.
"""

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent


class ScoringSignal(BaseModel):
    signal_name: str
    score: float = Field(ge=0, le=1, description="Signal score 0-1")
    weight: float = Field(description="Weight for this signal")
    reasoning: str = Field(description="Why this score")


class ScoringOutput(BaseModel):
    overall_score: float = Field(ge=0, le=100, description="Overall score 0-100")
    tier: str = Field(description="hot, warm, or cold")
    signals: list[ScoringSignal]
    explanation: str = Field(description="Summary explanation for the score")
    recommended_action: str = Field(description="Recommended next action")


SCORING_SYSTEM_PROMPT = """You are an expert B2B lead scoring analyst for Launch House Events.
Score leads for a cold outreach program selling outsourced event build and event-operations support
inside the prospect's existing Cvent license.

**Scoring Signals & Weights:**
1. Upcoming Event Window (0.25) – Are there public events 0-120 days out that create near-term build pressure?
2. Event Program Size (0.15) – Do they run enough events or complex programs to justify overflow support?
3. Title/Seniority Fit (0.20) – Is the contact likely to own event operations, field marketing, or Cvent decisions?
4. Company Size Fit (0.15) – Is the company large enough to run meaningful event volume but small enough to outsource overflow?
5. Recent Activity Signals (0.15) – Hiring, launches, news, expansion, or team changes that imply event workload.
6. Industry Fit (0.10) – Is the business model naturally event-heavy?

**Tier Thresholds:**
- Hot (≥75): High probability of conversion – prioritize immediately
- Warm (50-74): Moderate interest – nurture with personalized outreach
- Cold (<50): Low probability – consider for future nurturing

Assume Cvent usage is already confirmed. Do not spend score weight on proving they use Cvent.
Provide an honest, well-reasoned score. Don't inflate scores without justification.
"""


class ScoringAgent(BaseAgent):
    """AI-powered lead scoring with multi-signal analysis."""

    async def run(
        self,
        lead_id: str,
        tenant_id: str,
        lead_data: dict | None = None,
        enrichment_data: dict | None = None,
        research_data: dict | None = None,
    ) -> dict[str, Any]:
        llm = self.get_llm(temperature=0.2)
        parser = JsonOutputParser(pydantic_object=ScoringOutput)

        context_parts = []
        if lead_data:
            context_parts.append(f"Lead data: {lead_data}")
        if enrichment_data:
            context_parts.append(f"Enrichment data: {enrichment_data}")
        if research_data:
            context_parts.append(f"Research data: {research_data}")

        context = "\n\n".join(context_parts) if context_parts else "No data available."

        messages = [
            SystemMessage(content=SCORING_SYSTEM_PROMPT),
            HumanMessage(content=f"""
Score the following lead:

{context}

{parser.get_format_instructions()}
"""),
        ]

        result = await self.invoke_with_retry(llm, messages)
        try:
            return parser.parse(result.content)
        except Exception:
            return {"raw_response": result.content, "parse_error": True}
