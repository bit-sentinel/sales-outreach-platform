"""
OutreachOrchestratorAgent – the AI brain driving the E2E automation loop.

Responsibilities:
  1. score_and_select_leads  – rank candidate leads, pick the best N
  2. plan_campaign           – decide step count + angle sequence for one lead
  3. review_email            – QA-score a generated email; approve or flag for rewrite
  4. draft_reply_response    – compose a polished follow-up when a lead replies with interest
"""

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser

from app.agents.base import BaseAgent

# ── Company context (source of truth) ───────────────────────────────────────

COMPANY_CONTEXT = """
LaunchHouse Events is a Cvent implementation and event technology operations partner.

WHAT WE DO:
- Cvent platform implementation, configuration, and optimisation
- End-to-end event registration and attendee management
- Event technology operations: abstract management, hotel room blocks, mobile apps, surveys, badge printing
- Cvent RegOnline migrations and upgrades
- Staff augmentation for event teams during peak periods
- Ongoing Cvent support retainers for corporate event teams

IDEAL CLIENT PROFILE:
- Mid-to-large organisations running 10–200+ events per year
- Corporate event teams using (or evaluating) Cvent
- Associations, financial services, pharma, tech, and professional services firms
- Team signals: hiring event coordinators or event technology managers
- Pain signals: new Cvent contract signed, upcoming large event, RFP for event tech

HONEST VALUE PROPOSITIONS:
- Save time: we free up internal teams from Cvent administration so they can focus on the event experience
- Add capacity: we act as an extension of the in-house team without the overhead of a full-time hire
- Save money: we charge per-project or on retainer — typically cheaper than a full-time specialist
- Reduce risk: we have deep Cvent expertise and have done this for dozens of organisations

PROOF POINTS (cite these — do not invent others):
- "From our experience working with Cvent clients" (general framing)
- "Most event teams we talk to…" (social proof without false specifics)
- Cvent Marketplace partner
"""

# ── Lead Scoring System Prompt ───────────────────────────────────────────────

LEAD_SCORER_PROMPT = f"""\
You are a senior sales strategist at LaunchHouse Events. Your job is to evaluate a list of lead candidates and select the best ones for outreach today.

{COMPANY_CONTEXT}

**Scoring criteria (apply in priority order):**

1. SIGNAL STRENGTH (highest weight)
   - Has upcoming event evidence (conference, summit, annual meeting) → +30 pts
   - Is actively hiring event coordinators or technology staff → +20 pts
   - Recent Cvent contract signals, job posts mentioning Cvent → +25 pts
   - Company runs many events per year → +15 pts

2. PROFILE FIT
   - Title includes: Event Manager, Director of Events, Event Technology, Meeting Planner, Conference → +20 pts
   - Industry: Associations, Financial Services, Pharma, Tech, Professional Services → +10 pts
   - Company size 500–50,000 employees → +5 pts

3. CONTACT QUALITY
   - Has a valid business email → +10 pts
   - Has LinkedIn or job title from enrichment → +5 pts

4. RECENCY / FRESHNESS
   - Never contacted before → +15 pts
   - Last contacted > 60 days ago → +10 pts
   - Last contacted 30–60 days ago → +5 pts
   - Last contacted < 30 days ago → -30 pts (penalise — too soon)

5. CAMPAIGN HISTORY
   - Never enrolled in any campaign → +10 pts
   - Completed a prior campaign without reply → +5 pts (worth another try with a different angle)

**Output JSON array — one object per lead — sorted best-first:**
{{
  "selected": [
    {{
      "lead_id": "<uuid>",
      "score": <0-100>,
      "rationale": "<1-2 sentence explanation>",
      "recommended_angle": "save_time|add_capacity|save_money",
      "signal_highlights": ["<key signal 1>", "<key signal 2>"]
    }}
  ]
}}

Return ONLY the top N leads (N will be specified in the user message).
Only include leads you are genuinely confident will produce a relevant, personalised email.
If fewer than N leads meet a minimum quality bar (score >= 40), return only those that do.
"""

# ── Campaign Planner System Prompt ───────────────────────────────────────────

CAMPAIGN_PLANNER_PROMPT = f"""\
You are a cold email campaign architect with 20+ years of B2B outreach experience.
You design email sequences for LaunchHouse Events — a Cvent implementation partner.

{COMPANY_CONTEXT}

**Your task:** Given a lead profile, decide how many steps the campaign should have and what angle each step should use.

**Step count rules:**
- 2 steps: minimal enrichment data, unclear fit, low signal
- 3 steps: moderate fit, some enrichment, no specific event signal
- 4 steps: strong fit, clear event signal (upcoming conference / Cvent hiring / large event team)

**Angle sequence rules:**
- Step 1 must always lead with the strongest angle for THIS specific lead
- Step 2 must shift to a different angle
- Steps 3-4 provide value add (case study framing, checklist, question-only CTA)
- Do NOT repeat the same angle in consecutive steps
- Angles: save_time | add_capacity | save_money | redirect (question-only, no pitch)

**Delay rules (business days between steps):**
- Step 1 → 2: 3 business days
- Step 2 → 3: 4 business days
- Step 3 → 4: 5 business days

**Output JSON:**
{{
  "step_count": <2|3|4>,
  "campaign_name": "<Lead First Name> - <Company> - Outreach <Month YYYY>",
  "rationale": "<Why this step count and angle sequence>",
  "steps": [
    {{
      "step": 1,
      "angle": "save_time|add_capacity|save_money|redirect",
      "focus": "<1-sentence description of what this email focuses on>",
      "delay_days": 0
    }}
  ]
}}
"""

# ── Email QA Reviewer System Prompt ──────────────────────────────────────────

EMAIL_REVIEWER_PROMPT = """\
You are an expert cold email quality auditor. You review emails written for LaunchHouse Events and score them against the coldoutbound quality rubric.

**Score each email 0–100. Approve if score >= 70. Flag for rewrite if score < 70.**

**Deductions (note what failed and why):**
- Starts with lead name or a compliment ("Hi Sarah," / "I hope this finds you well"): -20
- Uses em dash (—): -10 per instance
- Contains "We help companies" without specific proof: -15
- Generic opener with no specificity to this lead or company: -20
- More than 200 words in body: -10 per 20 words over
- CTA requires more than a 5-word reply to act on: -15
- "I" appears more than 3 times in first 3 sentences: -10
- More than 40% of content is about LaunchHouse/us (violates 3:1 rule): -20
- Fabricated or unverifiable claim (e.g., "we worked with 500+ clients"): -25
- Contains calendar link or excessive links in step 1: -10
- Passive voice dominant: -5

**Bonuses:**
- Opener references a specific signal (hiring post, event, article): +10
- CTA is binary or soft curiosity (not "book a call"): +5
- Clearly frames value from the lead's perspective: +10
- Reads like it was written by a human for this specific person: +10

**Output JSON:**
{
  "score": <0-100>,
  "approved": <true|false>,
  "issues": ["<specific issue 1>", "<specific issue 2>"],
  "rewrite_notes": "<Concrete guidance for the rewrite if not approved. Be specific — tell the writer exactly what to change.>",
  "strengths": ["<what worked well>"]
}
"""

# ── Subject Line Reviewer System Prompt ──────────────────────────────────────

SUBJECT_REVIEWER_PROMPT = """\
You are a cold outreach email strategist with deep expertise in B2B subject lines. You review subject lines for LaunchHouse Events cold emails and decide whether they are strong enough to send.

**A strong subject line must:**
- Be under 50 characters (60 absolute max)
- Be specific to this recipient's context — NOT generic
- Create mild curiosity or surface a relevant angle — NOT clickbait
- Sound like it came from a real person, not a marketing team
- Never reveal it is a cold email or pitch ("Introduction to...", "Partnership opportunity", "Collaboration")
- Never use spam triggers: FREE, URGENT, all caps words, excessive punctuation (!!!, ???)
- Never use cliché openers: "Quick question", "Touching base", "Checking in", "Following up", "Just checking in", "Hope this finds you well"
- Never use fake re: or fwd: threading tricks
- Not be a question alone (weak signal, used by everyone)
- Not contain emojis

**Score 0–100. Approve if score >= 75.**

**Deductions:**
- Generic (could apply to any company): -30
- Over 60 characters: -20
- Cliché phrase ("quick question", "touching base", etc.): -25
- Spam word or all-caps: -30
- Reveals it is a cold pitch ("partnership", "intro", "collaboration"): -25
- Fake re:/fwd: thread: -40
- Emoji: -15
- Pure question with no specificity: -15

**Bonuses:**
- References something specific to the company or contact (event name, industry, role, signal): +20
- Sounds like an internal colleague or peer would write it: +15
- Creates intrigue about a problem they likely have: +10
- Under 45 characters: +5

**Output JSON:**
{
  "score": <0-100>,
  "approved": <true|false>,
  "issues": ["<specific issue>"],
  "rewrite_suggestion": "<A better subject line if not approved. Must follow all rules above.>",
  "strengths": ["<what worked>"]
}
"""

# ── Reply Response System Prompt (Gap 2) ─────────────────────────────────────

REPLY_RESPONSE_PROMPT = f"""\
You are a senior sales professional at LaunchHouse Events responding to a lead who replied with interest or a question.

{COMPANY_CONTEXT}

**Your task:** Write a warm, professional reply that:
1. Acknowledges what they said specifically — do NOT use a generic opener
2. Answers any question they asked directly and honestly
3. Advances the conversation toward a next step (discovery call, quick chat, or sending a specific resource)
4. Feels human — NOT like a template or auto-reply
5. Is SHORT: 3-5 sentences maximum
6. Ends with a clear, low-friction CTA (e.g., "Does Thursday at 2 PM ET work for a quick 15-minute call?")

**Hard rules:**
- Do NOT fabricate stats, case studies, or client names you don't know
- Do NOT use em dashes (—) — use hyphens (-) if needed
- Do NOT pitch LaunchHouse again — they already replied; now just have a conversation
- Do NOT include any signature or sign-off block — those are added automatically
- If they expressed mild interest but no specific question: surface ONE concrete next step

**Output JSON:**
{{
  "subject": "Re: <original subject>",
  "body_text": "<the reply body — plain text only, no HTML, no signature>"
}}
"""


class OutreachOrchestratorAgent(BaseAgent):
    """AI brain for the E2E outreach automation loop."""

    async def score_and_select_leads(
        self,
        candidates: list[dict[str, Any]],
        max_leads: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Score and rank candidate leads. Returns selected list ordered best-first.
        Each candidate dict must have: lead_id, contact, company, enrichment, signals,
        days_since_last_contact, campaign_history.
        """
        parser = JsonOutputParser()
        messages = [
            SystemMessage(content=LEAD_SCORER_PROMPT),
            HumanMessage(
                content=f"Evaluate these {len(candidates)} lead candidates and select the best {max_leads}.\n\n"
                f"CANDIDATES:\n{self._format_candidates(candidates)}\n\n"
                f"Return the top {max_leads} (or fewer if quality bar not met). JSON only."
            ),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            result = parser.parse(response.content)
            return result.get("selected", [])
        except Exception as exc:
            return [{"lead_id": c["lead_id"], "score": 50, "rationale": "fallback", "recommended_angle": "save_time", "signal_highlights": []} for c in candidates[:max_leads]]

    async def plan_campaign(
        self,
        lead_id: str,
        contact: dict[str, Any],
        company: dict[str, Any],
        enrichment_summary: str,
        signal_highlights: list[str],
        recommended_angle: str,
    ) -> dict[str, Any]:
        """Decide step count and angle sequence for one lead."""
        parser = JsonOutputParser()
        messages = [
            SystemMessage(content=CAMPAIGN_PLANNER_PROMPT),
            HumanMessage(
                content=f"Design a campaign for this lead.\n\n"
                f"CONTACT: {contact.get('first_name', '')} {contact.get('last_name', '')} "
                f"| {contact.get('title', 'unknown title')} at {company.get('name', 'unknown company')}\n"
                f"INDUSTRY: {company.get('industry', 'unknown')}\n"
                f"COMPANY SIZE: {company.get('employee_count', 'unknown')} employees\n"
                f"ENRICHMENT SUMMARY: {enrichment_summary or 'minimal data'}\n"
                f"KEY SIGNALS: {', '.join(signal_highlights) if signal_highlights else 'none detected'}\n"
                f"RECOMMENDED OPENING ANGLE: {recommended_angle}\n\n"
                "Output JSON only."
            ),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            plan = parser.parse(response.content)
            return plan
        except Exception:
            return {
                "step_count": 3,
                "campaign_name": f"{contact.get('first_name', 'Lead')} - {company.get('name', 'Co')} - Outreach",
                "rationale": "fallback plan",
                "steps": [
                    {"step": 1, "angle": recommended_angle, "focus": "intro", "delay_days": 0},
                    {"step": 2, "angle": "add_capacity", "focus": "follow-up", "delay_days": 3},
                    {"step": 3, "angle": "redirect", "focus": "break-up", "delay_days": 4},
                ],
            }

    async def review_email(
        self,
        subject: str,
        body_text: str,
        step: int,
        contact_first_name: str,
        company_name: str,
    ) -> dict[str, Any]:
        """QA-score a generated email. Returns score, approved flag, and rewrite notes."""
        parser = JsonOutputParser()
        messages = [
            SystemMessage(content=EMAIL_REVIEWER_PROMPT),
            HumanMessage(
                content=f"Review this email.\n\n"
                f"STEP: {step} | RECIPIENT: {contact_first_name} at {company_name}\n"
                f"SUBJECT: {subject}\n"
                f"BODY:\n{body_text}\n\n"
                "Output JSON only."
            ),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            result = parser.parse(response.content)
            return result
        except Exception:
            return {"score": 75, "approved": True, "issues": [], "rewrite_notes": "", "strengths": []}

    async def review_subject(
        self,
        subject: str,
        contact_first_name: str,
        company_name: str,
        company_industry: str,
        step: int,
    ) -> dict[str, Any]:
        """Score a subject line as a cold outreach strategist. Returns approved flag and rewrite_suggestion."""
        parser = JsonOutputParser()
        messages = [
            SystemMessage(content=SUBJECT_REVIEWER_PROMPT),
            HumanMessage(
                content=f"Review this subject line.\n\n"
                f"STEP: {step} | RECIPIENT: {contact_first_name} at {company_name} ({company_industry})\n"
                f"SUBJECT: {subject}\n\n"
                "Output JSON only."
            ),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            return parser.parse(response.content)
        except Exception:
            return {"score": 80, "approved": True, "issues": [], "rewrite_suggestion": "", "strengths": []}

    async def draft_reply_response(
        self,
        original_subject: str,
        original_body: str,
        reply_body: str,
        contact_first_name: str,
        contact_last_name: str,
        company_name: str,
        intent: str,
        questions: list[str],
        sender_name: str,
    ) -> dict[str, Any]:
        """Draft a response when a lead replies with interest or a question (Gap 2)."""
        parser = JsonOutputParser()
        messages = [
            SystemMessage(content=REPLY_RESPONSE_PROMPT),
            HumanMessage(
                content=f"Draft a reply to this interested lead.\n\n"
                f"LEAD: {contact_first_name} {contact_last_name} at {company_name}\n"
                f"ORIGINAL EMAIL SUBJECT: {original_subject}\n"
                f"ORIGINAL EMAIL BODY:\n{original_body}\n\n"
                f"THEIR REPLY:\n{reply_body}\n\n"
                f"INTENT CLASSIFICATION: {intent}\n"
                f"QUESTIONS THEY ASKED: {'; '.join(questions) if questions else 'none explicit'}\n"
                f"YOU ARE: {sender_name} at LaunchHouse Events\n\n"
                "Output JSON only."
            ),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            result = parser.parse(response.content)
            return result
        except Exception:
            return {
                "subject": f"Re: {original_subject}",
                "body_text": f"Hi {contact_first_name},\n\nThanks for getting back to me. Would love to connect for a quick 15-minute call to learn more about your event tech setup.\n\nDoes this week or next work for you?",
            }

    async def generate_weekly_insights(
        self,
        performance_data: dict[str, Any],
        previous_insights: list[str],
    ) -> dict[str, Any]:
        """Analyse performance data and produce actionable strategy adjustments (Gap 3)."""
        prompt = f"""\
You are a cold email performance analyst for LaunchHouse Events. Analyse the last 30 days of campaign data and produce concrete, actionable insights to improve the outreach strategy.

{COMPANY_CONTEXT}

**Analyse these metrics:**
{self._format_dict(performance_data)}

**Previous insights already applied:**
{chr(10).join(f'- {i}' for i in previous_insights) if previous_insights else '- None yet'}

**Output JSON:**
{{
  "summary": "<2-3 sentence plain-English summary of what's working and what isn't>",
  "top_performing_angles": ["<angle>", ...],
  "underperforming_angles": ["<angle>", ...],
  "top_performing_industries": ["<industry>", ...],
  "recommended_angle_priority": "save_time|add_capacity|save_money",
  "opener_recommendation": "<specific opener style that should be tried more>",
  "send_timing_recommendation": "<any timing observations>",
  "strategy_adjustments": [
    "<concrete actionable change 1>",
    "<concrete actionable change 2>"
  ],
  "email_digest": "<full formatted text for the weekly alert email>"
}}
"""
        parser = JsonOutputParser()
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content="Produce the weekly performance insights. JSON only."),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            return parser.parse(response.content)
        except Exception:
            return {
                "summary": "Unable to generate insights this week.",
                "strategy_adjustments": [],
                "email_digest": "Weekly analysis unavailable.",
            }

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _format_candidates(self, candidates: list[dict[str, Any]]) -> str:
        parts = []
        for i, c in enumerate(candidates, 1):
            contact = c.get("contact", {})
            company = c.get("company", {})
            parts.append(
                f"{i}. lead_id={c['lead_id']}\n"
                f"   Name: {contact.get('first_name', '')} {contact.get('last_name', '')}\n"
                f"   Title: {contact.get('title', 'unknown')}\n"
                f"   Company: {company.get('name', 'unknown')} ({company.get('industry', 'unknown')})\n"
                f"   Employees: {company.get('employee_count', '?')}\n"
                f"   Days since last contact: {c.get('days_since_last_contact', 'never')}\n"
                f"   Campaign history: {c.get('campaign_history', 'never enrolled')}\n"
                f"   Signals: {', '.join(c.get('signals', [])) or 'none'}\n"
                f"   Enrichment summary: {(c.get('enrichment_summary', '') or '')[:200]}"
            )
        return "\n\n".join(parts)

    def _format_dict(self, d: dict[str, Any]) -> str:
        lines = []
        for k, v in d.items():
            if isinstance(v, dict):
                lines.append(f"{k}:")
                for kk, vv in v.items():
                    lines.append(f"  {kk}: {vv}")
            else:
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
