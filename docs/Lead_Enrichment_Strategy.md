# Lead Enrichment Strategy & Process
## End-to-End Guide — LaunchHouse Events / Sales Outreach Platform

*Last updated: April 25, 2026*

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Architecture Overview](#2-system-architecture-overview)
3. [Data Model](#3-data-model)
4. [Lead Lifecycle & Status Transitions](#4-lead-lifecycle--status-transitions)
5. [Phase 1 — Lead Import & Registration](#5-phase-1--lead-import--registration)
6. [Phase 2 — Web Research Agent](#6-phase-2--web-research-agent)
7. [Phase 3 — Company & Contact Enrichment Agent](#7-phase-3--company--contact-enrichment-agent)
8. [Phase 4 — AI Lead Scoring Engine](#8-phase-4--ai-lead-scoring-engine)
9. [Phase 5 — Personalization & Email Generation](#9-phase-5--personalization--email-generation)
10. [Phase 6 — Campaign Execution & Email Delivery](#10-phase-6--campaign-execution--email-delivery)
11. [Orchestration & Pipeline Control](#11-orchestration--pipeline-control)
12. [AI Infrastructure & Model Configuration](#12-ai-infrastructure--model-configuration)
13. [Business Logic & ICP Assumptions](#13-business-logic--icp-assumptions)
14. [Scoring Reference Card](#14-scoring-reference-card)
15. [Template Reference Card](#15-template-reference-card)
16. [Current Limitations](#16-current-limitations)
17. [Future Enhancements](#17-future-enhancements)

---

## 1. Executive Summary

The Sales Outreach Platform automates end-to-end outbound prospecting for **LaunchHouse Events**, a Cvent development and professional services firm. The platform ingests raw lead lists (CSV/manual), runs a fully automated 3-stage AI enrichment pipeline, scores each lead for fit, and generates hyper-personalized email sequences using templates calibrated to the events industry.

**Core value proposition:** Turn a cold CSV of company names and emails into a ranked, personally researched, and actively-sequenced outbound campaign with zero human effort between import and first email draft.

**Technology foundations:**
- Primary AI: Anthropic Claude (`claude-sonnet-4-6`)
- Orchestration: Celery (distributed task queue) + Redis broker
- Storage: PostgreSQL with multi-tenant row-level isolation
- Email delivery: SendGrid
- Backend: Python / FastAPI (async)
- Frontend: Next.js 14

---

## 2. System Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                   USER / API LAYER                        │
│   Lead Import (CSV/manual)  →  Enrichment Trigger API    │
└────────────────────────┬─────────────────────────────────┘
                         │
                    EnrichmentService
                    (creates jobs, dispatches)
                         │
              ┌──────────▼─────────────┐
              │   Celery Queue         │
              │  ("enrichment" queue)  │
              └──────────┬─────────────┘
                         │
              run_enrichment_pipeline
              ┌───────────────────────┐
              │  Step 1: ResearchAgent │  ← Web synthesis via LLM
              │  Step 2: EnrichmentAgent│  ← Firmographic structuring
              │  Step 3: ScoringAgent  │  ← 10-signal weighted score
              └──────────┬────────────┘
                         │
              Lead marked "enriched" + "scored"
                         │
              ┌──────────▼─────────────┐
              │  Campaign Assignment    │
              │  (manual or auto-route) │
              └──────────┬─────────────┘
                         │
              process_campaign_lead
              ┌───────────────────────┐
              │  PersonalizationAgent  │  ← T1–T17 template selection
              │  Message draft created │
              │  send_email dispatched │
              └──────────┬────────────┘
                         │
              ┌──────────▼─────────────┐
              │   SendGrid API          │
              │   Email delivered       │
              └─────────────────────────┘
```

---

## 3. Data Model

### Core Tables

| Table | Purpose | Key Fields |
|-------|---------|-----------|
| `companies` | Firmographic data per company | `name`, `domain`, `industry`, `employee_count`, `revenue_range`, `location`, `description`, `technologies` (JSONB) |
| `contacts` | Individual people | `email`, `first_name`, `last_name`, `title`, `department`, `phone`, `linkedin_url`, `location`, `timezone` |
| `leads` | The join between contact + company with pipeline state | `status`, `enrichment_status`, `source`, `tags`, `enriched_at` |
| `lead_scores` | AI-generated score per lead | `overall_score` (float), `tier` (hot/warm/cold), `signal_scores` (JSONB), `explanation`, `model_used` |
| `enrichment_jobs` | Audit trail per enrichment step | `job_type`, `status`, `provider`, `input_data`, `output_data`, `error`, `duration_ms`, `tokens_used`, `cost_usd` |
| `research_data` | Raw research output | `source`, `url`, `title`, `content`, `relevance_score`, `metadata` (JSONB) |
| `enrichment_data` | Structured enrichment output | `data_type`, `provider`, `data` (JSONB), `confidence`, `version` |
| `ai_insights` | Human-readable AI summaries | `insight_type`, `content`, `confidence`, `model_used`, `tokens_used` |
| `lead_activities` | Audit log of all events | `activity_type`, `title`, `description`, `metadata` (JSONB) |
| `import_batches` | CSV upload tracking | `file_name`, `status`, `total_rows`, `processed_rows`, `success_rows`, `error_rows` |

### Campaign Tables

| Table | Purpose |
|-------|---------|
| `campaigns` | Campaign definition with sequence steps, sender, status |
| `campaign_leads` | Lead × Campaign assignment with `current_step`, `status` |
| `messages` | Every email draft/sent — `subject`, `body_html`, `body_text`, `status`, `ai_generated`, `personalization_hooks` |
| `follow_ups` | Scheduled next-step email queue |
| `replies` | Inbound reply tracking with `intent` classification |
| `email_events` | Open/click/bounce/sent tracking from SendGrid webhooks |

### All Entities Are Multi-Tenant
Every table includes a `tenant_id` column linked to the `tenants` table. Row-level isolation is enforced at the middleware and query layer — tenants cannot see each other's data.

---

## 4. Lead Lifecycle & Status Transitions

### `lead.status` Flow

```
new
 │
 ├─ (enrichment triggered) ──→ enriching
 │                                  │
 │                         (pipeline completes) ──→ scored
 │                                  │
 │                         (campaign assigned) ──→ campaign_active
 │                                  │
 │                         (reply received) ──→ replied
 │                                  │
 │                         (deal closed) ──→ converted
 │                         (disqualified) ──→ disqualified
 │
 └─ (manually set) ──→ any state above
```

### `lead.enrichment_status` Flow

```
pending
 │
 ├─ (pipeline started) ──→ enriching
 │
 ├─ (all steps complete) ──→ enriched
 │
 └─ (pipeline failed) ──→ failed
```

### `enrichment_job.status` per step

```
pending → running → completed
                 └→ failed (records error message)
```

---

## 5. Phase 1 — Lead Import & Registration

### How Leads Enter the System

Leads are imported in two ways:
1. **CSV Upload** — via the `/api/leads/import` endpoint. Columns are mapped to `Company` and `Contact` fields. Each row creates a `Company` + `Contact` + `Lead` record. Batch tracked in `import_batches`.
2. **Manual Entry** — via the UI form or REST API. Single point-of-entry creating the same three records.

### Initial Data Required
- Company name (required)
- Contact email (required)
- First/last name (optional but strongly recommended)
- Job title (optional)
- Company domain (optional — improves research quality significantly)

### Post-Import State
- `lead.status = "new"`
- `lead.enrichment_status = "pending"`
- Company, Contact records created with whatever raw data was available
- No enrichment, scoring, or AI processing has occurred yet

### Triggering Enrichment
Enrichment is triggered explicitly — either:
- Manually: user selects leads in the UI and clicks "Enrich"
- Via API: `POST /api/enrichment/enrich` with `lead_ids[]` and `enrichment_types[]`

Default enrichment types requested: `["web_research", "company", "scoring"]`

---

## 6. Phase 2 — Web Research Agent

**Class:** `ResearchAgent` (`agents/research_agent.py`)  
**LLM Temperature:** 0.3 (slight creativity for synthesis)  
**Model:** Claude `claude-sonnet-4-6` via `BaseAgent.get_llm()`

### Purpose
Gather publicly available intelligence about the company and contact: news, events, technology stack, funding, and buying signals — all without any human effort.

### Search Strategy — 5 Queries Built per Lead

| Query # | Pattern | Goal |
|---------|---------|------|
| 1 | `{company_name} company news recent` | Latest company updates, announcements, changes |
| 2 | `{company_name} events Cvent` | Cvent usage evidence, event calendar, hosted events |
| 3 | `{company_name} technology stack` | Technology platforms in use |
| 4 | `site:{domain}` | Homepage / about page / events page scan |
| 5 | `{contact_name} {company_name} LinkedIn` | Contact seniority, career path, responsibilities |

### Data Sources (Current Status)

| Source | Status | Purpose |
|--------|--------|---------|
| **Tavily** | ✅ Live | Primary web search — AI-optimised snippets, used for all 5 per-lead queries |
| **Firecrawl (search)** | ✅ Live (fallback) | Full-page search fallback if Tavily returns no results |
| **Firecrawl (scrape)** | ✅ Live | Homepage scrape — always runs if domain is known, returns full markdown (capped 3 000 chars) |
| **Claude LLM** | ✅ Live | Synthesis and structuring of all search findings into `ResearchOutput` |

**Provider priority:** Tavily is tried first for every query. If it returns results, Firecrawl search is skipped. Firecrawl scrape runs independently in parallel for the homepage regardless of search results.

**Python packages required:** `tavily-python>=0.3.0`, `firecrawl-py>=0.0.16` (both in `requirements.txt` and installed in all Docker containers).

### Research Output Schema (`ResearchOutput`)

```json
{
  "company_summary": "2-3 sentence overview of the company",
  "recent_news": [
    { "title": "...", "url": "...", "date": "...", "summary": "..." }
  ],
  "key_people": [
    { "name": "...", "title": "...", "linkedin_url": "..." }
  ],
  "technology_stack": ["Cvent", "Salesforce", "Marketo"],
  "funding_info": {
    "stage": "Series B",
    "amount": "$50M",
    "investors": ["Sequoia", "..."]
  },
  "industry_signals": [
    "company posted 3 event manager roles in past 30 days"
  ],
  "events_attended": [
    {
      "event": "Dreamforce 2024",
      "year": 2024,
      "month": 9,
      "date_label": "September 2024",
      "type": "past",
      "role": "sponsor",
      "confirmed": true,
      "url": "https://...",
      "description": "Gold sponsor, hosted networking dinner"
    }
  ],
  "competitor_info": ["Competitor A uses similar platform"],
  "relevance_score": 0.82
}
```

### Events Attended — Classification

The `events_attended` array is the most critical research output for personalization. Each event is classified across two dimensions:

**`type` values:**
- `past` — event has already occurred
- `upcoming` — event is in the future
- `recurring` — annual/regular event

**`role` values:**
- `attendee` — company sent staff to the event
- `sponsor` — company financially sponsored the event
- `host` — company ran/organized the event
- `speaker` — company had a speaker at the event
- `unknown` — role unclear from available data

### Storage
Research output is stored in two places:
1. `research_data` table — raw `source="ai_synthesis"` record with full JSON content
2. `ai_insights` table — `insight_type="research_summary"` with human-readable summary text

The corresponding `enrichment_jobs` record (type=`web_research`) is marked `completed` on success, `failed` with error text if an exception occurs.

---

## 7. Phase 3 — Company & Contact Enrichment Agent

**Class:** `EnrichmentAgent` (`agents/enrichment_agent.py`)  
**LLM Temperature:** 0.2 (precision-focused, minimal hallucination)  
**Model:** Claude `claude-sonnet-4-6`

### Purpose
Take the raw lead data + Phase 2 research output and produce structured firmographic and contact-demographic data. Determine the company's exact profile and assess the contact's decision-making authority.

### Inputs
1. Raw lead data (company name, domain, contact name/title, any existing DB fields)
2. Full `ResearchOutput` from Phase 2

### Enrichment Output Schema

**Company block:**
```json
{
  "employee_count_range": "51-200",
  "revenue_range": "$10M-$50M",
  "industry": "Technology / SaaS",
  "sub_industry": "Event Management Software",
  "founded_year": 2018,
  "headquarters": "San Francisco, CA",
  "description": "Cloud-based event operations platform for enterprise marketing teams",
  "technologies": ["Cvent", "Salesforce", "HubSpot", "Zoom"]
}
```

**Contact block:**
```json
{
  "seniority": "Director",
  "department": "Events",
  "likely_responsibilities": [
    "Manages Cvent license and configuration",
    "Coordinates with marketing on event calendar",
    "Owns vendor selection for event tech"
  ],
  "decision_maker": true,
  "buyer_persona": "Events Operations Lead"
}
```

**Confidence score:** 0.0–1.0 (how confident the agent is in its output given available data)

### Database Write-Back
After enrichment, the pipeline **updates existing company and contact records** with the enriched data:
- `company.industry` ← `enrichment.company.industry`
- `company.description` ← `enrichment.company.description`
- `contact.department` ← `enrichment.contact.department`
- `contact.title` ← `enrichment.contact.seniority` (if not already set)

These write-backs ensure the main records stay current and that the UI displays enriched values everywhere.

### Storage
1. `enrichment_data` table — `data_type="company_contact"`, `provider="anthropic"`, full JSON in `data` column
2. `ai_insights` table — `insight_type="company_enrichment"` with narrative summary

---

## 8. Phase 4 — AI Lead Scoring Engine

**Class:** `ScoringAgent` (`agents/scoring_agent.py`)  
**LLM Temperature:** 0.2 (deterministic scoring)  
**Model:** Claude `claude-sonnet-4-6`

### Purpose
Assign a numeric fit score (0–100) and tier (Hot/Warm/Cold) to each lead, enabling sales prioritization and automated campaign routing.

### Inputs
1. Lead data (contact + company fields)
2. `EnrichmentOutput` from Phase 3
3. `ResearchOutput` from Phase 2

### The 10 Scoring Signals

| # | Signal Name | Weight | What It Measures |
|---|-------------|--------|-----------------|
| 1 | **Company Size Fit** | **15%** | Does the company's headcount match LaunchHouse's sweet spot (event teams that need outside help but aren't enterprise enough for full agencies)? |
| 2 | **Industry Fit** | **12%** | Is the company in a Cvent-heavy vertical? (Corporate events, association management, pharma, finance, tech conference orgs) |
| 3 | **Title / Seniority Fit** | **15%** | Is the contact a decision-maker or influencer for Cvent builds? (Director/VP/Head of Events, Marketing Operations, IT) |
| 4 | **Technology Fit** | **10%** | Does the company use Cvent or adjacent event tech (Aventri, RainFocus, bizzabo)? Any mention of event tech modernization? |
| 5 | **Recent Activity Signals** | **12%** | Hiring for event roles, conference announcements, new office/expansion, increased event calendars |
| 6 | **Funding / Growth** | **8%** | Recent funding rounds often precede expanded event calendars (investor days, road shows, conferences) |
| 7 | **Event Usage (Cvent)** | **10%** | Direct evidence of Cvent usage — sponsor/host/speaker at Cvent-powered events, Cvent case studies, Cvent community mentions |
| 8 | **Engagement History** | **8%** | Prior interaction with LaunchHouse (email opens, clicks, past replies, known relationship) |
| 9 | **Timing Signals** | **5%** | Budget cycle indicators (Q4 planning, fiscal year end), contract renewal timing, recent Cvent RFP activity |
| 10 | **Geographic Fit** | **5%** | US-based preferred (primary delivery market). North America / UK secondary. |

**Total weights sum to 100%.**

### Score Calculation

For each signal, Claude assigns a sub-score from **0.0 to 1.0** with reasoning. The final `overall_score` is:

$$\text{overall\_score} = \sum_{i=1}^{10} \text{signal\_score}_i \times \text{weight}_i \times 100$$

Example:
- Company Size: 0.8 × 0.15 = 0.12
- Industry Fit: 0.9 × 0.12 = 0.108
- Title/Seniority: 0.7 × 0.15 = 0.105
- Technology Fit: 1.0 × 0.10 = 0.10
- *(... sum all 10 ...)*
- **Final score: 72/100 → Warm tier**

### Tier Definitions

| Tier | Score Range | Sales Action | Color |
|------|-------------|-------------|-------|
| 🔴 **Hot** | 75–100 | Prioritize immediately — highest probability ICP match | Red/Crimson |
| 🟡 **Warm** | 50–74 | Moderate interest — nurture with personalized outreach | Amber |
| 🔵 **Cold** | 0–49 | Low probability — consider for future nurturing or disqualify | Blue/Gray |

### Scoring Output Schema (`ScoringOutput`)

```json
{
  "overall_score": 72.4,
  "tier": "warm",
  "signals": [
    {
      "signal_name": "Technology Fit",
      "score": 0.90,
      "weight": 0.10,
      "reasoning": "Company mentioned Cvent in two job postings and LinkedIn bio references 'Cvent Community'"
    }
  ],
  "explanation": "Strong technology fit with confirmed Cvent usage. Director-level contact in Events team with likely purchasing authority. Company is 200-500 employees in growth phase with recent Series B - typical pre-expansion event calendar growth. Scored warm due to no direct recent engagement and uncertain timing.",
  "recommended_action": "Add to warm nurture sequence. Lead with T8 template if upcoming events confirmed, otherwise T1/T6."
}
```

### Storage
1. `lead_scores` table — `overall_score`, `tier`, `signal_scores` (full JSON), `explanation`, `model_used="claude"`
2. `ai_insights` table — `insight_type="lead_score"` with narrative
3. `lead.status` updated to `"scored"`

---

## 9. Phase 5 — Personalization & Email Generation

**Class:** `PersonalizationAgent` (`agents/personalization_agent.py`)  
**Model:** Claude `claude-sonnet-4-6`  
**Template Library:** 17 templates (T1–T17)

### Purpose
Generate hyper-personalized, on-brand cold email copy by selecting the right template from the playbook and filling it with lead-specific context. The output is a review-ready email draft — not a robo-blast.

### Context Provided to the Agent

The agent receives:
1. **Lead data** — contact name, title, company, industry, location
2. **Research data** — events attended, recent news, technology stack, buying signals (from Phases 2–3)
3. **Sender info** — first name, calendar link, company name (LaunchHouse Events)
4. **Step config** — which sequence step this is (1–4)
5. **Previous email subject** — for reply-handler continuity
6. **Reply intent** — if the lead has replied, the classified intent (positive/not-now/wrong-contact/etc.)

### Template Selection Hierarchy (Strict Priority Order)

The agent follows this decision tree — the **first matching condition wins**:

```
1. Reply received?
   ├─ Intent = positive interest          → T10 (Positive Interest Reply)
   ├─ Intent = "send more info"           → T11 (Send More Info Reply)
   ├─ Intent = "not now" / deferral       → T12 (Not Now Reply)
   ├─ Intent = "already have support"     → T13 (Already Have Support Reply)
   └─ Intent = wrong contact / referral   → T14 (Wrong Contact / Referral Ask)

2. No reply — upcoming event confirmed?
   ├─ Event 0–30 days away                → T7 (Rush Framing)
   ├─ Event 31–120 days away              → T8 (Build Scoping — highest converting)
   └─ Event 120+ days away / past event   → T5 (Event Trigger)

3. Recent news ≤45 days + events inferable → T9 (News Trigger)

4. No event/news but activity inferable    → T6 (Fit-Based)

5. Core sequence steps (default):
   ├─ Step 1                              → T1 (Initial Outreach)
   ├─ Step 2                              → T2 (Value Add Follow-Up)
   ├─ Step 3                              → T3 (Bump — "worth a reply?")
   └─ Step 4                              → T4 (Break-Up / Final Touch)

6. Scenario templates (special cases):
   ├─ Voicemail left                      → T15 (Voicemail Follow-Up)
   ├─ Meeting just booked                 → T16 (Meeting Confirmation)
   └─ Post-call                           → T17 (Post-Call Recap)
```

### The 17 Templates — Summary

#### Core Sequence
| Template | Name | Timing | CTA |
|----------|------|--------|-----|
| T1 | Initial Outreach | Day 1 | One-pager or 15-min call |
| T2 | Value Add Follow-Up | Day 4 | Share useful content + light ask |
| T3 | Bump | Day 9 | "Worth a reply or not?" |
| T4 | Break-Up | Day 20 | Final touch → moves to nurture |

#### Event & News Triggers
| Template | Name | Condition | Key Framing |
|----------|------|-----------|-------------|
| T5 | Event Trigger | Verified event, any date | Event-specific Cvent build angle |
| T6 | Fit-Based | No event found, activity inferable | Industry/motion overflow capacity |
| T7 | Upcoming Event — Rush | 0–30 days to event | Rush capacity, same-day turnaround |
| T8 | Upcoming Event — Build | 31–120 days | Fixed-fee build scoping (highest-converting) |
| T9 | News Trigger | News ≤45 days + event implication | Congratulate + anticipate event expansion |

#### Reply Handlers
| Template | Name | Trigger |
|----------|------|---------|
| T10 | Positive Interest | Lead expressed interest |
| T11 | Send More Info | Lead asked for details |
| T12 | Not Now | Lead deferred |
| T13 | Already Have Support | Lead has existing vendor |
| T14 | Wrong Contact / Referral | Reached wrong person |

#### Scenario Templates
| Template | Name | Trigger |
|----------|------|---------|
| T15 | Voicemail Follow-Up | Within 30 min of voicemail |
| T16 | Meeting Confirmation | Immediately after booking |
| T17 | Post-Call Recap | Within 2 hours of call |

### Token System
Each template uses `{{token}}` placeholders that the agent fills from lead/research data:

| Token | Source | Example |
|-------|--------|---------|
| `{{first_name}}` | `contact.first_name` | "Sarah" |
| `{{company_name}}` | `company.name` | "Acme Corp" |
| `{{event_name}}` | Research events_attended | "Dreamforce 2025" |
| `{{event_date_phrase}}` | Research events_attended | "mid-September" |
| `{{days_out}}` | Computed from event date | "43" |
| `{{news_headline_short}}` | Research recent_news | "your Series B" |
| `{{news_event_implication}}` | LLM-generated from news | "growth-stage companies typically double their event calendar" |
| `{{company_vertical_or_motion}}` | Enrichment industry | "enterprise SaaS" |
| `{{sender_first_name}}` | settings / SenderAccount | "Snehdeep" |
| `{{sender_calendar_link}}` | settings | Calendly URL |

### Sequence Suppression Rules
- After T4 (break-up email), no new sequence starts within **90 days**
- **Maximum 4 emails** in any active sequence
- Reply received at any step → all remaining sequence steps route to reply handlers
- "Not now" reply → log revisit window, resume outreach at that time

### Email Output Format
```json
{
  "subject": "Cvent build plan for Dreamforce 2025?",
  "body_html": "<html>...</html>",
  "body_text": "Hi Sarah,\n\nDreamforce in mid-September...",
  "template_used": "T8",
  "personalization_hooks": [
    "event: Dreamforce 2025 (31-120 days)",
    "role: sponsor",
    "template: T8"
  ]
}
```

---

## 10. Phase 6 — Campaign Execution & Email Delivery

### Campaign Structure

A campaign contains:
- **Sequence steps** — ordered array of `{ step, delay_days, condition, subject_hint }` objects
- **Sender account** — which FROM email and display name to use
- **Status** — draft / active / paused / completed

Standard 4-step sequence:
```
Step 0: Day 0  (immediate)
Step 1: Day 4  (delay_days: 4, condition: "no_reply")
Step 2: Day 9  (delay_days: 5, condition: "no_reply")
Step 3: Day 20 (delay_days: 11, condition: "no_reply")
```

### Campaign Lead Processing (`process_campaign_lead`)

For each lead in the campaign:

1. **Check reply condition** — if step has `condition: "no_reply"` and a reply exists → skip, mark completed
2. **Fetch full context** — Lead, Contact, Company, AIInsights, ResearchData, EnrichmentData
3. **Resolve sender** — reads `SenderAccount` linked to campaign; falls back to `settings.sender_first_name`
4. **Handle Test Mode** — if tenant has test mode enabled with test email addresses, round-robins delivery to test emails (stored in `personalization_data.test_email_override`); production contacts untouched
5. **Run PersonalizationAgent** — generates subject + body for this lead + step
6. **Create Message record** — status=`"draft"`, `ai_generated=true`
7. **Schedule next FollowUp** — creates `follow_ups` record with `scheduled_at = now() + delay_days`
8. **Dispatch `send_email` task** — auto-queues draft for immediate delivery

### Email Delivery (`send_email` task)

1. Resolves recipient email from message record → contact → fallback
2. Resolves sender from `SenderAccount` or environment defaults
3. Sends via SendGrid API (HTML + plain text multipart)
4. Records `X-Message-Id` for tracking
5. Creates `EmailEvent` record (`event_type="sent"`)
6. Sets `message.status = "sent"`, `message.sent_at = now()`

**Fallback behavior (no SendGrid key set):** logs warning, assigns mock ID, marks sent — safe for local development.

### Follow-Up Scheduling (`process_follow_ups`)

A periodic Celery beat task runs on the configured interval and:
1. Queries `follow_ups` table for `status="scheduled"` and `scheduled_at <= now()`
2. For each due follow-up, dispatches `process_campaign_lead.delay(campaign_lead_id)`
3. Marks follow-up as `processed`

---

## 11. Orchestration & Pipeline Control

### Celery Configuration

| Item | Value |
|------|-------|
| Broker | Redis |
| Task queues | `default`, `enrichment`, `email` |
| Enrichment queue | `run_enrichment_pipeline` |
| Max retries | 3 (enrichment), 3 (email) |
| Retry delay | 60s (enrichment), 60s (email), 30s (campaign lead) |
| Beat scheduler | `process_follow_ups` periodic task |

### Enrichment Task Flow

```python
@celery_app.task(bind=True, max_retries=3, queue="enrichment")
def run_enrichment_pipeline(self, lead_id, tenant_id, job_ids):
    # job_ids = {"web_research": "uuid", "company": "uuid", "scoring": "uuid"}
    
    # Set lead enriching
    lead.enrichment_status = "enriching"
    
    # Step 1 — Research
    job_web_research.status = "running"
    research_output = await ResearchAgent().run(company_name, domain, contact_name)
    persist(ResearchData, AIInsight[research_summary])
    job_web_research.status = "completed"
    
    # Step 2 — Enrichment
    job_company.status = "running"
    enrichment_output = await EnrichmentAgent().run(raw_data, research_output)
    persist(EnrichmentData, AIInsight[company_enrichment])
    back_fill(company.industry, company.description, contact.department, contact.title)
    job_company.status = "completed"
    
    # Step 3 — Scoring
    job_scoring.status = "running"
    score_output = await ScoringAgent().run(lead_data, enrichment_output, research_output)
    persist(LeadScore, AIInsight[lead_score])
    lead.status = "scored"
    job_scoring.status = "completed"
    
    # Finalize
    lead.enrichment_status = "enriched"
    lead.enriched_at = now()
```

### Error Handling
- Each step catches exceptions independently — a failed research step does not block enrichment or scoring
- Failed jobs record `job.error = str(exception)` for debugging
- Pipeline-level failures trigger Celery retry up to 3 times with 60s delay
- All errors visible in the UI via the Enrichment tab on the Lead detail page

---

## 12. AI Infrastructure & Model Configuration

### LLM Layer (`BaseAgent`)

All agents extend `BaseAgent` which provides three pre-configured LLM clients:

| Method | Model | When Used |
|--------|-------|-----------|
| `get_llm()` | `claude-sonnet-4-6` (primary) | Research, enrichment, scoring, personalization |
| `get_fast_llm()` | `claude-sonnet-4-6` (fast model) | Lightweight classification tasks |
| `get_fallback_llm()` | `gpt-4o` / `gpt-4o-mini` (OpenAI) | Fallback if Claude unavailable |

### Retry Logic
`BaseAgent.invoke_with_retry()` wraps all LLM calls with:
- **3 attempts max**
- **Exponential backoff:** starts at 2s, max 30s

### Temperature Settings by Task

| Agent | Temperature | Rationale |
|-------|-------------|-----------|
| ResearchAgent | 0.3 | Some creativity for synthesis, but grounded |
| EnrichmentAgent | 0.2 | Precision-focused, minimize hallucination |
| ScoringAgent | 0.2 | Deterministic scoring, reproducible |
| PersonalizationAgent | ~0.7 | Natural-sounding email copy |

### Output Parsing
All agents use LangChain's `JsonOutputParser` to enforce structured output. If parsing fails, the raw response is logged and the job is marked failed.

### Cost Tracking
`EnrichmentJob` records `tokens_used` and `cost_usd` per job — enabling per-lead and aggregate cost analysis. (Currently populated by agent responses where token counts are available.)

---

## 13. Business Logic & ICP Assumptions

### Ideal Customer Profile (ICP)

LaunchHouse Events targets organizations that:
1. **Use Cvent** — or are actively evaluating event tech that includes Cvent
2. **Run B2B events** — corporate events, conferences, trade shows, summits, product launches
3. **Have dedicated event staff** — 1+ event manager/coordinator who builds in Cvent
4. **Experience capacity constraints** — their in-house team can't handle all builds, especially during peak periods or for complex configurations
5. **Are mid-market to enterprise** — typically 50–5,000 employees; too large for DIY, too small / budget-conscious for full-retainer agencies

### Vertical Priority (incorporated into scoring)
High-fit verticals (companies in these sectors run the most Cvent-powered events):
- Technology / SaaS (conferences, summits, user days)
- Financial Services (investor events, roadshows, compliance training)
- Pharmaceutical / Healthcare (HCP educational events, congresses)
- Associations & Nonprofits (annual conferences, chapter events)
- Professional Services (client events, thought leadership forums)

### Contact Persona Priority
| Persona | Titles | Why They Matter |
|---------|--------|----------------|
| **Events Lead** (primary) | Head of Events, Director of Events, VP Events | Owns Cvent, selects vendors, direct budget |
| **Marketing Ops** | Marketing Operations Manager, Director of Demand Gen | Often manages Cvent license/integration |
| **IT / Procurement** | IT Director, Technology Manager | Cvent platform owner in large orgs |
| **C-Suite** | CMO, COO | Final sign-off, especially SMB |

### Cvent-Specific Signal Scoring Logic
The "Event Usage (Cvent)" signal (weight: 10%) scores highest when:
- Company is listed as Cvent customer/case study
- Contact is active in the Cvent Community forums
- Job postings mention "Cvent" as required skill
- Public event registration pages are Cvent-powered (cvent.com/events/...)
- Company attended Cvent Connect (Cvent's annual conference)

### "Upcoming Event" Priority Logic
The most commercially valuable trigger is an upcoming event — especially in the **31–120 day window** (T8 template). This is because:
- Event builds in Cvent take 2–8 weeks for anything non-trivial
- The 31–120 day window is when the decision to outsource gets made
- Inside 30 days → rush work only (scoped differently, T7)
- Past 120 days → pipeline nurture, not urgency-based close (T5)

---

## 14. Scoring Reference Card

### Quick Lookup — Signal Weights

```
┌─────────────────────────────────────────────────────────┐
│               SCORING SIGNAL WEIGHTS                    │
├─────────────────────────────────── ────────────┬────────┤
│ Company Size Fit                               │  15%  │
│ Title / Seniority Fit                          │  15%  │
│ Industry Fit                                   │  12%  │
│ Recent Activity Signals                        │  12%  │
│ Technology Fit                                 │  10%  │
│ Event Usage (Cvent)                            │  10%  │
│ Funding / Growth                               │   8%  │
│ Engagement History                             │   8%  │
│ Timing Signals                                 │   5%  │
│ Geographic Fit                                 │   5%  │
├────────────────────────────────────────────────┴────────┤
│ TOTAL                                          │ 100%  │
└─────────────────────────────────────────────────────────┘
```

### Tier Color Reference

| Tier | Score | Action |
|------|-------|--------|
| 🔴 Hot | ≥ 75 | Prioritize — direct sales motion |
| 🟡 Warm | 50–74 | Personalized nurture sequence |
| 🔵 Cold | < 50 | Low-touch future nurture or skip |

---

## 15. Template Reference Card

### Template Selection Quick Reference

```
Situation                          → Template
─────────────────────────────────────────────────────
Positive reply                     → T10
"Send more info" reply             → T11
"Not now / later" reply            → T12
"Already have vendor" reply        → T13
Wrong contact                      → T14
─────────────────────────────────────────────────────
Event verified, WITHIN 30 days     → T7 (Rush)
Event verified, 31-120 days        → T8 (Build — best)
Event verified, 120+ days/past     → T5 (Event trigger)
News ≤45 days + events             → T9 (News trigger)
Activity inferable, no event/news  → T6 (Fit-based)
─────────────────────────────────────────────────────
Step 1 (no other context)          → T1 (Initial)
Step 2 (no reply yet)              → T2 (Value add)
Step 3 (no reply yet)              → T3 (Bump)
Step 4 (no reply yet)              → T4 (Break-up)
─────────────────────────────────────────────────────
Post-voicemail (<30 min)           → T15
Meeting booked (immediate)         → T16
Post-call (<2 hours)               → T17
```

### Core Sequence Timing

```
Day 0: T1 — Initial Outreach
Day 4: T2 — Value Add Follow-Up
Day 9: T3 — Bump ("worth a reply?")
Day 20: T4 — Break-Up (→ moves to 90-day nurture)
```

**Suppression:** 90 days after T4 before new sequence. Max 4 emails per sequence.

---

## 16. Current Limitations

### Research Quality
- **Live web search is active.** Tavily is the primary provider (4–5 queries per lead), with Firecrawl search as fallback and Firecrawl homepage scrape always running when a domain is available.
- **Knowledge recency depends on Tavily index freshness.** Very recently published pages (hours old) may not yet be indexed.
- **No direct Cvent event calendar API.** Upcoming events are found via web search results and homepage scrapes, not by querying Cvent's platform directly.

### Scoring Accuracy
- Heavy dependence on title/industry classification from raw data or enrichment output
- Engagement History signal (8%) is mostly 0 for new leads with no prior interaction
- Geographic Fit uses coarse inference (company location from `contact.location` or `company.location`)

### Personalization
- Token filling is LLM-generated — hallucinated event names or news are possible (especially with stubs returning nothing)
- `{{days_out}}` calculation requires structured `events_attended` data with accurate future dates — quality depends on research accuracy

### Email Infrastructure
- `message.message_id` field is reused (dual-purpose: stores recipient email during draft creation, then overwritten with SendGrid message ID post-send) — a technical debt item
- Reply classification (`intent` field on `Reply` model) is currently set externally — no automated reply parsing is implemented in the current codebase

---

## 17. Future Enhancements

### High Priority

1. **Live web search integration** ✅ *Completed April 2026*
   - Tavily (primary) and Firecrawl (fallback + homepage scrape) are wired and live
   - Remaining: real-time Cvent.com event calendar scraping via direct API
   - Remaining: LinkedIn Sales Navigator API for contact verification

2. **Automated reply classification**
   - NLP pipeline to parse inbound replies and set `intent` automatically
   - Categories: positive, not-now (with timeframe extraction), wrong-contact, unsubscribe, question, bounce
   - Would enable fully automated campaign branching without human review

3. **Custom scoring profiles**
   - Allow per-tenant or per-campaign signal weight customization
   - Enable vertical-specific profiles (e.g., different weights for Pharma vs. SaaS)

4. **Cvent Connect attendee data**
   - Direct integration with Cvent's attendee export for event participant verification
   - Would elevate Event Usage signal accuracy significantly

### Medium Priority

5. **A/B template testing**
   - Track open/reply rates per template variant
   - Automated winning variant selection
   - Long-form vs. short-form performance tracking

6. **ICP profile refinement loop**
   - Feed back won/converted leads to refine scoring weights
   - Automatic weight adjustment based on conversion data

7. **Enrichment refresh scheduling**
   - Auto-re-enrich leads after 90 days
   - Trigger re-enrichment on company funding news, leadership change, or job posting activity

8. **Multi-sender rotation**
   - Assign leads across multiple `SenderAccount` records for volume scaling
   - Warmup tracking per sender domain

### Lower Priority

9. **LinkedIn outreach channel**
   - Extend `Message` model to support LinkedIn DMs alongside email
   - Coordinated multi-channel sequences

10. **Webhook-based real-time triggers**
    - Cvent webhook for registration spike detection mid-sequence
    - HubSpot/Salesforce synced enrichment for CRM-first workflows

11. **Custom field scoring rules**
    - Allow admins to define scoring logic for `custom_fields` data
    - E.g., "if custom_field.cvent_tier = 'enterprise', add 10 points to Event Usage signal"

---

*Document generated from source code analysis. Last updated: April 25, 2026.*  
*Backend: `backend/app/agents/`, `backend/app/tasks/`, `backend/app/models/lead.py`, `backend/app/tools/web_search.py`*
