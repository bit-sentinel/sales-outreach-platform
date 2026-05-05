# Campaign, Email Drafting & Replies Strategy

**Sales Outreach Platform — Internal Technical Reference**  
*Version 1.0 — LaunchHouse Events*

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture](#2-system-architecture)
3. [Data Model](#3-data-model)
4. [Campaign Lifecycle](#4-campaign-lifecycle)
5. [Sequence Configuration](#5-sequence-configuration)
6. [Campaign Launch Flow](#6-campaign-launch-flow)
7. [Per-Lead Email Generation](#7-per-lead-email-generation)
8. [Test Mode](#8-test-mode)
9. [Email Template System (T1–T17)](#9-email-template-system-t1t17)
10. [Template Selection Hierarchy](#10-template-selection-hierarchy)
11. [Seniority-Based Tone Rules](#11-seniority-based-tone-rules)
12. [Email Delivery — SendGrid Integration](#12-email-delivery--sendgrid-integration)
13. [Reply Ingestion — IMAP Polling](#13-reply-ingestion--imap-polling)
14. [AI Reply Analysis](#14-ai-reply-analysis)
15. [Follow-Up Scheduling](#15-follow-up-scheduling)
16. [Suppression & Compliance](#16-suppression--compliance)
17. [Metrics & Tracking](#17-metrics--tracking)
18. [Business Logic & Positioning](#18-business-logic--positioning)
19. [Example Email — Template T8](#19-example-email--template-t8)
20. [Operational Runbook](#20-operational-runbook)
21. [Current Limitations & Future Direction](#21-current-limitations--future-direction)

---

## 1. Executive Summary

The campaign system is the core revenue engine of the Sales Outreach Platform. It orchestrates the full lifecycle of B2B cold outreach for LaunchHouse Events — a Cvent implementation and event management firm. Every campaign targets event industry professionals (Conference Directors, VP Events, Event Coordinators) who are either already running events on Cvent or managing a programme that could benefit from specialist implementation support.

The system handles:

- **Multi-step drip sequences** driven by Celery beat scheduling
- **AI-generated, hyper-personalised emails** drawn from a 17-template playbook, weighted by event timing signals, news triggers, and reply intent
- **SendGrid delivery** with per-sender rate limits, daily warm-up tracking, and full event callbacks
- **Gmail IMAP reply ingestion** with AI-powered intent classification (9 categories), sentiment scoring, and auto-drafted suggested responses
- **Follow-up scheduling** and suppression logic that prevent over-messaging

The system is intentionally niche: it is purpose-built for the Cvent implementation vertical, not a generic email automation tool.

---

## 2. System Architecture

```
┌────────────────────────────────────────────────────────────┐
│                        CAMPAIGN ENGINE                     │
│                                                            │
│  API (FastAPI)                                             │
│   └─► CampaignService.launch()                             │
│         └─► execute_campaign.delay(campaign_id)  ──┐       │
│                                                    │       │
│  Celery Worker                                     ▼       │
│   ├─► process_campaign_lead(campaign_lead_id)              │
│   │     ├─► PersonalizationAgent.run()  (Claude AI)        │
│   │     ├─► Message(status=draft) created                  │
│   │     ├─► FollowUp scheduled                             │
│   │     └─► send_email.delay(message_id)                   │
│   │                                                        │
│   ├─► send_email(message_id)                               │
│   │     └─► SendGrid API  ──► EmailEvent(sent)             │
│   │                                                        │
│   ├─► check_replies()  [beat, every 15 min]                │
│   │     ├─► Gmail IMAP                                     │
│   │     └─► ReplyAnalysisAgent.run()  (Claude AI)          │
│   │           └─► Reply record + suggested_response        │
│   │                                                        │
│   └─► process_follow_ups()  [beat, every 5 min]            │
│         └─► process_campaign_lead(campaign_lead_id)        │
│                                                            │
│  PostgreSQL    Redis (EventBus)    SendGrid    Gmail IMAP  │
└────────────────────────────────────────────────────────────┘
```

**Key technology choices:**
| Component | Technology | Rationale |
|---|---|---|
| Async task queue | Celery + Redis | Decouple email sends from API response cycle |
| LLM | Claude (claude-3-5-sonnet-20241022) | Superior instruction-following for template enforcement |
| Email delivery | SendGrid | Deliverability, event webhooks, HTML/text support |
| Reply ingestion | Gmail IMAP | Direct inbox access; no webhook dependency |
| Database | PostgreSQL + asyncpg | JSONB for flexible sequence/personalization storage |

---

## 3. Data Model

### 3.1 Campaign

The top-level entity representing an outreach campaign.

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `tenant_id` | UUID FK | Owning tenant |
| `name` | String | Human-readable campaign name |
| `description` | Text | Optional notes |
| `status` | Enum | `draft / active / paused / completed / archived` |
| `sequence` | JSONB | Array of step objects (see §5) |
| `sender_account_id` | UUID FK? | Optional fixed sender (overrides system default) |
| `total_leads` | Int | Denormalized count of enrolled leads |
| `sent_count` | Int | Emails sent across all steps |
| `open_count` | Int | Email opens tracked |
| `click_count` | Int | Link clicks tracked |
| `reply_count` | Int | Replies received |
| `bounce_count` | Int | Hard/soft bounces |
| `launched_at` | Timestamp? | First activation timestamp (never overwritten) |
| `completed_at` | Timestamp? | Campaign completion timestamp |

### 3.2 CampaignLead

Junction table linking a Lead to a Campaign, tracking per-lead progress through the sequence.

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `campaign_id` | UUID FK | Parent campaign |
| `lead_id` | UUID FK | Target lead |
| `status` | Enum | `pending / active / completed / replied / bounced / unsubscribed / paused` |
| `current_step` | Int | Next sequence step index to execute |
| `next_action_at` | Timestamp? | When the next email should fire |
| `personalization_data` | JSONB | Arbitrary slot — stores `test_email_override` in test mode |

### 3.3 Message

Every outbound email draft and every inbound reply is stored as a Message record.

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `campaign_id` | UUID FK | Parent campaign |
| `lead_id` | UUID FK | Target lead |
| `tenant_id` | UUID FK | Owning tenant |
| `direction` | Enum | `outbound / inbound` |
| `status` | Enum | `draft / queued / sending / sent / delivered / bounced / failed` |
| `subject` | String | Email subject line |
| `body_html` | Text | HTML version of the body |
| `body_text` | Text | Plain-text version of the body |
| `sequence_step` | Int? | Which step in the sequence this message corresponds to |
| `ai_generated` | Bool | Whether AI wrote this message |
| `message_id` | String? | During draft creation: stores recipient email. Overwritten with SendGrid X-Message-Id after send. |
| `personalization_hooks` | JSONB | Array of hook strings, e.g. `["event: Cvent Summit 2025", "template: T8"]` |
| `error_message` | String? | Populated on delivery failure |

> **Design note on `message_id` dual-use**: The field is used as a temporary scratch space to pass the resolved `to_email` from the campaign task (where lead context is available) to the send task (which otherwise only has the message ID). The field is overwritten by the actual SendGrid message ID after a successful send.

### 3.4 EmailEvent

Individual delivery events appended throughout the email lifecycle.

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `message_id` | UUID FK | Parent message |
| `event_type` | String | `sent / delivered / opened / clicked / bounced / complained / unsubscribed` |
| `event_data` | JSONB | Provider-specific payload |
| `occurred_at` | Timestamp | Event time (defaults to now) |

### 3.5 FollowUp

Scheduled task records that drive the drip sequence forward.

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `campaign_lead_id` | UUID FK | Which lead/campaign to advance |
| `scheduled_at` | Timestamp | When to fire |
| `status` | Enum | `scheduled / processing` |

### 3.6 Reply

Inbound reply records, fully AI-analysed.

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `lead_id` | UUID FK | Replying lead |
| `message_id` | UUID FK? | The outbound message being replied to |
| `campaign_id` | UUID FK? | Campaign context |
| `tenant_id` | UUID FK | Owning tenant |
| `body` | Text | Raw reply text |
| `intent` | String | AI-classified intent (see §14) |
| `sentiment` | String | `positive / neutral / negative` |
| `priority` | String | `high / medium / low` |
| `ai_analysis` | JSONB | `{key_points, suggested_action, objections, questions, meeting_requested, reply_handler_template}` |
| `suggested_response` | Text | AI-drafted reply for the BDR to review and send |
| `is_read` | Bool | Whether BDR has seen this reply in the UI |

### 3.7 SenderAccount

Represents an outbound email identity with warm-up and health tracking.

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `tenant_id` | UUID FK | Owning tenant |
| `email` | String | Sender email address |
| `display_name` | String | From name displayed in inbox |
| `provider` | String | `sendgrid / smtp / gmail` |
| `daily_limit` | Int | Maximum emails per day |
| `sent_today` | Int | Emails sent today (reset nightly) |
| `warmup_stage` | Int | Warm-up progression level |
| `health_score` | Float | Deliverability health 0–100 |

### 3.8 SuppressionList

Global do-not-contact list enforced before every send.

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `tenant_id` | UUID FK | Tenant scope |
| `email` | String | Suppressed address |
| `reason` | String | `unsubscribed / bounced / complained` |
| `source` | String? | Which campaign/message triggered the suppression |

---

## 4. Campaign Lifecycle

### Status Transitions

```
         ┌─────────┐
         │  draft  │
         └────┬────┘
              │ launch / activate
              ▼
         ┌─────────┐ ◄──────────── pause
         │ active  │ ──────────── paused ──► completed
         └────┬────┘                            │
              │ all leads done                  │
              ▼                                 │
        ┌──────────┐ ◄───────────────────────── ┘
        │completed │
        └────┬─────┘
             │ archive
             ▼
        ┌──────────┐
        │ archived │
        └──────────┘
```

**Valid transitions enforced by `CampaignService`:**

| From | To | Notes |
|---|---|---|
| `draft` | `active` | Sets `launched_at` on first activation only |
| `active` | `paused` | Stops follow-up processing for this campaign |
| `active` | `completed` | Marks campaign done |
| `paused` | `active` | Resumes — existing FollowUps continue |
| `paused` | `completed` | — |
| `completed` | `archived` | Final state |

Any other transition raises a 400 Bad Request. The `launched_at` timestamp is write-once: re-activating a paused campaign does not overwrite it.

### Lead Status Transitions

Each `CampaignLead` progresses independently:

```
pending → active → completed
              └──► replied
              └──► bounced
              └──► unsubscribed
              └──► paused
```

---

## 5. Sequence Configuration

The `Campaign.sequence` field stores a JSONB array of step objects. There is no hard schema — the fields are consumed by `process_campaign_lead`. A typical 4-step cold outreach sequence:

```json
[
  {
    "step": 0,
    "delay_days": 0,
    "type": "email",
    "name": "Initial Outreach"
  },
  {
    "step": 1,
    "delay_days": 4,
    "type": "email",
    "condition": "no_reply",
    "name": "Value Add Follow-Up"
  },
  {
    "step": 2,
    "delay_days": 9,
    "type": "email",
    "condition": "no_reply",
    "name": "Bump"
  },
  {
    "step": 3,
    "delay_days": 20,
    "type": "email",
    "condition": "no_reply",
    "name": "Break-Up"
  }
]
```

**Key fields:**
- `delay_days`: Number of days to wait after the previous step fires
- `condition: "no_reply"`: Skip this step and mark the lead completed if the lead has already replied
- `step`: Zero-based index matching `CampaignLead.current_step`

**Timing unit override (development / testing):**  
The environment variable `STEP_DELAY_UNIT` controls the unit for `delay_days`:
- `days` (default, production)
- `minutes` — useful for rapid end-to-end testing
- `seconds` — useful for unit tests
- `hours` — intermediate testing

This allows a 4-step sequence to complete in minutes instead of a month during development.

---

## 6. Campaign Launch Flow

When a campaign is activated via the API (`PATCH /campaigns/{id}/status`), `CampaignService._transition()` is called, which:

1. Validates the `draft → active` transition
2. Sets `campaign.launched_at = now()` (if not already set)
3. Sets `campaign.status = "active"`
4. Commits the change
5. Immediately dispatches: `execute_campaign.delay(campaign_id)`

**`execute_campaign` Celery task:**
1. Loads the Campaign record
2. Queries all `CampaignLead` where `campaign_id = X` AND `status = "pending"`
3. For each pending lead, dispatches: `process_campaign_lead.delay(campaign_lead.id)`

All initial emails for all pending leads are thus dispatched concurrently into the Celery queue within seconds of launch.

---

## 7. Per-Lead Email Generation

`process_campaign_lead(campaign_lead_id)` is the core per-lead state machine. It runs both on initial launch (Step 0) and for every subsequent follow-up step.

### Step-by-Step Execution

```
1.  Load CampaignLead + Campaign
2.  Guard: campaign.status != "active" → abort
3.  Guard: current_step >= len(sequence) → mark lead "completed", return
4.  Load step_config = sequence[current_step]
5.  Guard: step_config.condition == "no_reply" AND reply exists → mark "completed", return
6.  Load Lead + Contact + Company data
7.  Load AI insights from enrichment pipeline
8.  Load research snippets (web search results)
9.  Load enrichment_data (enriched profile fields)
10. Build sender_info:
      - Base: from Settings (SENDGRID_FROM_EMAIL, SENDER_DISPLAY_NAME, SENDER_FIRST_NAME)
      - Override: from campaign.sender_account if set
11. [Test mode] Resolve to_email override (see §8)
12. Look up previous_email_subject from last outbound Message for this lead/campaign
13. Look up latest Reply.intent (reply_intent) for this lead/campaign
14. Call PersonalizationAgent.run(...) → EmailOutput
      - subject, body_html, body_text, template_used, personalization_hooks, rationale
15. Create Message record:
      - status = "draft"
      - ai_generated = True
      - message_id = to_email  ← temporary recipient storage
      - personalization_hooks includes "template: TX"
16. Advance: cl.current_step += 1
17. Set: cl.status = "active"
18. If next step exists:
      Create FollowUp(scheduled_at = now + delay_days * unit)
19. Commit all changes
20. Dispatch: send_email.delay(message.id)
```

### Context Assembly for PersonalizationAgent

The agent receives a rich context object:

```python
{
  "lead": {
    "name": "Amanda Chen",
    "title": "Director of Events",
    "company": "TechConf Global",
    "domain": "techconfglobal.com",
    "tier": "hot",
    "enrichment_score": 87
  },
  "company": {
    "name": "TechConf Global",
    "industry": "Event Management",
    "size": "51-200",
    "cvent_user": True
  },
  "enrichment": {
    "upcoming_events": ["TechSummit 2025", "DevConnect Europe"],
    "cvent_modules": ["Registration", "Attendee Hub"],
    "pain_points": ["complex registration logic", "multi-track sessions"],
    "last_event_date": "2025-06-15"
  },
  "research": [
    "TechConf Global announced TechSummit 2025 registration opening...",
    "Company expanded to EMEA market with DevConnect Europe..."
  ],
  "insights": [
    {"type": "event_trigger", "detail": "TechSummit 2025 is 58 days away"},
    {"type": "cvent_usage", "detail": "Using Registration + Attendee Hub"}
  ],
  "sender_info": {
    "email": "cto@launchhouse.events",
    "display_name": "LaunchHouse Events",
    "first_name": "Snehdeep",
    "company_site_url": "https://launchhouse.events/"
  },
  "previous_email_subject": null,
  "reply_intent": null
}
```

---

## 8. Test Mode

Test mode allows a campaign to be fully exercised without sending emails to real prospect inboxes.

### Outbound: Email Override

When a tenant has test mode enabled (`tenant.settings.test_mode = true`):

1. `process_campaign_lead` builds a list of `enabled_test_emails` from tenant settings
2. The lead index within the campaign is used for round-robin assignment:  
   `test_email = enabled_test_emails[lead_index % len(enabled_test_emails)]`
3. The resolved test email is stored in `CampaignLead.personalization_data`:  
   `{"test_email_override": "tester@company.com"}`
4. The `message.message_id` field is set to the test email address instead of the lead's real email

This means all outbound test emails go to known internal addresses, but each message retains the full personalisation context of the real lead.

### Inbound: Reply Routing

When `check_replies()` processes incoming mail:

1. It builds `test_email_set` — all email addresses across all test-mode tenants
2. For a reply arriving from `from_email` in `test_email_set`:
   - Does NOT use the normal `email_to_lead` lookup (which would fail since the lead's real email doesn't match)
   - Instead: looks up the outbound Message by subject matching → finds the `lead_id`
   - Verifies `CampaignLead.personalization_data.test_email_override == from_email` before associating the reply

This closes the loop: test replies are correctly attributed to the real leads they represent.

---

## 9. Email Template System (T1–T17)

The `PersonalizationAgent` uses a playbook of 17 templates. These are fixed in the system prompt — the LLM's job is to select the right template and fill every token with real, specific context (never leave a placeholder unfilled).

### Template Overview

| ID | Template Name | Primary Use Case | Sequence Position |
|---|---|---|---|
| **T1** | Initial Outreach | Default first touch | Step 1 (Day 0) |
| **T2** | Value Add | Second touch, builds on T1 | Step 2 (Day 4) |
| **T3** | Bump | Ultra-short "worth a reply?" | Step 3 (Day 9) |
| **T4** | Break-Up | Final touch, leads to nurture | Step 4 (Day 20) |
| **T5** | Event Trigger | Verified event found, 120+ days out | Any date |
| **T6** | Fit-Based | No specific event, activity inferable | When event unknown |
| **T7** | Rush (0–30 days) | Verified event <30 days away | Urgent window |
| **T8** | Build Scoping (31–120 days) | **Primary revenue template** — 31–120 day window | Sweet spot |
| **T9** | News Trigger | News ≤45 days old tied to events | Any, with news |
| **T10** | Positive Interest Reply | Lead replied: interested / meeting_request | Reply follow-up |
| **T11** | Send More Info | Lead replied: question / send more info | Reply follow-up |
| **T12** | Not Now Reply | Lead replied: not_now / timing objection | Reply follow-up |
| **T13** | Already Have Support | Lead replied: objection (has agency) | Reply follow-up |
| **T14** | Wrong Contact / Referral | Lead replied: wrong_contact | Reply follow-up |
| **T15** | Voicemail Follow-Up | After leaving a voicemail (within 30 min) | Voicemail follow-up |
| **T16** | Meeting Confirmation | After meeting is booked | Post-booking |
| **T17** | Post-Call Recap | Within 2 hrs of call ending | Post-call |

---

### Template Definitions

**T1 — Initial Outreach**

The default Day 0 cold email. Used when no stronger signal (event timing, news, reply) is present.

```
Subject options:
  - "Cvent support for {{company_name}}"
  - "{{company_name}} + LaunchHouse"
  - "{{event_name}} build"

Body (SHORT — Director/VP):
Hi {{first_name}},

Saw {{company_name}} runs {{event_name}} on Cvent — we handle implementation
for teams that need overflow capacity on registration logic, Attendee Hub builds,
or custom API work.

Worth 15 min?

{{sender_first_name}}
{{company_site_url}}

Body (FULL — Coordinator/Specialist):
Hi {{first_name}},

Noticed {{company_name}} is running {{event_name}} on Cvent. We work with event
teams as an on-demand implementation partner — registration logic, Attendee Hub
builds, API integrations — when the internal team needs extra hands.

Would it be useful to put 15 minutes on the calendar to see if there's a fit?

{{sender_first_name}}
{{company_site_url}}
```

---

**T2 — Value Add**

Follows T1 at Day 4. References the prior email and adds a specific value proof point.

```
Subject options:
  - "Re: Cvent support for {{company_name}}"
  - "One more thing on {{event_name}}"

Body:
Hi {{first_name}},

Following up on my note last week. We recently helped {{similar_company_type}}
cut their Cvent registration setup from 3 weeks to 4 days for a comparable event.

If {{event_name}} has any complex logic — multi-track, tiered pricing, group reg —
that's exactly where we save teams the most time.

Open to a quick call?

{{sender_first_name}}
```

---

**T3 — Bump**

Day 9 ultra-short follow-up — purely checking if the previous emails landed.

```
Subject:
  - "Re: Cvent support for {{company_name}}"

Body:
Hi {{first_name}},

Just bumping this up — worth a quick reply?

{{sender_first_name}}
```

---

**T4 — Break-Up**

Day 20 final touch. Sets a graceful exit that opens the door to future contact.

```
Subject:
  - "Closing the loop"
  - "Last note on {{event_name}}"

Body:
Hi {{first_name}},

I'll stop following up after this — clearly the timing isn't right.

If {{event_name}} build or any future event brings Cvent complexity, we're easy
to reach at {{company_site_url}}.

{{sender_first_name}}
```

---

**T5 — Event Trigger (120+ days)**

Used when a verified event is found but is more than 120 days away. Strategic, low-pressure.

```
Subject options:
  - "{{event_name}} on Cvent"
  - "Planning phase for {{event_name}}"

Body (SHORT):
Hi {{first_name}},

Saw {{event_name}} is coming up — looks like you're still in early planning.
We do Cvent builds for teams that want the infrastructure locked before the rush.

Worth a conversation while the calendar is open?

{{sender_first_name}}

Body (FULL):
Hi {{first_name}},

Noticed {{event_name}} is on the horizon. We work with event teams during the
planning phase to handle Cvent registration architecture, Attendee Hub setup,
and any API work before things get hectic.

Happy to share what a scoping conversation looks like — 15 min?

{{sender_first_name}}
{{company_site_url}}
```

---

**T6 — Fit-Based (no event found)**

Used when no specific event can be confirmed but the company's profile clearly indicates active event management.

```
Subject options:
  - "Cvent implementation support"
  - "{{company_name}} event operations"

Body (SHORT):
Hi {{first_name}},

We work with {{industry_type}} teams as an on-demand Cvent implementation partner —
overflow capacity for registration builds, Attendee Hub, or integrations.

Worth 15 min to see if there's a fit?

{{sender_first_name}}

Body (FULL):
Hi {{first_name}},

Based on {{company_name}}'s event profile, it looks like your team manages a
significant programme on Cvent. We work with event operations teams as a specialist
implementation partner — taking on the technical Cvent work when internal capacity
is stretched.

Happy to run through what that looks like. 15 minutes?

{{sender_first_name}}
{{company_site_url}}
```

---

**T7 — Rush / Urgent (event 0–30 days out)**

Highest-urgency template. Used when a verified event is within 30 days. Frames LaunchHouse as an emergency resource.

```
Subject options:
  - "{{event_name}} in {{days_until}} days"
  - "Last-minute Cvent help for {{event_name}}"
  - "Rush support for {{event_name}}"

Body (SHORT):
Hi {{first_name}},

{{event_name}} is {{days_until}} days out. If anything in the Cvent build is
still unresolved — registration logic, last-minute Attendee Hub updates,
API issues — we take on rush work.

Can jump on a call today or tomorrow.

{{sender_first_name}}

Body (FULL):
Hi {{first_name}},

Saw {{event_name}} is coming up in {{days_until}} days. If your team is carrying
any unresolved Cvent items into the final stretch — registration complexity,
Attendee Hub setup, or last-minute integration issues — we specialise in
exactly that kind of rush turnaround.

We work on fixed-fee briefs, so no open-ended commitment. Happy to do a same-day
assessment call if useful.

{{sender_first_name}}
{{company_site_url}}
```

---

**T8 — Build Scoping (31–120 days out) — Highest-Converting Template**

The primary revenue template. Used when an event is in the 31–120 day "sweet spot" — close enough that budget is approved and scope is being set, but not so close that it's a crisis.

```
Subject options:
  - "Scoping the {{event_name}} build"
  - "{{event_name}} Cvent build — fixed fee"
  - "Implementation support for {{event_name}}"

Body (SHORT):
Hi {{first_name}},

{{event_name}} is {{days_until}} days out — usually when teams are locking
in Cvent scope. We handle implementation on fixed-fee briefs: registration
architecture, Attendee Hub, integrations.

Worth 20 min to scope it?

{{sender_first_name}}

Body (FULL):
Hi {{first_name}},

Noticed {{event_name}} is {{days_until}} days away — that's usually when event
teams are deep in Cvent build planning. We work as an implementation partner
on fixed-fee scopes: registration logic, multi-track setup, Attendee Hub builds,
and API integrations.

No ongoing retainer — just a scoped brief for the event. Happy to do a 20-minute
scoping call to see what, if anything, makes sense.

{{sender_first_name}}
{{company_site_url}}
```

---

**T9 — News Trigger**

Used when recent news (≤45 days) is found that is directly relevant to an event or Cvent usage. Combines the news hook with the event proximity signal.

```
Subject options:
  - "Saw the news on {{news_topic}}"
  - "{{company_name}} + {{event_name}}"

Body:
Hi {{first_name}},

Saw {{news_detail}} — that kind of shift usually creates some Cvent complexity,
especially with {{relevant_module}} setup.

We work with teams in that position on fixed-fee implementation briefs.
Worth 15 min?

{{sender_first_name}}
{{company_site_url}}
```

---

**T10 — Positive Interest Reply**

Triggered when `reply_intent = "interested"` or `"meeting_request"`. Moves quickly to booking.

```
Subject: Re: [original subject]

Body:
Hi {{first_name}},

Great to hear — let's find time. Here's my calendar: {{sender_calendar_link}}

{{sender_first_name}}
```

---

**T11 — Send More Info**

Triggered when `reply_intent = "question"` or lead asks for more information.

```
Subject: Re: [original subject]

Body:
Hi {{first_name}},

Happy to share more. In short: we work on fixed-fee Cvent implementation briefs —
registration architecture, Attendee Hub, API integrations. No retainer, no
long-term contract.

A few questions would help me send something relevant — what's the event,
and which parts of the Cvent build are you still working through?

{{sender_first_name}}
{{company_site_url}}
```

---

**T12 — Not Now / Timing Objection**

Triggered when `reply_intent = "not_now"`. Graceful exit with a future door.

```
Subject: Re: [original subject]

Body:
Hi {{first_name}},

Totally understand — timing matters a lot with this. I'll circle back when
{{event_name}} is closer to the planning phase.

If anything comes up in the interim, easy to reach at {{company_site_url}}.

{{sender_first_name}}
```

---

**T13 — Already Have Support**

Triggered when `reply_intent = "objection"` and lead has an existing agency relationship.

```
Subject: Re: [original subject]

Body:
Hi {{first_name}},

Good to know — sounds like you're covered. If that ever changes, or if there's
overflow from a particularly complex build, that's exactly where we step in.

{{sender_first_name}}
```

---

**T14 — Wrong Contact / Referral**

Triggered when `reply_intent = "wrong_contact"`. Asks for a warm redirect.

```
Subject: Re: [original subject]

Body:
Hi {{first_name}},

Appreciate you letting me know — who would be the right person to speak with?
Happy to reach out directly and keep it brief.

{{sender_first_name}}
```

---

**T15 — Voicemail Follow-Up** *(within 30 min of voicemail)*

```
Subject: "Just left you a voicemail"

Body:
Hi {{first_name}},

Left a quick voicemail — calling about Cvent implementation support for
{{event_name}}. Easy to reach at this email or {{sender_calendar_link}}.

{{sender_first_name}}
```

---

**T16 — Meeting Confirmation** *(after booking)*

```
Subject: "Confirmed: {{meeting_time}}"

Body:
Hi {{first_name}},

Looking forward to speaking {{meeting_time}}. I'll send a calendar invite
to {{contact_email}}.

A brief agenda: a quick look at your Cvent setup for {{event_name}} and
where implementation support might fill gaps. Should be 20 minutes.

{{sender_first_name}}
```

---

**T17 — Post-Call Recap** *(within 2 hrs of call)*

```
Subject: "Recap from our call"

Body:
Hi {{first_name}},

Good speaking today. To summarise what we discussed:

{{call_summary_bullets}}

Next step: {{agreed_next_step}}

If anything changes or you have questions before then, just reply here.

{{sender_first_name}}
```

---

## 10. Template Selection Hierarchy

The agent enforces a strict priority decision tree. **Higher-priority signals always override lower ones.** No exceptions.

```
INPUT: lead context, enrichment data, current reply intent
       ↓
STEP 1: Is there a reply?
        ├── intent = "interested" | "meeting_request"  →  T10
        ├── intent = "question"                        →  T11
        ├── intent = "not_now"                         →  T12
        ├── intent = "objection" (has agency)          →  T13
        └── intent = "wrong_contact"                   →  T14
        
STEP 2: Is there a verified upcoming event?
        ├── days_until ≤ 30                            →  T7 (Rush)
        ├── 31 ≤ days_until ≤ 120                      →  T8 (Build Scoping) ★
        └── days_until > 120                           →  T5 (Event Trigger)

STEP 3: Is there relevant news ≤ 45 days old?
        └── news AND events inferable                  →  T9 (News Trigger)

STEP 4: No event found, activity inferable?
        └── Profile clearly shows event ops            →  T6 (Fit-Based)

STEP 5: Default sequence position
        ├── sequence_step = 0 (first touch)            →  T1 (Initial Outreach)
        ├── sequence_step = 1                           →  T2 (Value Add)
        ├── sequence_step = 2                           →  T3 (Bump)
        └── sequence_step = 3                           →  T4 (Break-Up)
```

**T8 is the highest-converting template in the playbook** — the 31–120 day window is when event budgets are live and scope decisions are being made. The system is explicitly designed to maximise the probability of leads hitting this window.

---

## 11. Seniority-Based Tone Rules

Every template has two versions. The correct version is selected based on the lead's job title:

### Director / VP / Head of Events (Senior)
- **Use the SHORT version** of every template
- Strategic framing: "overflow capacity", "pressure valve", "scale without headcount"
- Max optionality CTAs: "worth 15 min?" rather than direct requests
- Never mention specific product names or modules in opening line
- Assume they understand Cvent — no explanation needed

### Specialist / Coordinator / Manager (Operational)
- **Use the FULL version** of every template
- Tactical framing: "registration logic", "Attendee Hub cleanup", "rush turnarounds"
- Insider Cvent language is welcome and increases credibility
- CTAs can be more direct: "15 minutes this week?"
- Can go deeper on feature-level specifics

---

### Universal Rules (All Templates, All Recipients)

| Rule | Detail |
|---|---|
| No wellness openers | Never "Hope you're well", "Hope this finds you" etc. |
| No exclamation marks | Zero. Not one. Even for positive replies (T10). |
| No stack questions | Never lead with "What tool do you use for X?" |
| One CTA maximum | Never present two options or two asks in a cold email |
| Under 130 words | All cold outreach (T1–T9) must be under 130 words |
| No funding mentions | Never reference funding rounds or dollar amounts |
| No headcount data | Never mention employee count figures from scraped data |
| No layoff references | Never reference redundancies, restructuring, downsizing |
| No personal social | Never reference personal LinkedIn, Twitter etc. |
| No past employers | Never reference previous companies of the contact |
| No LinkedIn anniversaries | Never reference work anniversaries |
| All tokens resolved | No raw `{{token}}` may appear in the final output |

---

## 12. Email Delivery — SendGrid Integration

### Delivery Flow

```
send_email(message_id)
    │
    ├── Load Message — skip if status not in (draft, queued)
    │
    ├── Resolve to_email:
    │     1. message.message_id field (stashed during creation)
    │     2. Lead → Contact.email (fallback)
    │
    ├── Resolve from_email:
    │     1. SENDGRID_FROM_EMAIL env var
    │     2. campaign.sender_account.email
    │
    ├── Build SendGrid Mail object:
    │     - from: from_email (display_name from settings or sender_account)
    │     - to: to_email
    │     - subject: message.subject
    │     - html: message.body_html
    │     - plain: message.body_text
    │     - custom header: X-Lead-Id: {lead_id}
    │
    ├── Send via SendGrid Python SDK
    │
    ├── ON SUCCESS:
    │     - message.status = "sent"
    │     - message.message_id = sendgrid_response.x_message_id
    │     - Create EmailEvent(event_type="sent")
    │     - sender.sent_today += 1
    │     - campaign.sent_count += 1
    │     - Publish Redis event: "email.sent" {message_id, lead_id, campaign_id}
    │
    └── ON FAILURE:
          - message.status = "failed"
          - message.error_message = error detail
```

### Dev / No API Key Mode

If `SENDGRID_API_KEY` is not configured, `send_email` logs a warning and marks the message as `sent` with a mock ID (`mock-{uuid}`). This allows full local development without a SendGrid account.

### Sender Resolution

| Priority | Source |
|---|---|
| 1 | `SENDGRID_FROM_EMAIL` environment variable |
| 2 | `campaign.sender_account.email` |

Display name (`From` header):
1. `SENDER_DISPLAY_NAME` environment variable
2. `campaign.sender_account.display_name`

Production sender: `cto@launchhouse.events` / display `LaunchHouse Events` / first name `Snehdeep`

### Daily Limits

Each `SenderAccount` tracks `sent_today` (reset nightly by `reset_daily_counts` beat task) against `daily_limit`. **Note:** The current implementation increments `sent_today` but does not actively block sends when the limit is reached — this is left for a future enforcement pass.

---

## 13. Reply Ingestion — IMAP Polling

`check_replies()` is a Celery beat task that polls the Gmail inbox every 15 minutes.

### Prerequisites
- `GMAIL_IMAP_USER`: Full Gmail address (e.g. `cto@launchhouse.events`)
- `GMAIL_APP_PASSWORD`: Gmail App Password (not the account password)

### Processing Flow

```
check_replies()
    │
    ├── Connect: imap.gmail.com:993 (SSL)
    ├── Login with GMAIL_IMAP_USER + GMAIL_APP_PASSWORD
    ├── SELECT INBOX
    ├── SEARCH UNSEEN messages
    │
    ├── Build lookup tables:
    │     email_to_lead:    contact.email → Lead (all tenants)
    │     test_email_set:   all test emails across test-mode tenants
    │     subject_to_message: subject → outbound Message (sent status)
    │
    ├── For each UNSEEN message:
    │     │
    │     ├── Extract from_email, subject, body_text
    │     │
    │     ├── Test mode path (from_email in test_email_set):
    │     │     - Match subject → outbound Message
    │     │     - Verify CampaignLead.personalization_data.test_email_override == from_email
    │     │     - Resolve lead from message.lead_id
    │     │
    │     ├── Normal path:
    │     │     - Direct email_to_lead lookup
    │     │
    │     ├── Subject match (strip "Re:", "Fwd:" prefix, fuzzy 30-char prefix match)
    │     │
    │     ├── Dedup check: skip if Reply already exists for (lead_id, message_id)
    │     │
    │     ├── Run ReplyAnalysisAgent.run(reply_text, original_message_body)
    │     │     → intent, sentiment, priority, ai_analysis, suggested_response
    │     │
    │     ├── Create Reply record (all fields populated)
    │     │
    │     └── campaign.reply_count += 1
    │
    └── Mark messages as READ after processing (matched messages only)
         Unmatched messages remain UNSEEN for retry on next cycle
```

### Deduplication

The system prevents duplicate Reply records by checking the combination of `(lead_id, message_id)` before creating a new record. Unmatched messages (no lead found, no subject match) are intentionally left unread so they will be retried on the next poll cycle.

---

## 14. AI Reply Analysis

`ReplyAnalysisAgent` uses Claude Haiku at `temperature=0.2` (precision over creativity) to classify every incoming reply.

### Intent Categories

| Intent | Priority | Template Trigger | Meaning |
|---|---|---|---|
| `interested` | HIGH | T10 | Lead wants to learn more or proceed |
| `meeting_request` | HIGH | T10 | Lead explicitly asks to book a call |
| `question` | HIGH | T11 | Lead asks a specific question |
| `objection` | MEDIUM | T13 | Lead has concerns or pushback |
| `not_now` | MEDIUM | T12 | Lead is interested but not ready |
| `unsubscribe` | HIGH | (suppress) | Lead requests removal |
| `out_of_office` | LOW | none | Automated OOO reply |
| `bounce` | LOW | none | Delivery failure notification |
| `irrelevant` | LOW | none | Spam, misdirected, or unrelated reply |

### Structured Output

The agent returns a `ReplyAnalysis` Pydantic model:

```python
class ReplyAnalysis(BaseModel):
    intent: str                    # one of 9 categories above
    sentiment: str                 # "positive" | "neutral" | "negative"
    priority: str                  # "high" | "medium" | "low"
    key_points: list[str]          # bullet points of reply content
    suggested_action: str          # what the BDR should do next
    objections: list[str]          # any explicit objections raised
    questions: list[str]           # specific questions asked
    meeting_requested: bool        # explicit meeting ask
    reply_handler_template: str    # T10–T14 or "" if none applies
    suggested_response: str        # draft reply text for the BDR to review
```

### Suggested Response Generation

The agent generates a complete draft reply (`suggested_response`) that the BDR can review and send (possibly with minor edits). This draft:
- Always uses the appropriate template (T10–T14) as the base
- Is personalised to the specific reply content (references their objection, question, or interest)
- Follows all universal tone rules (no exclamation marks, under 130 words for simple replies)
- Is stored in `Reply.suggested_response` and displayed in the UI for the BDR

---

## 15. Follow-Up Scheduling

The drip sequence is maintained by `FollowUp` records and the `process_follow_ups` beat task.

### FollowUp Creation

When `process_campaign_lead` completes a step and there is a next step:

```python
next_step = sequence[current_step]  # current_step was already incremented
delay_days = next_step.get("delay_days", 1)

unit = os.getenv("STEP_DELAY_UNIT", "days")
if unit == "minutes":
    delta = timedelta(minutes=delay_days)
elif unit == "seconds":
    delta = timedelta(seconds=delay_days)
elif unit == "hours":
    delta = timedelta(hours=delay_days)
else:
    delta = timedelta(days=delay_days)

FollowUp(
    campaign_lead_id = campaign_lead.id,
    scheduled_at = datetime.utcnow() + delta,
    status = "scheduled"
)
```

### process_follow_ups Beat Task

Runs every 5 minutes. Logic:

```python
# Find all due follow-ups
follow_ups = db.query(FollowUp).where(
    FollowUp.status == "scheduled",
    FollowUp.scheduled_at <= datetime.utcnow()
).limit(100).all()

for fu in follow_ups:
    fu.status = "processing"
    db.commit()
    process_campaign_lead.delay(fu.campaign_lead_id)
```

The status is set to `"processing"` before dispatching to prevent double-processing if the beat fires again before the task completes.

### Sequence Timing Example

For a production 4-step sequence:

```
Day 0:   Step 0 fires → Initial Outreach sent → FollowUp scheduled for Day 4
Day 4:   Step 1 fires → Value Add sent → FollowUp scheduled for Day 9
Day 9:   Step 2 fires → Bump sent → FollowUp scheduled for Day 20
Day 20:  Step 3 fires → Break-Up sent → no next step → lead "completed"
```

Total outreach window per lead: 20 days, 4 touches.

---

## 16. Suppression & Compliance

### SuppressionList

The `SuppressionList` table maintains a global per-tenant block list. Entries are created:

| Reason | Trigger |
|---|---|
| `unsubscribed` | Lead replies with unsubscribe intent (T14 path) or clicks unsubscribe link |
| `bounced` | SendGrid bounce event webhook |
| `complained` | SendGrid spam complaint webhook |

**Future enforcement**: The current implementation records suppressions but the `send_email` task does not yet pre-check the suppression list before sending. This is a planned addition.

### Lead Completion Conditions

A `CampaignLead` is marked `"completed"` (stops receiving further emails) when:
1. `current_step >= len(sequence)` — all sequence steps exhausted
2. Step has `condition = "no_reply"` but lead has already replied
3. Lead is manually marked completed via the API

### 90-Day Suppression Rule

After T4 (Break-Up) fires, the personalization agent's playbook states: **no new sequence should be initiated for this lead within 90 days**. This is enforced at the template level (the agent is instructed not to select a new initial sequence template for leads marked "completed" within 90 days). Future versions will enforce this at the `CampaignService.add_leads()` level.

### Maximum Email Rule

**Never more than 4 emails per sequence** for cold outreach. The T1–T4 framework is the maximum. The personalization agent's system prompt explicitly states this constraint.

---

## 17. Metrics & Tracking

### Per-Campaign Denormalized Counters

Stored directly on the `Campaign` record for fast dashboard queries:

| Field | Incremented by |
|---|---|
| `total_leads` | `campaign_service.add_leads()` |
| `sent_count` | `send_email()` on success |
| `open_count` | SendGrid webhook `opened` event |
| `click_count` | SendGrid webhook `clicked` event |
| `reply_count` | `check_replies()` on successful match |
| `bounce_count` | SendGrid webhook `bounced` event |

### EmailEvent Log

Every state change in an email's lifecycle is recorded as an `EmailEvent`:

| Event Type | Source |
|---|---|
| `sent` | `send_email()` on SendGrid success |
| `delivered` | SendGrid webhook |
| `opened` | SendGrid webhook (pixel tracking) |
| `clicked` | SendGrid webhook (link tracking) |
| `bounced` | SendGrid webhook |
| `complained` | SendGrid webhook (spam report) |
| `unsubscribed` | SendGrid webhook or IMAP reply analysis |

### Reply Metrics

Available directly from the `Reply` table:
- Intent distribution (interested / objection / not_now etc.)
- Sentiment breakdown (positive / neutral / negative)
- Priority queue (high priority replies awaiting BDR response)
- `is_read` flag for unactioned reply count

---

## 18. Business Logic & Positioning

### The Niche: Cvent Implementation for Events

Every element of this system is tuned for a single vertical: B2B outreach to event managers, conference directors, and marketing operations teams who use or need Cvent.

**LaunchHouse Events' positioning**: Not a Cvent reseller or a software company — an implementation firm that provides specialist engineering/configuration capacity on demand.

**Core value proposition**: "Overflow capacity for your Cvent build" — the prospect does not need to hire, train, or manage; they scope a brief, LaunchHouse delivers.

### Why Fixed-Fee Matters

The fixed-fee pitch (prominent in T7 and T8) is a deliberate trust signal for event teams who have been burned by open-ended consulting retainers. It reduces buying friction and accelerates decisions.

### The T8 Window

The 31–120 day window before an event is the highest-value sales window because:
1. Budget has been approved (the event is happening)
2. Scope is being defined (decisions are being made)
3. The team is not yet in crisis mode (they have bandwidth to evaluate)

T8 is the system's primary revenue driver. The entire enrichment pipeline (event date extraction, urgency scoring) is designed to maximise the probability of hitting a lead during their T8 window.

### Target Personas

| Persona | Template Version | Key Pain Points |
|---|---|---|
| VP Events / Conference Director | SHORT | Capacity, quality, timeline risk |
| Head of Event Technology | SHORT | Technical complexity, integration risk |
| Event Manager / Coordinator | FULL | Registration logic, Attendee Hub setup, deadline pressure |
| Marketing Operations Manager | FULL | Cvent integration with marketing stack, data flows |

---

## 19. Example Email — Template T8

**Lead Context:**
- Name: Amanda Chen, Director of Events, TechConf Global
- Event: TechSummit 2025, 58 days away
- Cvent modules: Registration, Attendee Hub
- Pain: Multi-track, tiered pricing, complex registration

**Template Selected**: T8 (Build Scoping — 58 days out)  
**Tone Version**: SHORT (Director title)

---

**Subject**: Scoping the TechSummit 2025 build

---

**Body**:

Hi Amanda,

TechSummit 2025 is 58 days out — usually when teams are locking in Cvent scope. We handle implementation on fixed-fee briefs: registration architecture, Attendee Hub, integrations.

Worth 20 min to scope it?

Snehdeep  
https://launchhouse.events/

---

**Personalization hooks stored** (in `Message.personalization_hooks`):
```json
[
  "event: TechSummit 2025",
  "days_until: 58",
  "template: T8",
  "tier: high-converting",
  "tone: short (Director)"
]
```

**Why T8 won the selection hierarchy:**
- No prior reply (T10–T14 skipped)
- Event found = TechSummit 2025
- days_until = 58 (31–120 window) → T8 selected
- Title = Director → SHORT version applied

---

## 20. Operational Runbook

### Starting the System

```bash
# Full stack (API + Celery + DB + Redis)
docker compose up -d

# Check Celery worker is running
docker compose logs celery-worker --tail=50

# Check beat scheduler is running
docker compose logs celery-beat --tail=50
```

### Testing the Full Pipeline (Development)

1. Set `STEP_DELAY_UNIT=minutes` in `.env`
2. Create a campaign with a 4-step sequence (set `delay_days: 1` for each step)  
   → Each step fires 1 minute after the previous
3. Enable test mode in tenant settings and add test email addresses
4. Launch the campaign via the UI or API
5. Watch `check_replies` pick up replies from the test inbox every 15 minutes

### Monitoring

| What to watch | How |
|---|---|
| Email send failures | `SELECT * FROM messages WHERE status='failed'` |
| Stuck follow-ups | `SELECT * FROM follow_ups WHERE status='scheduled' AND scheduled_at < now() - interval '1 hour'` |
| High-priority replies | `SELECT * FROM replies WHERE priority='high' AND is_read=false` |
| Sender health | `SELECT email, sent_today, daily_limit, health_score FROM sender_accounts` |

### Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `SENDGRID_API_KEY` | Email delivery | Production |
| `SENDGRID_FROM_EMAIL` | Sender address | Production |
| `SENDER_DISPLAY_NAME` | From display name | Production |
| `SENDER_FIRST_NAME` | Signature first name | Production |
| `GMAIL_IMAP_USER` | Reply inbox address | Production |
| `GMAIL_APP_PASSWORD` | Gmail App Password | Production |
| `ANTHROPIC_API_KEY` | Claude LLM access | Required |
| `STEP_DELAY_UNIT` | `days`/`hours`/`minutes`/`seconds` | Dev only |

---

## 21. Current Limitations & Future Direction

### Known Limitations

| Area | Current State | Future State |
|---|---|---|
| Suppression check | Suppression list is written to but not checked before send | Pre-send suppression check in `send_email()` |
| Daily limit enforcement | `sent_today` is tracked but not enforced | Block send when `sent_today >= daily_limit` |
| T15/T16/T17 triggers | Templates defined but no automatic trigger mechanism | LinkedIn voicemail webhook, calendar booking webhook |
| Open/click tracking | EmailEvent schema supports it; webhook handler not implemented | SendGrid webhook endpoint receiving open/click events |
| 90-day suppression | Enforced at template level (prompt instruction only) | Enforce at `add_leads()` — check `completed_at` before adding |
| Multi-tenant sender isolation | All tenants share one sender identity | Per-tenant or per-campaign sender rotation |
| A/B testing | No variant system | Template variant field + statistical significance tracking |
| SendGrid webhooks | `EmailEvent` table ready | `POST /webhooks/sendgrid` endpoint |

### Planned Enhancements

1. **Webhook handler** for SendGrid events → populates open/click/bounce events in real time
2. **Suppression pre-check** before every `send_email()` call
3. **Calendar integration** (Calendly or Cal.com) → auto-trigger T16 on booking, T17 after call
4. **A/B subject line testing** with statistical variant tracking
5. **Sender warm-up automation** — automatic `daily_limit` progression based on health score
6. **Reply auto-send** — optional setting to auto-send `suggested_response` for low-risk intents (T12, OOO)
7. **Campaign cloning** — duplicate a campaign with a new target lead list

---

*Document generated from source code analysis of `backend/app/agents/personalization_agent.py`, `backend/app/tasks/campaign_tasks.py`, `backend/app/tasks/email_tasks.py`, `backend/app/agents/reply_analysis_agent.py`, `backend/app/models/campaign.py`, and `backend/app/services/campaign_service.py`.*
