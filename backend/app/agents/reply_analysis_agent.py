"""
Reply Analysis Agent – analyzes incoming replies and classifies intent.
"""

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent


class ReplyAnalysis(BaseModel):
    intent: str = Field(
        description="One of: interested, meeting_request, question, objection, "
        "not_now, unsubscribe, out_of_office, bounce, irrelevant"
    )
    sentiment: str = Field(description="positive, neutral, negative")
    priority: str = Field(description="high, medium, low")
    key_points: list[str] = Field(description="Key points from the reply")
    suggested_action: str = Field(description="Recommended next action")
    suggested_response: str | None = Field(description="Draft response if appropriate")
    meeting_requested: bool = Field(description="Whether a meeting was requested")
    objections: list[str] = Field(description="Any objections raised")
    questions: list[str] = Field(description="Any questions asked")
    reply_handler_template: str = Field(
        description="Which reply handler template to use: "
        "T10 (positive interest), T11 (send more info), T12 (not now), "
        "T13 (already have support/agency), T14 (wrong contact/referral), "
        "or 'none' for auto-replies/OOO/bounce"
    )


REPLY_ANALYSIS_PROMPT = """You are an expert sales communication analyst for Launch House Events — a Cvent implementation and event management firm. Analyze incoming email replies and classify them accurately.

**Intent Categories:**
1. **interested** – Positive response, wants to learn more (priority: HIGH)
2. **meeting_request** – Explicitly asks for a meeting/call (priority: HIGH)
3. **question** – Asks specific questions about product/service (priority: HIGH)
4. **objection** – Raises concerns (budget, timing, competition) (priority: MEDIUM)
5. **not_now** – Timing is wrong, maybe later (priority: MEDIUM)
6. **unsubscribe** – Asks to be removed from list (priority: HIGH – compliance)
7. **out_of_office** – Auto-reply, out of office (priority: LOW)
8. **bounce** – Delivery failure (priority: LOW)
9. **irrelevant** – Not related to outreach (priority: LOW)

**Reply Handler Template Routing (map intent → template):**
- interested OR meeting_request → T10 (Positive Interest Reply)
- question OR "send more info" → T11 ("Send More Info" Reply)
- not_now OR objection (timing) → T12 ("Not Now" Reply)
- objection (has agency/internal team) → T13 ("Already Have Support" Reply)
- wrong person / referral request → T14 (Wrong Contact / Referral)
- out_of_office / bounce / irrelevant → none

**Analysis Guidelines:**
- Be precise with intent — don't over-interpret politeness as interest
- "Not interested" stated plainly = objection, not interested intent
- "Need to think" = not_now
- Extract all questions that need answers
- Identify specific objections that can be addressed
- Suggest concrete next actions based on the template routing
- If interested/meeting: draft a concise response using T10 style (two paths forward)
- If objection/agency: draft T13-style response (overflow lane, pressure valve)
- If not_now: draft T12-style response (revisit window, no push)
- If unsubscribe: flag for immediate removal, no response
"""


class ReplyAnalysisAgent(BaseAgent):
    """Analyzes incoming email replies for intent and sentiment."""

    async def run(
        self,
        reply_text: str,
        original_message: str | None = None,
        lead_context: dict | None = None,
    ) -> dict[str, Any]:
        llm = self.get_llm(temperature=0.2)  # Low temperature for classification
        parser = JsonOutputParser(pydantic_object=ReplyAnalysis)

        context = ""
        if original_message:
            context += f"**Original message sent:**\n{original_message}\n\n"
        if lead_context:
            context += f"**Lead context:**\n{lead_context}\n\n"

        messages = [
            SystemMessage(content=REPLY_ANALYSIS_PROMPT),
            HumanMessage(content=f"""
Analyze this email reply:

**Reply:**
{reply_text}

{context}

{parser.get_format_instructions()}
"""),
        ]

        result = await self.invoke_with_retry(llm, messages)
        try:
            return parser.parse(result.content)
        except Exception:
            return {"raw_response": result.content, "parse_error": True}
