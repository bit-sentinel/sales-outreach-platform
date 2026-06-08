"""
Stage 6 — OutreachIntelligenceAgent.

Consumes the lead score, evidence, signals and CompanyEventProfile and produces
a fully-explainable outreach package: every angle, event reference, timing call
and service recommendation carries a `why` tracing it to a specific signal or
evidence item.

Caching is two-layered:
  • AgentResultCache  — the whole result, CONTACT-scoped (base class)
  • Anthropic prompt caching — the static system prompt block (ephemeral)
"""
import json
import logging
import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.agents.v3.base import BaseIntelligenceAgent
from app.agents.v3.contracts import (
    AgentContext, AgentResult, AgentStatus, CacheScope, EvidenceItem,
    PipelineStage, SignalType, SourceType,
)
from app.agents.v3.errors import RetryableError
from app.agents.v3.registry import register_agent

logger = logging.getLogger(__name__)


# ── Output schema ──────────────────────────────────────────────────────────
class OutreachAngle(BaseModel):
    angle: Optional[str] = ""
    why: Optional[str] = ""                 # explainability: what drove this angle
    backed_by_signal: str = "unknown"       # signal_type that supports it


class EventReference(BaseModel):
    event_name: Optional[str] = ""
    detail: Optional[str] = ""
    why_relevant: Optional[str] = ""
    source_url: Optional[str] = None


class ServiceRecommendation(BaseModel):
    service: Optional[str] = ""
    rationale: Optional[str] = ""
    matched_signal: str = "unknown"


class OutreachIntelligence(BaseModel):
    recommended_contact_role: Optional[str] = ""
    subject_line: Optional[str] = ""
    email_body: Optional[str] = ""
    angles: list[OutreachAngle] = Field(default_factory=list)
    event_references: list[EventReference] = Field(default_factory=list)
    timing_recommendation: Optional[str] = ""
    timing_rationale: Optional[str] = ""
    service_recommendations: list[ServiceRecommendation] = Field(default_factory=list)
    # Explainability — the inputs that drove the whole generation.
    generation_basis: dict[str, Any] = Field(default_factory=dict)


# ── Service catalog (static — part of the cacheable system prompt) ─────────
SERVICE_CATALOG = [
    "Cvent registration build & management",
    "OnArrival check-in / badging staffing",
    "Attendee Hub setup & content loading",
    "Event-program overflow / surge support",
    "Session & speaker logistics coordination",
    "Post-event reporting & attendee analytics",
]


# ── Prompt templates ───────────────────────────────────────────────────────
OUTREACH_SYSTEM_PROMPT = f"""\
You generate B2B outreach intelligence for a firm that provides OUTSOURCED \
Cvent event-operations services to enterprises. The firm does not sell Cvent \
licenses — it provides the human team that runs Cvent for clients.

SERVICE CATALOG (only ever recommend from this list):
{chr(10).join(f'  - {s}' for s in SERVICE_CATALOG)}

YOUR JOB:
Given a scored lead with signals, evidence and a company event profile, produce
a personalized outreach package. The prospect already uses Cvent — the pitch is
ALWAYS "we run it for you / we extend your team", never "switch platforms".

VOICE & TONE — this is non-negotiable:
  Write like a sharp, self-aware founder texting a peer. Not a sales rep emailing a stranger.
  Study these patterns and apply them to every email body and subject line:
  • Short sentences. Then another short one. Then maybe a longer one that earns its length.
  • Start mid-thought. Skip the warm-up. "Saw your [X]." not "I wanted to reach out because..."
  • Be specific. Reference something real — an actual event name, a number, a detail from evidence.
  • Honest and direct. Say what you mean. No hedging.
  • No corporate language. Never use: "leverage", "synergies", "circle back", "touch base",
    "I hope this finds you well", "I wanted to reach out", "at your earliest convenience",
    "value-add", "bandwidth", "move the needle", "deep dive", "take this offline".
  • The ask is clear and small. Not "let's explore a potential partnership opportunity."
    More like "worth a quick call?"
  • Pattern interrupts are good. An unexpected opener beats a safe one every time.
  • Max 3–4 sentences in the body. Every word must earn its place.

HARD RULES:
  1. Every angle, event reference, timing call and service recommendation MUST
     include a `why` / `rationale` field that cites a specific signal or piece
     of evidence. No unexplained claims.
  2. Only reference events that appear in the supplied evidence. Never invent
     event names, dates or numbers.
  3. Recommend services only from the catalog above, matched to a real signal.
  4. Keep the email body under 100 words. No fluff. No filler. No throat-clearing.

OUTPUT — return JSON only, this exact shape:
{{
  "recommended_contact_role": str,
  "subject_line": str,
  "email_body": str,
  "angles": [{{"angle": str, "why": str, "backed_by_signal": str}}],
  "event_references": [{{"event_name": str, "detail": str,
                         "why_relevant": str, "source_url": str|null}}],
  "timing_recommendation": str,
  "timing_rationale": str,
  "service_recommendations": [{{"service": str, "rationale": str,
                                "matched_signal": str}}]
}}"""


def build_user_prompt(ctx: AgentContext, facts: list[str],
                      evidence_lines: list[str]) -> str:
    score = ctx.extra.get("lead_score", {})
    profile = ctx.extra.get("company_profile", {})
    contact = ctx.contact
    return (
        f"COMPANY: {ctx.company.name} ({ctx.company.industry or 'industry n/a'})\n"
        f"CONTACT: {contact.full_name if contact else 'n/a'} — "
        f"{contact.title if contact else 'n/a'}\n\n"
        f"LEAD SCORE: {score.get('overall_score', 'n/a')} "
        f"({score.get('tier', 'n/a')}), confidence {score.get('confidence', 'n/a')}\n"
        f"SCORE EXPLANATION: {score.get('explanation', 'n/a')}\n\n"
        f"COMPANY EVENT PROFILE:\n"
        f"  cvent_status={profile.get('cvent_status', 'n/a')}, "
        f"event_volume_tier={profile.get('event_volume_tier', 'n/a')}, "
        f"events/yr={profile.get('estimated_events_per_year', 'n/a')}, "
        f"budget_band={profile.get('estimated_budget_band', 'n/a')}, "
        f"outsourcing_tier={profile.get('outsourcing_tier', 'n/a')}\n\n"
        f"SIGNALS:\n" + "\n".join(facts) + "\n\n"
        f"EVIDENCE (cite these — do not invent):\n" + "\n".join(evidence_lines)
    )


# ── JSON parsing ──────────────────────────────────────────────────────────
def _parse_llm_json(raw: str) -> dict:
    """
    Tolerant JSON extraction from LLM output.
    1. Strip markdown code fences.
    2. Extract first {...} block.
    3. Try strict json.loads.
    4. Fall back to json_repair if available.
    5. Raise RetryableError so the agent retries on complete failure.
    """
    # Strip ```json ... ``` or ``` ... ``` fences
    text = re.sub(r"```(?:json)?\s*", "", raw).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise RetryableError("no JSON object in LLM response")
    candidate = match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # Try json_repair (pip install json-repair) for tolerant parsing
    try:
        from json_repair import repair_json
        repaired = repair_json(candidate)
        return json.loads(repaired)
    except Exception:
        pass
    raise RetryableError(f"unparseable JSON from LLM (len={len(candidate)})")


# ── Agent ──────────────────────────────────────────────────────────────────
@register_agent
class OutreachIntelligenceAgent(BaseIntelligenceAgent):
    signal_type = SignalType.OUTREACH
    stage = PipelineStage.INTELLIGENCE.value
    cache_scope = CacheScope.CONTACT
    cache_ttl_hours = 168
    timeout_s = 70.0
    max_attempts = 2

    async def _collect(self, ctx: AgentContext) -> AgentResult:
        if not self.settings.anthropic_api_key:
            return AgentResult(
                signal_type=self.signal_type, status=AgentStatus.SKIPPED,
                value=0.0, confidence=0.0, error="no anthropic key",
            )

        # ── assemble inputs ────────────────────────────────────────────────
        facts: list[str] = []
        evidence_lines: list[str] = []
        signals_used: list[str] = []
        for sig in (SignalType.CVENT, SignalType.EVENT_VOLUME, SignalType.EVENT_TEAM,
                    SignalType.HIRING, SignalType.BUDGET, SignalType.OUTSOURCING,
                    SignalType.TARGETED_RESEARCH):
            r = ctx.upstream_result(sig)
            if not (r and r.is_usable()):
                continue
            signals_used.append(sig.value)
            facts.append(f"- {sig.value}: value={r.value:.2f} conf={r.confidence:.2f} "
                         f"{json.dumps(r.payload, default=str)[:280]}")
            for ev in r.evidence[:3]:
                evidence_lines.append(
                    f"  [{sig.value}] {ev.claim[:200]}"
                    + (f"  <{ev.source_url}>" if ev.source_url else "")
                )

        if not facts:
            return AgentResult(
                signal_type=self.signal_type, status=AgentStatus.SKIPPED,
                value=0.0, confidence=0.0, error="no usable upstream signals",
            )

        # ── call Claude with prompt caching on the static system block ─────
        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = ChatAnthropic(model=self.settings.anthropic_model, temperature=0.4,
                            api_key=self.settings.anthropic_api_key, max_retries=2)
        system = SystemMessage(content=[{
            "type": "text", "text": OUTREACH_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},   # cached across leads (~5m TTL)
        }])
        user = HumanMessage(content=build_user_prompt(ctx, facts, evidence_lines))
        resp = await llm.ainvoke([system, user])

        # Extract text from content (may be str or list of content blocks)
        if isinstance(resp.content, str):
            raw = resp.content
        elif isinstance(resp.content, list):
            raw = " ".join(
                block["text"] if isinstance(block, dict) and "text" in block
                else str(block)
                for block in resp.content
            )
        else:
            raw = str(resp.content)
        parsed = _parse_llm_json(raw)
        intel = OutreachIntelligence.model_validate(parsed)
        # Coerce any None string fields to "" (Claude occasionally omits them)
        _STR_FIELDS = ("recommended_contact_role", "subject_line", "email_body",
                       "timing_recommendation", "timing_rationale")
        for _f in _STR_FIELDS:
            if getattr(intel, _f) is None:
                setattr(intel, _f, "")
        for a in intel.angles:
            if a.angle is None: a.angle = ""
            if a.why is None: a.why = ""
        for e in intel.event_references:
            if e.event_name is None: e.event_name = ""
            if e.detail is None: e.detail = ""
            if e.why_relevant is None: e.why_relevant = ""
        for s in intel.service_recommendations:
            if s.service is None: s.service = ""
            if s.rationale is None: s.rationale = ""

        # explainability — record exactly what fed the generation
        score = ctx.extra.get("lead_score", {})
        intel.generation_basis = {
            "signals_used": signals_used,
            "evidence_count": len(evidence_lines),
            "lead_score": score.get("overall_score"),
            "lead_tier": score.get("tier"),
            "company_profile_used": bool(ctx.extra.get("company_profile")),
        }

        usage = getattr(resp, "usage_metadata", None) or {}
        # ── one evidence row per generated angle (traceable) ───────────────
        evidence = [EvidenceItem(
            claim=f"Outreach angle: {a.angle} — why: {a.why}",
            signal_type=self.signal_type, source_type=SourceType.LLM_INFERENCE,
            source_provider="claude", confidence=0.7,
            raw_data={"backed_by_signal": a.backed_by_signal},
        ) for a in intel.angles[:5]]

        return AgentResult(
            signal_type=self.signal_type, status=AgentStatus.OK,
            value=1.0 if intel.angles else 0.3,
            confidence=0.75 if intel.angles else 0.4,
            payload=intel.model_dump(),
            evidence=evidence, providers=["claude"],
            tokens_used=int(usage.get("total_tokens", 0) or 0),
        )
