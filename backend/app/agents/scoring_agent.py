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


SCORING_SYSTEM_PROMPT = """You are an expert B2B lead scoring analyst. Score leads based on 
their likelihood to convert, considering multiple signals:

**Scoring Signals & Weights:**
1. Company Size Fit (0.15) – Does the company size match the ideal customer profile?
2. Industry Fit (0.12) – Is the industry a good fit?
3. Title/Seniority Fit (0.15) – Is the contact a decision-maker?
4. Technology Fit (0.10) – Do they use relevant technologies?
5. Recent Activity Signals (0.12) – Hiring, events, expansion
6. Funding/Growth (0.08) – Recent funding or growth indicators
7. Event Usage (0.10) – Current event platform usage (especially Cvent)
8. Engagement History (0.08) – Past interactions and engagement
9. Timing Signals (0.05) – Contract renewal, budget cycle
10. Geographic Fit (0.05) – Location alignment

**Tier Thresholds:**
- Hot (≥75): High probability of conversion – prioritize immediately
- Warm (50-74): Moderate interest – nurture with personalized outreach
- Cold (<50): Low probability – consider for future nurturing

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
