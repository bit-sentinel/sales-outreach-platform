"""
ExplainerAgent — generates a human-readable explanation of a signal-based score.

Called ONCE per lead, AFTER the scoring engine has produced a deterministic result.
Uses Claude Haiku (not Sonnet) — the score already exists, this is just narration.

The agent is given:
  - The scoring breakdown (signal values, weights, evidence)
  - Company / contact context
  - The final score + tier

It returns:
  - explanation (2-3 sentence paragraph for the UI)
  - recommended_action (one actionable sentence)
  - top_hooks (list of 3 personalisation hooks for email generation)
  - outreach_angle (best template selection hint: e.g. "Template 8 — event 31-120 days")
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)

_EXPLAINER_SYSTEM = """You are a terse B2B sales analyst summarising why a lead scored the way it did
for Launch House Events (Cvent build + event ops outsourcing).

Write in second person ("This lead…").  Be specific — cite actual evidence from the signal data.
Never hallucinate.  If a signal has no evidence, say so.
Keep the explanation under 80 words.
Return JSON only:
{
  "explanation": "<2-3 sentence score rationale>",
  "recommended_action": "<one sentence — what the BDR should do next>",
  "top_hooks": ["<hook 1>", "<hook 2>", "<hook 3>"],
  "outreach_angle": "<template selection hint>"
}
"""


class ExplainerAgent(BaseAgent):
    """Narrates a pre-computed signal score using Claude Haiku."""

    async def run(
        self,
        score_result: dict[str, Any],
        company_name: str | None = None,
        contact_name: str | None = None,
        contact_title: str | None = None,
    ) -> dict[str, Any]:
        import json
        import re

        llm = self.get_fast_llm(temperature=0.2)

        # Build a concise signal summary for the prompt
        breakdown = score_result.get("signal_breakdown") or {}
        signal_lines: list[str] = []
        for sig_type, detail in breakdown.items():
            val = detail.get("value", 0)
            contrib = detail.get("contribution", 0)
            evidence_summary = _summarise_evidence(sig_type, detail.get("evidence") or {})
            signal_lines.append(
                f"• {sig_type}: {val:.2f} (weight {detail.get('weight', 0):.2f}, "
                f"contributes {contrib:.2f}) — {evidence_summary}"
            )

        context = (
            f"Company: {company_name or 'Unknown'}\n"
            f"Contact: {contact_name or 'Unknown'} ({contact_title or 'Unknown title'})\n"
            f"Overall score: {score_result.get('overall_score', 0):.1f} / 100  "
            f"({score_result.get('tier', 'cold').upper()})\n\n"
            "Signal breakdown:\n" + "\n".join(signal_lines)
        )

        messages = [
            SystemMessage(content=_EXPLAINER_SYSTEM),
            HumanMessage(content=context),
        ]

        try:
            result = await self.invoke_with_retry(llm, messages)
            raw = result.content or ""
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as exc:
            logger.warning("ExplainerAgent failed: %s", exc)

        # Fallback — deterministic explanation from score alone
        return _fallback_explanation(score_result, company_name)


def _summarise_evidence(sig_type: str, evidence: dict) -> str:
    """Produce a one-line evidence summary for each signal type."""
    if sig_type == "cvent_events":
        soonest = evidence.get("soonest_days")
        count = evidence.get("upcoming_count", 0)
        if soonest is not None and soonest >= 0:
            return f"{count} upcoming event(s), soonest in {soonest}d"
        pages = evidence.get("total_pages_found", 0)
        return f"{pages} Cvent page(s) found, no upcoming dates confirmed"
    if sig_type == "event_volume":
        epy = evidence.get("events_per_year")
        cmx = evidence.get("complexity", "unknown")
        return f"~{epy or '?'} events/yr, complexity={cmx}"
    if sig_type == "hiring_signal":
        kw = evidence.get("matched_keywords", [])
        return f"{len(kw)} hiring keyword(s): {', '.join(kw[:3])}" if kw else "no job postings matched"
    if sig_type == "org_fit":
        return (
            f"seniority={evidence.get('seniority_label','?')}, "
            f"dept={evidence.get('department_label','?')}, "
            f"size={evidence.get('company_size','?')}"
        )
    if sig_type == "news_signal":
        return evidence.get("reason", "no relevant news")
    if sig_type == "industry_fit":
        return f"industry={evidence.get('industry_raw','?')} → {evidence.get('matched_label','?')}"
    return "no evidence"


def _fallback_explanation(score: dict, company_name: str | None) -> dict:
    tier = score.get("tier", "cold")
    overall = score.get("overall_score", 0)
    name = company_name or "This lead"
    if tier == "hot":
        explanation = (
            f"{name} scores {overall:.0f}/100. "
            "Strong upcoming event window with good title fit — prioritise immediately."
        )
        action = "Send Template 7 or 8 today based on days-to-event."
    elif tier == "warm":
        explanation = (
            f"{name} scores {overall:.0f}/100. "
            "Moderate event activity with reasonable contact fit — worth a personalised sequence."
        )
        action = "Enrol in standard 4-step sequence starting with Template 1."
    else:
        explanation = (
            f"{name} scores {overall:.0f}/100. "
            "Limited event signal or poor ICP fit — low conversion probability."
        )
        action = "Add to long-term nurture; re-score in 90 days."

    return {
        "explanation": explanation,
        "recommended_action": action,
        "top_hooks": [],
        "outreach_angle": "default",
    }
