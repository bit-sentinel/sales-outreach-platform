"""
Personalization Agent – generates hyper-personalized email content.

Template system based on Launch House Events outbound playbook (email templates.docx):
- Core Sequence (T1–T4): Day 1 Initial · Day 4 Value Add · Day 9 Bump · Day 20 Break-up
- Trigger Variants (T5–T9): Event trigger · Fit-based · 0-30 days · 31-120 days · News trigger
- Reply Handlers (T10–T14): Positive interest · More info · Not now · Already have support · Wrong contact
- Scenario Templates (T15–T17): Voicemail follow-up · Meeting confirmation · Post-call recap
"""

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent


class EmailOutput(BaseModel):
    subject: str = Field(description="Email subject line chosen from the template options, under 8 words")
    body_html: str = Field(description="HTML email body with all tokens resolved")
    body_text: str = Field(description="Plain text email body with all tokens resolved")
    personalization_hooks: list[str] = Field(description="Tokens and personalization points used")
    template_used: str = Field(description="Which template was selected and why, e.g. 'Template 8 — event 31-120 days out'")
    tone: str = Field(description="Tone used: professional, casual, tactical, etc.")


# ── Template Reference ────────────────────────────────────────────────────────

TEMPLATES = """
=== LAUNCH HOUSE EVENTS — OUTBOUND EMAIL TEMPLATE SYSTEM ===

ABOUT LAUNCH HOUSE EVENTS:
Cvent implementation specialists and event management outsourcing. Build inside Cvent for event and marketing teams — registration, Flex, Attendee Hub, speaker portals, rush variants. Fixed-fee per build. Run as overflow alongside in-house teams, not in place of them. Sender signs as a human BDR (use sender_first_name/sender_last_name).

SENDER SIGNATURE FORMAT (always end emails with — nothing else after this):
Best,
{{sender_first_name}}

──────────────────────────────────────────────────────────────
TEMPLATE SELECTION HIERARCHY (follow strictly, top = highest priority):
1. Reply received → Templates 10–14 based on reply intent
2. Verified event 0–30 days away → Template 7 (rush framing only)
3. Verified event 31–120 days away → Template 8 (build scoping — highest-converting)
4. Verified event 120+ days away → Template 5 (no urgency)
5. Recent news ≤45 days tied to events → Template 9
6. No event/news but event activity inferable from category/hiring → Template 6
7. If step_number=1, default → Template 1
8. If step_number=2 (Day 4 follow-up) → Template 2
9. If step_number=3 (Day 9 follow-up) → Template 3  
10. If step_number=4 (Day 20 final) → Template 4
SUPPRESSION: After Template 4, no new sequence within 90 days. Never chain more than 4 emails.
──────────────────────────────────────────────────────────────

=== CORE SEQUENCE ===

TEMPLATE 1 — Initial Outreach (Day 1, default first-touch)
Subject options: "Cvent build capacity for {{company_name}}" / "Extra hands on your event builds" / "Quick one, {{first_name}}"
Full:
Hi {{first_name}},

{{company_name}}'s event cadence — {{event_cadence_observation}} — usually means Cvent build work competes with everything else your team owns.

We build inside Cvent for a living. Registration sites, Flex pages, form logic, Attendee Hub, speaker portals — Simple Builds through Complex, with rush variants when timelines compress.

Not pitching a platform. Just an extra set of hands for the weeks your team runs hot.

Useful to send two recent build examples at your cadence?

{{sender_first_name}}

Short (Director+):
Hi {{first_name}},

{{company_name}}'s event cadence is heavy enough that Cvent build work likely competes with everything else.

We build inside Cvent — sites, forms, Flex, Attendee Hub — as overflow for teams that need speed without adding headcount.

Want two examples at your cadence?

{{sender_first_name}}

Tokens: {{first_name}}, {{company_name}}, {{event_cadence_observation}} (short specific phrase e.g. "a monthly customer event series")
Rules: Use only if event cadence is verifiable. Suppress if event in next 120 days found (use T5/7/8 instead). Full version for Specialist/Coordinator. Short version for Director+.

──────────────────────────────────────────────────────────────
TEMPLATE 2 — Value Add (Day 4 follow-up)
Subject options: "One thing that might be useful, {{first_name}}" / "Cvent resource — worth a look?" / "Quick follow-up, {{first_name}}"
Full:
Hi {{first_name}},

Sent a note last week about Cvent build overflow for {{company_name}} — wanted to add something concrete before moving on.

{{value_add_piece}} — relevant given {{value_add_relevance}}.

No pitch. If it's useful, worth a 15-minute conversation. If not, no follow-up after this.

Want it, or shall I close this out?

{{sender_first_name}}

Short:
Hi {{first_name}},

One thing that might be useful: {{value_add_piece}}.

Relevant because {{value_add_relevance}}. Worth a look?

{{sender_first_name}}

Tokens: {{first_name}}, {{company_name}}, {{value_add_piece}} (specific resource e.g. "a post-event data checklist for Cvent"), {{value_add_relevance}} (why it fits them)
Rules: Always references T1 briefly. Offers something concrete. Ends with binary yes/no.

──────────────────────────────────────────────────────────────
TEMPLATE 3 — Bump (Day 9, third touch)
Subject options: "Worth a reply or not?" / "Close this out?" / "Two-line check-in"
Full:
Hi {{first_name}},

Happy to close this thread if build support isn't on the radar.

If there's a version that could be useful — an event in 60 days, a Hub rebuild, or just overflow hands — one line tells me whether to stay in touch or move on.

{{sender_first_name}}

Short:
Hi {{first_name}},

Worth staying in touch, or close this out? Either reply works.

{{sender_first_name}}

Rules: Do NOT re-pitch. Suppress if prospect opened previous email 3+ times. Cap at 50 words.

──────────────────────────────────────────────────────────────
TEMPLATE 4 — Break-up (Day 20, final touch)
Subject options: "Closing the loop" / "Last note from me" / "Wrapping this up"
Full:
Hi {{first_name}},

I'll stop here — your inbox doesn't need more from me.

If timing changes later — a new event on the calendar, a Cvent build you'd rather not staff in-house, a rescue on something stalled — door's open. No follow-up needed.

Wishing your next event a clean load-in.

{{sender_first_name}}

Short:
Hi {{first_name}},

I'll stop here. If timing changes — a build, a rescue, an overflow week — come back anytime.

Good luck with the next one.

{{sender_first_name}}

Rules: Never say "final email" or "goodbye" in subject. Swap "clean load-in" → "successful launch" for marketing leadership titles. Move lead to nurture after this.

=== TRIGGER VARIANTS ===

──────────────────────────────────────────────────────────────
TEMPLATE 5 — Initial Outreach, Event Trigger (verified event, any date range)
Subject options: "{{event_name}} — build support?" / "Before {{event_name}}" / "Cvent help on {{event_name}}"
Full:
Hi {{first_name}},

{{event_name}} is on the calendar for {{event_date_phrase}}. Congrats on getting it to this stage — the build stretch is usually where good teams run out of hours, not talent.

We build inside Cvent for event teams: registration, Flex, form logic, Attendee Hub, speaker workflows. If any part of the lift would be easier handed off than done in-house, we can scope it cleanly.

Even if the core build is done, rush work and last-mile fixes are where we usually help most.

Useful to share two examples from similar events?

{{sender_first_name}}

Short:
Hi {{first_name}},

{{event_name}} in {{event_date_phrase}} — the build stretch is where hours get thin.

We build inside Cvent for event teams. Registration, Flex, Hub, rush fixes. If anything is easier handed off, happy to scope it.

Two examples from similar events?

{{sender_first_name}}

Tokens: {{first_name}}, {{event_name}} (exact public-facing name, never abbreviated), {{event_date_phrase}} (e.g. "late June", "the week of Sept 9", "mid-Q4")
Rules: Use ONLY if event is verifiable on public site/press. If 0-30 days out → use T7 instead. If 31-120 days → use T8 instead. Never write "I noticed" without confirmed evidence.

──────────────────────────────────────────────────────────────
TEMPLATE 6 — Initial Outreach, Fit-Based (no event found, activity inferable)
Subject options: "Cvent build capacity — {{company_name}}" / "Overflow support for {{company_name}} events" / "Built for {{company_vertical_short}} event teams"
Full:
Hi {{first_name}},

Teams in {{company_vertical_or_motion}} usually carry heavier event calendars than headcount accounts for — owned events, partner activations, and internal programs all needing Cvent builds on compressed timelines.

That's the lane we sit in. We're Cvent developers by trade, running as overflow for event and marketing teams: Simple through Complex builds, Attendee Hub, rush variants when something has to ship in days.

No meeting ask. If it's useful, I can send a one-pager on how we engage and what the economics look like.

Want it?

{{sender_first_name}}

Short:
Hi {{first_name}},

Teams in {{company_vertical_or_motion}} carry more event volume than headcount usually accounts for.

We're Cvent developers — overflow hands for event teams. Simple to Complex builds, Attendee Hub, rush work.

One-pager on how we engage?

{{sender_first_name}}

Tokens: {{first_name}}, {{company_name}}, {{company_vertical_or_motion}} (e.g. "enterprise SaaS", "financial services field marketing"), {{company_vertical_short}} (1-2 word for subject, e.g. "SaaS", "FinServ")
Rules: Use when event activity is inferable but no specific event confirmed. Vague is safer than wrong.

──────────────────────────────────────────────────────────────
TEMPLATE 7 — Upcoming Event, 0–30 Days Out (RUSH framing)
Subject options: "{{event_name}} — rush capacity" / "Last-mile Cvent help before {{event_name}}" / "Anything left to fix on {{event_name}}?"
Full:
Hi {{first_name}},

{{event_name}} is {{days_out}} days out — the window where small Cvent fixes take longer than they should because everything else is also on fire.

We hold rush capacity for exactly this stretch. Form logic fixes, Flex page edits, Attendee Hub cleanup, registration flow corrections — same-day or next-day turnaround.

If anything's still on the list, one-line reply and I'll confirm feasibility within the hour. No meeting needed to scope small work.

{{sender_first_name}}

Short:
Hi {{first_name}},

{{days_out}} days to {{event_name}}. If anything small in Cvent is still on the fix list — form logic, Flex, Hub — we hold rush capacity for this window.

One line and I'll confirm in the hour.

{{sender_first_name}}

Tokens: {{first_name}}, {{event_name}}, {{days_out}} (integer 1-30)
Rules: Only if rush capacity genuinely available. Do NOT pitch new builds. Inside 7 days → smallest possible ask only.

──────────────────────────────────────────────────────────────
TEMPLATE 8 — Upcoming Event, 31–120 Days Out (BUILD SCOPING — highest-converting)
Subject options: "Cvent build plan for {{event_name}}?" / "{{event_name}} — build window" / "Scoping {{event_name}}?"
Full:
Hi {{first_name}},

{{event_name}} in {{event_date_phrase}} — close enough that the build plan is getting real.

If any of it is likely to compete with everything else your team owns, we'll take it. Full Cvent build coverage — registration, Flex, form logic, Attendee Hub, speaker portals — scoped fixed-fee, no time-and-materials surprise.

Two ways forward: a 15-minute scoping call, or send over what you have and we'll come back with a fit read and proposal outline. Whichever's faster for you.

{{sender_first_name}}

Short:
Hi {{first_name}},

{{event_name}} in {{event_date_phrase}}. If the Cvent build is likely to compete with your team's other work, we'll take it — fixed-fee, full coverage.

15 min, or send what you have first?

{{sender_first_name}}

Tokens: {{first_name}}, {{event_name}}, {{event_date_phrase}}
Rules: Default for 31-120 day window. "Send what you have" CTA outperforms meeting asks for Director level.

──────────────────────────────────────────────────────────────
TEMPLATE 9 — News Trigger (recent news ≤45 days, tied to events)
Subject options: "Congrats on {{news_short_phrase}}" / "{{news_short_phrase}} — quick thought" / "Event impact of {{news_short_phrase}}"
Full:
Hi {{first_name}},

Saw the news on {{news_headline_short}} — congrats.

News like that usually expands the event calendar before it eases anything: {{news_event_implication}}. If any of it turns into Cvent build work, we run as overflow for event and marketing teams — Simple through Complex, Attendee Hub, rush variants.

Not asking for a meeting off the back of a press release. But if it's useful to have a partner pre-wired for when the calendar expands, I can send a one-pager.

{{sender_first_name}}

Short:
Hi {{first_name}},

Congrats on {{news_headline_short}} — usually means more events on the calendar, sooner than planned.

We're Cvent developers running as overflow. Want a one-pager for when the build load spikes?

{{sender_first_name}}

Tokens: {{first_name}}, {{news_short_phrase}} (2-4 words for subject e.g. "the Series C"), {{news_headline_short}} (sentence-ready e.g. "your Series C"), {{news_event_implication}} (one line connecting news to events)
Rules: News must be public, recent (≤45 days), credibly tied to event motion. Congratulations must name the specific news. Leadership change → welcome note framing, drop congrats.

=== REPLY HANDLERS ===

──────────────────────────────────────────────────────────────
TEMPLATE 10 — Positive Interest Reply
Subject: Re: {{previous_subject}}
Full:
Hi {{first_name}},

Glad it landed. Two ways forward:

1) 20-minute intro this week — send a window that works and I'll confirm.

2) If you'd rather scope offline, send what you have — an event brief, a Cvent spec, a list of what's on the build roadmap — and I'll come back with a fit read and proposal outline.

Either works.

{{sender_first_name}}
Rules: Respond within 4 hours. Do not re-pitch. Acknowledge specific service if they named one.

──────────────────────────────────────────────────────────────
TEMPLATE 11 — "Send More Info" Reply
Subject: Re: {{previous_subject}} — overview attached
Full:
Hi {{first_name}},

Attached is a short overview — engagement model, build tiers (Simple through Complex, plus Abstract and Attendee Hub), rush options, and two examples from teams running cadences similar to {{company_name}}.

Two notes: Fixed-fee per build, scoped before work starts. We sit alongside in-house team, not in place of them.

After you've had a look, worth 15 minutes to pressure-test fit against your actual build pipeline?

{{sender_first_name}}

──────────────────────────────────────────────────────────────
TEMPLATE 12 — "Not Now" Reply
Subject: Re: {{previous_subject}} — understood
Full:
Hi {{first_name}},

Understood — appreciate the directness.

I'll circle back {{revisit_window}}. If anything shifts before — a new event added, a Cvent build that needs to land fast, a rescue on something stalled — I'm an email away.

Thanks for the reply.

{{sender_first_name}}

Tokens: {{revisit_window}} (e.g. "in 60 days", "after your next event", "in Q3". Default: 60 days)
Rules: Do NOT try to convert "not now" into "now." Log revisit window and actually return at that time.

──────────────────────────────────────────────────────────────
TEMPLATE 13 — "Already Have Support" Reply
Subject: Re: {{previous_subject}} — makes sense
Full:
Hi {{first_name}},

Makes sense — most teams we work well with already have primary coverage, in-house or via an agency.

Where we usually fit is the overflow lane: weeks the primary team is maxed, rush builds that can't wait for a full scoping cycle, and Cvent rescues when something's stalled inside the existing setup.

Nothing to switch, no retainer. Worth keeping us as a pressure valve for those moments?

If yes, I'll send a one-pager you can file for when you need it.

{{sender_first_name}}
Rules: Never disparage existing team/agency. "Pressure valve" framing. If they accept → long nurture, not active sequence.

──────────────────────────────────────────────────────────────
TEMPLATE 14 — Wrong Contact / Referral Ask
Subject: Re: {{previous_subject}} — quick ask
Full:
Hi {{first_name}},

Appreciate the note — and apologies for the mis-aim.

Two easy options:

1) Reply with the name of whoever owns Cvent builds or event ops, and I'll take it from there.

2) Forward this thread with a one-line intro and I'll handle the rest.

Either works. Thanks for the redirect.

{{sender_first_name}}

=== SCENARIO TEMPLATES ===

──────────────────────────────────────────────────────────────
TEMPLATE 15 — Voicemail Follow-Up (within 30 min of voicemail)
Subject: "Voicemail just now — easier by email" / "Tried you by phone, {{first_name}}"
Full:
Hi {{first_name}},

Left you a voicemail a minute ago — no callback needed, easier by email.

Short context: we're Cvent developers running full-time as overflow for event and marketing teams. Thought {{company_name}} might find value in extra hands for builds — registration, Flex, Attendee Hub, rush work.

Worth 15 minutes? If not, one-line reply and I'll close the thread.

{{sender_first_name}}
Rules: Send ONLY if voicemail was actually left. Within 30 minutes.

──────────────────────────────────────────────────────────────
TEMPLATE 16 — Meeting Confirmation
Subject: "Confirmed — {{meeting_day}} at {{meeting_time}}" / "{{first_name}} ↔ Launch House Events — {{meeting_day}}"
Full:
Hi {{first_name}},

Confirmed for {{meeting_day}} at {{meeting_time}} ({{timezone}}). Calendar invite is in your inbox.

Fifteen minutes, focused on three things:
— Your current Cvent build load and where the pressure points are
— Two or three examples from our side relevant to your cadence
— Whether overflow makes sense, and if so, what shape

If anything specific would help us prep — a current build, a stalled project, an Attendee Hub plan — send it ahead.

Talk {{meeting_day_short}}.

{{sender_first_name}}
Rules: Send immediately after booking. Three-item agenda is required (anti-no-show). 24-hour reminder if meeting is 5+ business days out.

──────────────────────────────────────────────────────────────
TEMPLATE 17 — Post-Call Recap
Subject: "Recap — {{company_name}} ↔ Launch House Events" / "Notes and next steps from today"
Full:
Hi {{first_name}},

Thanks for the time today. Quick recap so nothing slips:

What we heard:
— {{discussion_point_1}}
— {{discussion_point_2}}

Where we think we can help:
— {{help_area_1}}
— {{help_area_2}}

Next steps:
— On us: {{our_next_step}} by {{our_due_date}}
— On you: {{their_next_step}}
— Reconvene: {{reconvene_date_or_trigger}}

Anything off or missing? Easier to fix now than later.

{{sender_first_name}}
Rules: Send within 2 hours of call. Use prospect's own language. Name their next step explicitly.

=== DO NOT USE THESE SIGNALS FOR PERSONALIZATION ===
- LinkedIn anniversaries, work anniversaries, birthdays
- Funding dollar amounts in email body
- Layoffs or restructuring news
- Specific employee headcount numbers ("saw you grew to 247 employees")
- Personal social media posts
- Health, family, personal-life information
- Past employers (unless they mentioned it)
- Negative news (earnings misses, controversy, legal matters)

=== TONE BY SENIORITY ===
Director / VP / Head of:
- Use SHORTER version of every template
- Strategic framing: "overflow capacity", "pressure valve", "pre-wired for scale"
- Drop tactical jargon unless they use it first
- CTAs lean optionality ("two paths")
- Never explain the product

Specialist / Coordinator / Manager:
- Use FULL version of every template
- Tactical framing: "registration logic", "Attendee Hub cleanup", "rush turnarounds"
- Insider language welcome
- CTAs more direct ("15 minutes this week?")

Universal rules:
- Never "hope you're well" or wellness preambles
- Never exclamation marks
- Never lead with a question about their tools or stack
- One clear CTA maximum
- Under 130 words for cold emails
"""

# ── Main prompt ───────────────────────────────────────────────────────────────

PERSONALIZATION_SYSTEM_PROMPT = """You are the AI email writer for Launch House Events — a Cvent implementation and event management firm. Your ONLY job is to select the right template from the playbook and fill in every token with real, specific data from the lead context.

CRITICAL RULES:
1. Select the template using the strict hierarchy in the playbook. Higher-priority signals always win.
2. Every token ({{token_name}}) MUST be resolved with real data. No raw token may appear in the output.
3. If a token cannot be filled confidently, use a reasonable specific inference — never a generic placeholder.
4. The email must read as written by a human BDR, not generated by an AI.
5. Subject line must come from the template's listed options, adapted to the specific lead.
6. No exclamation marks. No wellness openers. No generic phrases.
7. Resolve {{sender_first_name}} using the provided sender info. Do NOT include URLs, calendar links, or website addresses in the email body — those are added separately.
8. The body_text field must be the plain-text version. The body_html field wraps it in simple <p> tags.
"""


class PersonalizationAgent(BaseAgent):
    """Generates hyper-personalized email content using the Launch House Events template playbook."""

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
                # Trim to first 1500 chars to avoid bloating the prompt
                trimmed = previous_email_body[:1500].strip()
                if len(previous_email_body) > 1500:
                    trimmed += "\n[…]"
                prev_block += f"\n\n{trimmed}"
            prev_block += "\n\nIMPORTANT: The follow-up must reference the specific value/offer from this previous email — not a generic 'sent you a note'. Build directly on what was said."
            context_parts.append(prev_block)
        if reply_intent:
            context_parts.append(f"**Reply Intent Detected:** {reply_intent}")

        step_num = step_config.get("step", 1) if step_config else 1
        context = "\n\n".join(context_parts) if context_parts else "Limited data available — use best inference."

        messages = [
            SystemMessage(content=PERSONALIZATION_SYSTEM_PROMPT),
            HumanMessage(content=f"""
Generate the outbound email for this lead. Step number in the sequence: {step_num}.

Use the template playbook below to select the right template and fill in all tokens.

**Lead Context:**
{context}

**Template Playbook:**
{TEMPLATES}

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

            # Determine sender info from context
            _sender = sender_info or {}
            if isinstance(_sender, str):
                # sender_info was passed as a string repr; use defaults
                _sender = {}
            _sender_name = _sender.get("first_name") or _sender.get("name") or "Sameera Gurung"
            _sender_company = _sender.get("company") or "LaunchHouse Events"
            _sender_role = _sender.get("role") or "Cvent Registration & Event Technology Operations"
            _sender_site = _sender.get("site_url") or _sender.get("company_site_url") or "https://launchhouse.events/"
            _sender_cal = _sender.get("calendar_link") or _sender.get("sender_calendar_link") or ""

            # All 4 core sequence templates use slim header per spec
            _step = step_config.get("step", 1) if step_config else 1
            _header = HeaderStyle.SLIM

            # Use compact signature for senior contacts (Director+) OR steps 3+ (Day 9 Bump, Day 20 Break-up)
            _lead = lead_data or {}
            if isinstance(_lead, str):
                _lead_lower = _lead.lower()
                _compact = _step >= 3 or any(t in _lead_lower for t in ("director", "vp ", "vice president", "head of", "chief", " coo", " cmo", " cto", " ceo"))
            else:
                _title = str(_lead.get("title", "") or _lead.get("job_title", "")).lower()
                _compact = _step >= 3 or any(t in _title for t in ("director", "vp ", "vice president", "head of", "chief", "coo", "cmo", "cto", "ceo"))

            branded_html = render_email_html(
                body_text=raw_body,
                sender_name=_sender_name,
                sender_company=_sender_company,
                sender_role=_sender_role,
                sender_site_url=_sender_site,
                sender_calendar_link=_sender_cal,
                header_style=_header,
                compact_signature=_compact,
            )
            plain_text = render_email_plain(
                body_text=raw_body,
                sender_name=_sender_name,
                sender_site_url=_sender_site,
                sender_calendar_link=_sender_cal,
            )
            parsed["body_html"] = branded_html
            parsed["body_text"] = plain_text
        except Exception as render_err:
            import logging as _log
            _log.getLogger(__name__).warning(
                "email_renderer failed, using raw LLM body: %s", render_err
            )

        return parsed
