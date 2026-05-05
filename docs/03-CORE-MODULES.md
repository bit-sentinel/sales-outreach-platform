# 3. Core Platform Modules

## Module Architecture

Each module follows a consistent internal architecture:

```
module/
├── router.py          # FastAPI route definitions
├── service.py         # Business logic layer
├── repository.py      # Data access layer (SQLAlchemy)
├── models.py          # SQLAlchemy ORM models
├── schemas.py         # Pydantic request/response schemas
├── events.py          # Event emitters/consumers
├── tasks.py           # Celery async tasks
├── exceptions.py      # Module-specific exceptions
└── tests/
    ├── test_router.py
    ├── test_service.py
    └── test_tasks.py
```

---

## Module 1: Lead Management Module

**Responsibility**: CRUD operations for leads, contacts, companies. Import/export. Pipeline tracking. Deduplication.

### Capabilities
- Upload leads via CSV/Excel/JSON
- Manual lead creation
- Lead deduplication (email-based + fuzzy company match)
- Lead pipeline stages (New → Enriching → Scored → Contacted → Replied → Converted → Closed)
- Bulk operations (tag, assign, delete, move stage)
- Search and filtering (full-text, faceted)
- Lead export
- Custom fields per tenant

### Key Entities
- `Lead` (composite of Contact + Company)
- `Contact` (person details)
- `Company` (organization details)
- `LeadTag`, `LeadNote`, `LeadActivity`

### Events Emitted
- `lead.created`, `lead.updated`, `lead.deleted`
- `lead.batch_created`, `lead.stage_changed`
- `lead.assigned`, `lead.tagged`

---

## Module 2: Data Ingestion Service

**Responsibility**: Parse, validate, normalize, and import data from multiple sources.

### Capabilities
- CSV upload with column mapping UI
- Excel (.xlsx) import
- JSON/API import
- Duplicate detection during import
- Data validation rules (email format, required fields)
- Import history and rollback
- Incremental imports (merge with existing data)
- Batch processing for large files (chunked processing via Celery)

### Process Flow
```
Upload CSV ──► Parse & Validate ──► Column Mapping ──► Normalize ──►
Dedup Check ──► Bulk Insert ──► Emit "leads.batch_created"
```

### Rate Limits
- Max file size: 50MB
- Max rows per import: 100,000
- Concurrent imports per tenant: 3

---

## Module 3: Lead Enrichment Engine

**Responsibility**: Orchestrate multi-source data enrichment for each lead.

### Capabilities
- Automatic enrichment trigger on lead creation
- Manual re-enrichment
- Enrichment waterfall (try source A, fallback to B, then C)
- Enrichment completeness scoring
- Caching of enrichment results (TTL: 30 days)
- Rate limit management per data source

### Data Sources
| Source | Data Provided | Provider |
|---|---|---|
| Web Search | Company info, news, events | SerpAPI / Tavily |
| Website Scraping | About page, team, services | Firecrawl |
| LinkedIn (future) | Employee count, role details | Proxycurl / RapidAPI |
| Crunchbase (future) | Funding, investors, revenue | Crunchbase API |
| Clearbit (future) | Firmographics, tech stack | Clearbit API |

### Enrichment Schema
```json
{
  "company": {
    "industry": "string",
    "size": "string (1-10 / 11-50 / 51-200 / 201-500 / 501-1000 / 1000+)",
    "funding_total": "number",
    "funding_stage": "string (seed / series_a / series_b / ... / public)",
    "category": "string (enterprise / sme / startup / ngo / nonprofit / government)",
    "annual_revenue_range": "string",
    "tech_stack": ["string"],
    "headquarters": "string",
    "website": "string"
  },
  "events": {
    "event_marketing_maturity": "string (none / basic / intermediate / advanced)",
    "upcoming_events": [{"name": "string", "date": "string", "type": "string"}],
    "past_events": [{"name": "string", "date": "string", "type": "string"}],
    "conference_participation": ["string"],
    "event_budget_estimate": "string"
  },
  "signals": {
    "recent_news": [{"title": "string", "url": "string", "date": "string"}],
    "hiring_activity": "string (none / low / moderate / high)",
    "growth_signals": ["string"],
    "relevant_announcements": ["string"]
  }
}
```

### Events Emitted
- `enrichment.started`, `enrichment.completed`, `enrichment.failed`
- `lead.enriched`

---

## Module 4: Web Research Agent

**Responsibility**: Execute web searches and scrape relevant pages for a given lead/company.

### Tools Available to Agent
- `search_web(query)` → SerpAPI / Tavily
- `scrape_url(url)` → Firecrawl
- `search_news(company_name)` → Tavily / SerpAPI News
- `search_events(company_name)` → Custom event search
- `search_linkedin_company(company_name)` → (future)

### Process
```
Input: {company_name, contact_name, domain} ──►
  1. Search "{company_name} events conferences" ──► parse results
  2. Search "{company_name} funding news" ──► parse results
  3. Scrape company website ──► extract about, services, team info
  4. Search "{company_name} {contact_name}" ──► find relevant mentions
  5. Aggregate all raw research data
Output: {raw_research_data: [...sources]}
```

---

## Module 5: AI Insight Extraction Engine

**Responsibility**: Process raw research data into structured insights using LLMs.

### Capabilities
- Extract structured fields from unstructured research
- Identify business signals (growth, hiring, events)
- Generate company summaries
- Identify relevance signals for outreach
- Generate "hooks" for personalization (recent events, news, milestones)

### Events Emitted
- `insights.extracted`

---

## Module 6: Lead Scoring Engine

**Responsibility**: Calculate composite lead scores and tier assignments.

### Scoring Model

```
TOTAL SCORE = Σ (signal_weight × signal_value) / max_possible_score × 100

Tiers:
  Hot Opportunity:  score >= 75
  Warm Opportunity: score >= 40 AND score < 75
  Cold Lead:        score < 40
```

### Default Scoring Signals

| Signal | Weight | Scoring Logic |
|---|---|---|
| Upcoming Events | 15 | Has upcoming events = 15, planning events = 10, none = 0 |
| Event Marketing Maturity | 15 | Advanced = 15, Intermediate = 10, Basic = 5, None = 0 |
| Company Size | 10 | 1000+ = 10, 201-1000 = 8, 51-200 = 6, 11-50 = 4, 1-10 = 2 |
| Recent Funding | 12 | Funded in last 6mo = 12, last 1yr = 8, last 2yr = 4, none = 0 |
| Hiring Activity | 8 | High = 8, Moderate = 5, Low = 2, None = 0 |
| Tech Stack Compatibility | 10 | Uses Cvent = 10, competitor = 5, none = 0 |
| Growth Signals | 10 | Strong = 10, Moderate = 6, Weak = 2, None = 0 |
| Company Category | 5 | Enterprise = 5, SME = 4, Startup = 3, NGO = 2 |
| Engagement (opens) | 8 | Opened 3+ = 8, Opened 1-2 = 4, None = 0 |
| Engagement (replies) | 7 | Replied positive = 7, Replied neutral = 4, None = 0 |

### Scoring Profiles
Scoring weights are configurable per campaign/vertical through **Scoring Profiles**:
- `cvent_consultancy` (default, weighted toward events)
- `saas_sales` (weighted toward funding + tech stack)
- `recruitment` (weighted toward hiring + growth)

### Events Emitted
- `lead.scored`, `lead.tier_changed`

---

## Module 7: Personalization Engine

**Responsibility**: Generate personalized outreach content using enriched data + AI.

### Capabilities
- AI email generation with enriched context
- Template-based generation with AI enhancement
- Multi-variant generation (generate 2-3 variants per lead)
- Tone control (formal, conversational, consultative)
- Subject line generation + A/B variants
- Follow-up sequence generation (email 1, 2, 3…)

### Personalization Context
```
{
  contact: { name, title, company },
  company: { industry, size, category, tech_stack },
  enrichment: { events, funding, news, signals },
  scoring: { score, tier, top_signals },
  campaign: { template, tone, goal, value_proposition },
  sequence_position: 1,  // which email in the sequence
  previous_messages: []   // for follow-up context
}
```

### Events Emitted
- `email.generated`, `email.approved`, `email.edited`

---

## Module 8: Outreach Campaign Engine

**Responsibility**: Campaign lifecycle management — creation, configuration, launch, monitoring, pause, complete.

### Campaign States
```
Draft ──► Generating ──► Ready ──► Active ──► Paused ──► Completed
                                      │
                                      └──► Cancelled
```

### Capabilities
- Campaign creation with target leads, template, schedule
- Lead segmentation filters (by score, tags, pipeline stage, enrichment data)
- Send scheduling (time windows, timezone-aware, throttling)
- A/B testing (subject lines, email variants)
- Daily send limits per sender account
- Campaign pause/resume
- Exclusion lists (unsubscribed, bounced, already contacted)

### Campaign Configuration Schema
```json
{
  "name": "Q1 Cvent Enterprise Outreach",
  "type": "email_sequence",
  "target_segment": {
    "score_tier": ["hot", "warm"],
    "tags": ["enterprise"],
    "exclude_tags": ["unsubscribed"],
    "enrichment_filters": {
      "event_marketing_maturity": ["intermediate", "advanced"]
    }
  },
  "sequence": [
    {"step": 1, "delay_days": 0, "template_id": "initial_outreach"},
    {"step": 2, "delay_days": 3, "template_id": "follow_up_1", "condition": "no_reply"},
    {"step": 3, "delay_days": 7, "template_id": "follow_up_2", "condition": "no_reply"},
    {"step": 4, "delay_days": 14, "template_id": "breakup_email", "condition": "no_reply"}
  ],
  "schedule": {
    "timezone": "America/New_York",
    "send_window": {"start": "09:00", "end": "17:00"},
    "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "max_per_day": 100,
    "throttle_per_minute": 5
  },
  "sender_account_id": "uuid"
}
```

---

## Module 9: Messaging Channel Layer

**Responsibility**: Abstract message delivery across channels. All outbound communication flows through this layer.

### Channel Interface
```python
class MessageChannel(ABC):
    """Abstract base class for all messaging channels."""

    @abstractmethod
    async def send(self, message: OutboundMessage) -> DeliveryResult:
        """Send a message through this channel."""
        pass

    @abstractmethod
    async def check_delivery_status(self, provider_id: str) -> DeliveryStatus:
        """Check delivery status of a sent message."""
        pass

    @abstractmethod
    async def handle_webhook(self, payload: dict) -> WebhookEvent:
        """Process inbound webhook events (delivery, bounce, open, click)."""
        pass
```

### Channel Registry
```
ChannelRegistry
├── EmailChannel
│   ├── GmailProvider
│   ├── SendGridProvider
│   └── SESProvider
├── WhatsAppChannel (future)
│   └── TwilioWhatsAppProvider
├── LinkedInChannel (future)
│   └── LinkedInAPIProvider
├── SMSChannel (future)
│   └── TwilioSMSProvider
└── SlackChannel (future)
    └── SlackAPIProvider
```

---

## Module 10: Email Delivery Service

**Responsibility**: Reliable email sending with deliverability optimization.

### Capabilities
- Multi-provider support (Gmail API, SendGrid, SES)
- Automatic failover between providers
- Domain authentication (SPF, DKIM, DMARC)
- Warm-up schedules for new domains/IPs
- Bounce handling and suppression list management
- Rate limiting per provider and per domain
- Tracking pixel injection (opens)
- Link wrapping for click tracking

### Deliverability Strategy
```
1. Domain Setup: SPF + DKIM + DMARC for all sender domains
2. Warm-up: Start at 20 emails/day, increase 20% daily
3. Rotation: Rotate sender accounts to distribute volume
4. Throttling: Max 50 emails/hour per account initially
5. Reputation: Monitor bounce rate (<2%), spam rate (<0.1%)
6. Content: Avoid spam triggers, use text/html ratio
7. Engagement: Track opens/clicks, pause poor performers
```

---

## Module 11: Email Tracking System

**Responsibility**: Track email engagement events.

### Tracked Events
| Event | Method | Data Captured |
|---|---|---|
| Sent | API callback | timestamp, provider_message_id |
| Delivered | Webhook | timestamp |
| Opened | Tracking pixel | timestamp, user_agent, IP (anonymized) |
| Clicked | Link redirect | timestamp, link_url, user_agent |
| Bounced | Webhook | bounce_type (hard/soft), reason |
| Unsubscribed | Link handler | timestamp |
| Spam Complaint | Webhook (FBL) | timestamp |

---

## Module 12: Follow-up Scheduler

**Responsibility**: Schedule and execute follow-up messages based on campaign rules.

### Scheduling Logic
```
When message.sent:
  IF campaign has next step:
    Schedule follow_up at now + delay_days
    Store in follow_ups table with status="scheduled"

Every 5 minutes (Celery Beat):
  Query follow_ups WHERE due_at <= now AND status="scheduled"
  For each:
    Check condition (e.g., "no_reply" → query reply_events)
    IF condition met:
      Generate follow-up content (Personalization Engine)
      Queue for sending (Messaging Service)
      Update status = "sent"
    ELSE:
      Update status = "condition_not_met"
```

---

## Module 13: Reply Listener

**Responsibility**: Detect and ingest inbound replies.

### Detection Methods
- Gmail API watch (push notifications via Pub/Sub)
- IMAP polling (fallback, every 2 minutes)
- SendGrid Inbound Parse webhook
- SES receiving rules → SNS → Lambda → API

### Reply Matching
```
Inbound email ──► Extract In-Reply-To / References header
  ──► Match to sent message_id
  ──► Link to lead_id, campaign_id
  ──► Store reply in replies table
  ──► Emit "reply.received" event
```

---

## Module 14: AI Reply Analysis Engine

**Responsibility**: Analyze incoming replies with AI.

### Analysis Outputs
```json
{
  "summary": "The prospect expressed interest in learning more about Cvent consulting services and wants to schedule a call next week.",
  "intent": "interested",  // interested | not_interested | out_of_office | wrong_person | question | meeting_request | unsubscribe
  "sentiment": "positive", // positive | neutral | negative
  "urgency": "medium",     // low | medium | high
  "action_items": ["Schedule call", "Send service overview deck"],
  "suggested_response": "... AI generated response ...",
  "key_entities": ["next week", "consulting services", "Cvent"]
}
```

### Intent Categories
| Intent | Action |
|---|---|
| interested | Flag as Hot, notify user, generate response |
| meeting_request | Flag as Hot, suggest calendar link |
| question | Generate informative response |
| not_interested | Mark as Cold, stop follow-ups |
| out_of_office | Reschedule follow-up after return date |
| wrong_person | Log, suggest redirect |
| unsubscribe | Add to suppression list, stop all contact |

---

## Module 15: AI Response Generator

**Responsibility**: Generate contextual reply suggestions.

### Context Used
- Original outreach message
- Reply content
- Reply analysis (intent, sentiment)
- Lead enrichment data
- Campaign context
- Conversation history

---

## Module 16: Notification Service

**Responsibility**: Real-time notifications to users.

### Channels
- In-app (WebSocket push)
- Email digest (daily summary)
- Browser push notifications (future)

### Notification Types
| Event | Priority | Target |
|---|---|---|
| Reply received (interested) | High | Assigned user |
| Reply received (meeting) | High | Assigned user |
| Campaign completed | Medium | Campaign owner |
| Enrichment completed | Low | Batch owner |
| Lead scored Hot | Medium | Team |
| Daily engagement summary | Low | All users |

---

## Module 17: Analytics Engine

**Responsibility**: Aggregate and serve metrics.

### Metrics Generated
- Campaign performance (sent, delivered, opened, clicked, replied, converted)
- Lead pipeline (new, enriched, scored, contacted, replied, converted)
- Score distribution (hot/warm/cold breakdown)
- Time-series (daily sends, opens, replies)
- Top performing campaigns
- Most engaged leads
- A/B test results

### Implementation
- Materialized views in PostgreSQL for common queries
- Redis cached aggregations for dashboard loads
- Async recalculation via Celery tasks

---

## Module 18: Enterprise Dashboard UI

See section 8: UI Design (separate document).

---

## Module 19: Admin & Configuration Module

**Responsibility**: Platform configuration, user management, integrations.

### Capabilities
- Tenant settings (company name, branding, timezone)
- User management (invite, roles, permissions)
- Email account connections (OAuth for Gmail, API keys for SendGrid/SES)
- AI model configuration (LLM provider, API keys)
- Enrichment source configuration
- Scoring profile management
- Template library management
- Webhook configuration
- API key management
- Audit log viewing
