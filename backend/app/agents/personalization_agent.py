"""
Personalization Agent – generates hyper-personalized email content.

Copywriting framework based on coldoutboundskills principles:
- Write fresh from signal context, never fill templates
- Structure: Situation Recognition → Value Prop + Proof → CTA (50-90 words)
- Follow-up sequence: rotate value props (save time → make money → save money), never reference prior email
- Subject line: 2-4 words (intrigue) OR whole offer (self-selecting)
- Each email stands alone — follow-ups are not "following up"
"""

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent

# Known email → full name mappings (for accounts where username != display name)
_SENDER_NAME_MAP: dict[str, str] = {
    "sam@launchhouse.events": "Sameera Gurung",
    "sam@launchhouse.in": "Sameera Gurung",
}


def _resolve_sender_name(email: str, display_name: str = "") -> str:
    """Return the display name for a sender email address.

    Priority: known map → SenderAccount.display_name → capitalize username.
    e.g. sneha@launchhouse.in → "Sneha", john.smith@x.com → "John Smith"
    """
    e = (email or "").lower().strip()
    if e in _SENDER_NAME_MAP:
        return _SENDER_NAME_MAP[e]
    if display_name:
        return display_name
    username = e.split("@")[0]
    return " ".join(part.capitalize() for part in re.split(r"[._\-]", username)) or "Sameera Gurung"


def _strip_body_signatures(text: str) -> str:
    """Remove any LLM-appended signature block from the email body.

    Handles two patterns:
    1. "Best," sign-off (caught by _strip_llm_signature from email_renderer)
    2. Bare name/company/email block appended without "Best," (e.g. "Sameera Gurung\\nLaunchHouse Events\\nsam@...")
    """
    from app.tools.email_renderer import _strip_llm_signature
    # Pass 1: strip from "Best," onwards
    text = _strip_llm_signature(text)
    # Pass 2: strip trailing paragraphs that look like a contact block
    # (contains an @ address, or is all short lines with no sentence-ending punctuation)
    paragraphs = re.split(r"\n\s*\n", text.strip())
    while len(paragraphs) > 1:
        last = paragraphs[-1].strip()
        lines = [l.strip() for l in last.splitlines() if l.strip()]
        if not lines:
            paragraphs.pop()
            continue
        has_email = any("@" in l for l in lines)
        looks_like_sig = (
            all(len(l) < 60 and not re.search(r"[.?!]$", l) for l in lines)
            and len(lines) <= 5
        )
        if has_email or looks_like_sig:
            paragraphs.pop()
        else:
            break
    return "\n\n".join(paragraphs).strip()


class EmailOutput(BaseModel):
    subject: str = Field(description="Email subject line, under 8 words")
    body_html: str = Field(description="HTML email body, fully written and resolved")
    body_text: str = Field(description="Plain text email body, fully written and resolved")
    personalization_hooks: list[str] = Field(description="Specific signals used to personalize this email")
    template_used: str = Field(description="Angle and step used, e.g. 'Step 1 — event trigger, upcoming summit in 45 days'")
    tone: str = Field(description="Tone applied: direct, tactical, strategic, etc.")


# ── Copywriting Framework ─────────────────────────────────────────────────────

COPYWRITING_FRAMEWORK = """
=== LAUNCH HOUSE EVENTS — COLD EMAIL COPYWRITING FRAMEWORK ===

ABOUT LAUNCH HOUSE EVENTS:
Cvent implementation specialists and event management outsourcing. Build inside Cvent for event and
marketing teams — registration, Flex, Attendee Hub, speaker portals, rush variants. Fixed-fee per
build. Run as overflow alongside in-house teams, not in place of them.

WHAT WE DO (only ever pitch from this list):
  - Cvent registration build & management
  - OnArrival check-in / badging staffing
  - Attendee Hub setup & content loading
  - Event-program overflow / surge support
  - Session & speaker logistics coordination
  - Post-event reporting & attendee analytics

THE PITCH IS ALWAYS: "we run it for you / we extend your team"
Never pitch Cvent licenses — the prospect already uses Cvent.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EMAIL STRUCTURE (every email, every step)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Line 1 — SITUATION RECOGNITION (1 sentence)
  Describe THEIR exact situation. Use a real signal from the lead context.
  Good: "Saw [company_name] has [specific event] on the calendar."
  Good: "[company_name] runs [N] events a year — registration builds must stack up fast."
  Good: "Noticed [company_name] is hiring a Cvent specialist right now."
  Bad: "I hope this email finds you well"
  Bad: "I wanted to reach out because..."
  Bad: Generic observations anyone could make without the lead data

Line 2 — VALUE PROP + PROOF (1-2 sentences MAX)
  What we do + a proof point. Choose angle based on step number (see rotation below).
  Good: "We build inside Cvent full-time — registration, Flex, Hub — so event teams don't have to."
  Good: "Teams in [industry] hand off builds to us when their calendar gets heavy."
  Bad: "We help companies leverage synergies to optimize their event technology ecosystem"

Optional — THE "SPECIFICALLY" LINE (1 sentence, only when their context varies)
  "Specifically, it looks like [company] runs [event type] events — that's exactly where we help most."

Line 3 — LOW-EFFORT CTA (1 sentence)
  Binary question. They should be able to reply in 5 words.
  Good: "Worth a look?"
  Good: "Useful to send two examples at your cadence?"
  Good: "15 min, or send what you have first?"
  Bad: "Would you be open to scheduling 15 minutes next Tuesday at 2pm?"
  Bad: "Let's explore a potential partnership opportunity"

Optional — PS LINE
  Only if body is short and there's a strong specific hook to add.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FOLLOW-UP SEQUENCE — STEP-BY-STEP ANGLE GUIDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1 (first email) — BEST SHOT
  Angle: Strongest available signal. Event-triggered > hiring signal > event volume > industry fit.
  Value prop: SAVE TIME ("so your team doesn't have to build it")
  Subject: 2-4 words (intrigue) OR whole offer if signal is thin.
    Examples: "[event_name] build support" / "Cvent overflow for [company]" / "Extra hands for event builds"
  Signal priority order (use the highest available):
    1. Upcoming verified event (0-120 days) — name it, give the date phrase, frame the build window
    2. Hiring Cvent/event staff — they're growing capacity, the timing is right
    3. High event volume — "[N] events a year" is the hook
    4. Company in event-heavy vertical — use industry framing
  Rush framing (event 0-30 days out): "X days to [event] — if anything's on the fix list, we hold rush capacity."
  Build window framing (event 31-120 days): "[event] in [date phrase] — the build plan is getting real."

STEP 2 (first follow-up, OWN SUBJECT LINE) — DIFFERENT VALUE PROP + CHECKLIST
  Philosophy: Treat this as a standalone email. Different subject, different angle, different value prop.
  Angle: MAKE MONEY / ADD CAPACITY ("do more events without adding headcount")
  Subject: resource or pain-point framing, different from Step 0.
    Examples: "Cvent pre-launch checklist" / "something useful, [first_name]" / "[company_name] build timeline"
  CRITICAL: Never start with "Following up", "Just checking in", "One more thought", "Checking back in".
  Lead with a punchy standalone first line as if they've never heard from you.
  ALWAYS include the checklist as a concrete value-exchange CTA — no exceptions.
  Format: "Cvent Pre-Launch QA Checklist -> {{checklist_link}}"
  Good opener examples:
    "Most event teams hit a wall when the calendar grows faster than headcount."
    "Fixed-fee builds mean no scope surprises when timelines compress."
  Structure: situation line -> value prop sentence -> checklist offer -> soft CTA ("if useful, take a look")

STEP 3 (second follow-up, NEW THREAD — new subject line) — DIFFERENT ANGLE ENTIRELY
  Philosophy: Start completely fresh. Different subject, treat it as first contact.
  Angle: SAVE MONEY ("fixed-fee, no time-and-materials surprise")
  Drop AI personalization if it would feel forced. Go direct with a universal pain.
  Good subject patterns: "question for [first_name]" (lowercase) / "[pain point phrase]"
  Good openers:
    "When you took the role at [company_name], did you inherit [specific challenge]?"
    "Most [role title] leaders tell me the same thing — [common pain]."
  Never reference previous emails. This stands completely alone.

STEP 4 (final email) — REDIRECT OR RESOURCE OFFER
  Philosophy: Last email. Close gracefully or give them something useful.
  Path A — Redirect: "If Cvent builds aren't your department, who handles them at [company_name]?"
  Path B — Resource + clean close: Offer the checklist if timing isn't right.
    Checklist token: {{checklist_link}}
  Path C — Clean close: "I'll stop here. If timing changes — a build, a rescue, an overflow week — door's open."
  Subject: "Closing the loop" / "Last note from me" / "Wrapping this up"
  Never say "final email" or "goodbye" explicitly.
  For marketing leadership titles: swap "clean load-in" for "successful launch".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUBJECT LINE STRATEGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Strategy A — 2-4 Words (Intrigue): Use when you have a real signal.
  "[event_name] build plan" / "Cvent capacity gap" / "Event builds stacking up?"
  Personalized lowercase: "question for [first_name]" NOT "Question for [first_name]"

Strategy B — Whole Offer (Self-selecting): Use when signal is thin.
  "Cvent build overflow for [company_name]" / "Extra Cvent hands when your team runs hot"

Banned subjects: "Curious" / "Quick question" / "Checking in" / "Following up" / "Touching base"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TONE BY SENIORITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Director / VP / Head of / C-suite:
  - Shorter email. 40-60 words total.
  - Strategic framing: "overflow capacity", "pressure valve", "pre-wired for scale"
  - CTAs lean optionality: "15 min, or send what you have?"
  - Never explain the product

Specialist / Coordinator / Manager:
  - Full structure OK. 60-90 words.
  - Tactical framing: "registration logic", "Attendee Hub cleanup", "rush turnarounds"
  - Direct CTAs: "Useful to send two examples?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DO NOT USE FOR PERSONALIZATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- LinkedIn anniversaries, work anniversaries, birthdays
- Funding dollar amounts in email body
- Layoffs or restructuring news
- Specific employee headcount numbers ("saw you grew to 247 employees")
- Personal social media posts
- Health, family, personal-life information
- Past employers (unless they mentioned it)
- Negative news (earnings misses, controversy, legal matters)
"""

# ── Main prompt ───────────────────────────────────────────────────────────────

PERSONALIZATION_SYSTEM_PROMPT = """You are the AI email writer for Launch House Events — a Cvent implementation and event management firm.

Your job is to WRITE the email from scratch using the lead's signals. Do NOT fill in a template.
Use the copywriting framework below to make every decision: which angle to lead with, what proof to use, how to phrase the CTA.

VOICE & TONE — non-negotiable:
Write like a sharp, self-aware founder texting a peer. Not a sales rep emailing a stranger.
- Short sentences. Then another short one. A longer one only when it earns its place.
- Start mid-thought. Skip the warm-up. "Saw your [X]." not "I wanted to reach out because..."
- Be specific. Use a real event name, a real number, a real detail from the lead context. Vague = deleted.
- Honest and direct. Say what you mean. No hedging ("perhaps", "maybe", "I think"), no softening, no throat-clearing.
- The ask is small and clear. "Worth a quick call?" not "explore a potential partnership opportunity."
- Pattern interrupts beat safe openers every time.
- Max 3-4 sentences in the body. Every word must earn its place.
- Active voice always. "We build registrations" not "We have built a platform that can build registrations."
- Light, peer-like tone is fine. Relatable is better than formal.
- NEVER use: "leverage", "synergies", "circle back", "touch base", "I hope this finds you well",
  "I wanted to reach out", "at your earliest convenience", "value-add", "bandwidth",
  "move the needle", "deep dive", "take this offline", "excited to", "would love to",
  "following up", "just checking in", "one more thought", "touching base",
  "We help companies" (banned unless immediately followed by a specific case study or metric).

THEM:US RATIO:
Write 3 sentences about them for every 1 sentence about us. The email must be about their situation,
not our product. If you're spending more than 1 sentence describing what we do, cut it.

"FROM MY EXPERIENCE" FRAMING:
When making a general claim about what most people in their role experience, frame it as personal
observation, not stated fact.
- Good: "From my experience, most association teams hit a wall when the calendar grows faster than headcount."
- Bad: "Most association teams hit a wall when..."
This one change makes the same claim feel earned rather than assumed.

PREVIEW TEXT:
Line 1 of the body is what appears in the inbox preview. Make it the most compelling line.
The recipient decides to open or delete based on subject + first line together.

OPENER PATTERNS — pick the one that fits the lead's situation:
- Status pressure: "Have you figured out how to [outcome] without adding headcount?"
- Soft humility: "I may be wrong, but do you have something in place for [area]?"
- Binary: "Is your [process] where you want it, or still a manual lift?"
- Direct observation: "Saw [company] has [specific event/signal]. [One-line implication]."
- Situation question: "When you took the role at [company], did you inherit [specific challenge]?"

CTA CATEGORIES — use one, keep it answerable in 5 words:
- Confirmation: "Is this still the case?" / "Worth exploring?"
- Value-exchange: "Useful to send two build examples?"
- Resource offer: "Want me to send it over?"

HARD RULES:
1. Write fresh prose. Never reference a template or use placeholder brackets like [X].
2. Use only signals that appear in the provided lead context. Never invent events, dates, or numbers.
3. Only recommend services from the catalog in the copywriting framework.
4. Keep email body under 90 words for specialist/coordinator, under 60 for director/VP/C-suite.
5. Subject line: 2-4 words OR whole offer. Never banned subjects (Curious, Quick question, etc.).
6. No exclamation marks. No wellness openers. One CTA maximum.
7. {{checklist_link}} may remain as-is — it is resolved server-side.
8. Do NOT include arbitrary URLs in the email body. The only allowed link token is {{checklist_link}}.
9. Resolve sender as the human BDR. The body_text is plain text. The body_html wraps it in <p> tags.
10. NEVER use em dashes (—). Use a regular hyphen (-) if you need a dash at all. Em dashes read as AI-written.
11. Do NOT include any signature, sign-off, name, or closing in body_text or body_html. End with the CTA line only. The signature (name, company, contact details) is appended automatically — if you write one it will appear twice.
"""


class PersonalizationAgent(BaseAgent):
    """Generates hyper-personalized email content using the coldoutboundskills copywriting framework."""

    async def run(
        self,
        lead_id: str,
        tenant_id: str,
        step_config: dict | None = None,
        lead_data: dict | None = None,
        enrichment_data: dict | None = None,
        research_data: dict | None = None,
        insights: list[dict] | None = None,
        sender_info: dict | None = None,
        previous_email_subject: str | None = None,
        previous_email_body: str | None = None,
        reply_intent: str | None = None,
    ) -> dict[str, Any]:
        llm = self.get_llm(temperature=0.7)
        parser = JsonOutputParser(pydantic_object=EmailOutput)

        # Build context block
        context_parts = []
        if lead_data:
            context_parts.append(f"**Lead & Company Info:**\n{lead_data}")
        if enrichment_data:
            context_parts.append(f"**Enrichment Data:**\n{enrichment_data}")
        if research_data:
            context_parts.append(f"**Research Findings (events, news, signals):**\n{research_data}")
        if insights:
            context_parts.append(
                "**AI Insights:**\n" + "\n".join(f"- {i.get('content', '')}" for i in insights)
            )
        if sender_info:
            context_parts.append(f"**Sender Info:**\n{sender_info}")
        if previous_email_subject or previous_email_body:
            prev_block = "**Previous Email Sent to This Lead:**"
            if previous_email_subject:
                prev_block += f"\nSubject: {previous_email_subject}"
            if previous_email_body:
                trimmed = previous_email_body[:1500].strip()
                if len(previous_email_body) > 1500:
                    trimmed += "\n[…]"
                prev_block += f"\n\n{trimmed}"
            prev_block += "\n\nNOTE: For follow-up emails, do NOT reference this previous email. Write a standalone email with a completely different angle and value prop. The only case to use this context is for reply_intent handling."
            context_parts.append(prev_block)
        if reply_intent:
            context_parts.append(f"**Reply Intent Detected:** {reply_intent}")

        step_num = step_config.get("step", 1) if step_config else 1
        context = "\n\n".join(context_parts) if context_parts else "Limited data available — use best inference."

        rewrite_notes = (step_config or {}).get("rewrite_notes", "")
        strategy_notes = (step_config or {}).get("strategy_notes", "")
        extra_instructions = ""
        if rewrite_notes:
            extra_instructions += f"\n\n**REWRITE NOTES (from QA review — fix these specific issues):**\n{rewrite_notes}"
        if strategy_notes:
            extra_instructions += f"\n\n**STRATEGY CONTEXT (from performance analysis — apply these learnings):**\n{strategy_notes}"

        messages = [
            SystemMessage(content=PERSONALIZATION_SYSTEM_PROMPT),
            HumanMessage(content=f"""
Write the outbound email for this lead. Step number in the sequence: {step_num}.

Use the copywriting framework below to pick the right angle and write the email from scratch.
Do not fill in a template — write original prose using the signals from the lead context.

**Lead Context:**
{context}

**Copywriting Framework:**
{COPYWRITING_FRAMEWORK}
{extra_instructions}

{parser.get_format_instructions()}
"""),
        ]

        result = await self.invoke_with_retry(llm, messages)
        try:
            parsed: dict = parser.parse(result.content)
        except Exception:
            return {"raw_response": result.content, "parse_error": True}

        # ── Wrap body content in the LaunchHouse branded HTML template ────────
        try:
            from app.tools.email_renderer import HeaderStyle, render_email_html, render_email_plain

            raw_body = parsed.get("body_text") or parsed.get("body_html") or ""
            # Replace em dashes with a plain hyphen regardless of LLM output
            raw_body = raw_body.replace("—", " - ")
            # Strip any LLM-appended signature (name/email/company block or "Best,")
            raw_body = _strip_body_signatures(raw_body)

            _sender = sender_info if isinstance(sender_info, dict) else {}
            _checklist_link = (
                _sender.get("checklist_link")
                or _sender.get("checklist_url")
                or "https://launch-house.uk/checklist"
            )
            _sender_cal = _sender.get("calendar_link") or _sender.get("sender_calendar_link") or ""
            _sender_email = _sender.get("sender_email") or "sam@launchhouse.events"
            _sender_name = _resolve_sender_name(_sender_email, _sender.get("sender_display_name", ""))

            if "{{checklist_link}}" in raw_body:
                raw_body = raw_body.replace("{{checklist_link}}", _checklist_link)

            # Checklist CTA: button in HTML, plain-text fallback
            _checklist_display = re.sub(r"^https?://", "", _checklist_link).rstrip("/")
            _cta_line_re = re.compile(r"^\s*Cvent Pre-Launch QA Checklist\s*[→\-]*>?\s*.+$", re.I | re.M)
            _cta_plain = f"Download the Cvent Pre-Launch QA Checklist: {_checklist_display}"
            _cta_button = (
                f'<a href="{_checklist_link}" '
                f'style="display:inline-block;padding:8px 13px;border-radius:6px;'
                f'background:#1c8ed4;color:#ffffff;text-decoration:none;font-weight:600;'
                f'font-size:11px;line-height:1.2;">'
                f'Download the Cvent Pre-Launch QA Checklist</a>'
            )
            raw_body_plain = _cta_line_re.sub(_cta_plain, raw_body)
            raw_body_html = _cta_line_re.sub(_cta_button, raw_body)

            # Same template for every email — compact signature (no calendar button)
            branded_html = render_email_html(
                body_text=raw_body_html,
                sender_name=_sender_name,
                sender_company="LaunchHouse Events",
                sender_role="Cvent Registration & Event Technology Operations",
                sender_site_url="https://launchhouse.events/",
                sender_calendar_link=_sender_cal,
                sender_phone="+1 (571) 444-8523",
                sender_email=_sender_email,
                header_style=HeaderStyle.SLIM,
                compact_signature=True,
            )
            branded_html = re.sub(
                r'<p[^>]*>\s*Download the Cvent Pre-Launch QA Checklist:\s*<a href="([^"]+)"[^>]*>[^<]+</a>\s*</p>',
                (
                    r'<div style="margin:14px 0 8px;">'
                    r'<a href="\1" '
                    r'style="display:inline-block;padding:8px 13px;border-radius:6px;'
                    r'background:#1c8ed4;color:#ffffff;text-decoration:none;font-weight:600;'
                    r'font-size:11px;line-height:1.2;">'
                    r'Download the Cvent Pre-Launch QA Checklist</a></div>'
                ),
                branded_html,
                flags=re.I,
            )
            plain_text = render_email_plain(
                body_text=raw_body_plain,
                sender_name=_sender_name,
                sender_site_url="https://launchhouse.events/",
                sender_phone="+1 (571) 444-8523",
                sender_email=_sender_email,
            )
            parsed["body_html"] = branded_html
            parsed["body_text"] = plain_text
        except Exception as render_err:
            import logging as _log
            _log.getLogger(__name__).warning(
                "email_renderer failed, using raw LLM body: %s", render_err
            )

        return parsed
