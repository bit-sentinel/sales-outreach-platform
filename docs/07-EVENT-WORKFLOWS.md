# 7. Event Workflows & Messaging Architecture

## Event-Driven Architecture Overview

The platform is built on an event-driven architecture where every state change emits an event consumed by downstream services. This ensures loose coupling, scalability, and auditability.

```
┌──────────────────────────────────────────────────────────────────┐
│                    EVENT BUS (Redis Streams)                      │
│                                                                  │
│  Streams:                                                        │
│  ├── outreach.leads          (lead lifecycle events)             │
│  ├── outreach.enrichment     (enrichment pipeline events)        │
│  ├── outreach.campaigns      (campaign lifecycle events)         │
│  ├── outreach.messages       (message delivery events)           │
│  ├── outreach.replies        (reply detection events)            │
│  ├── outreach.analytics      (analytics aggregation events)      │
│  └── outreach.notifications  (notification dispatch events)      │
│                                                                  │
│  Consumer Groups:                                                │
│  ├── enrichment-workers      (consumes: outreach.leads)          │
│  ├── scoring-workers         (consumes: outreach.enrichment)     │
│  ├── campaign-workers        (consumes: outreach.campaigns)      │
│  ├── messaging-workers       (consumes: outreach.messages)       │
│  ├── reply-workers           (consumes: outreach.replies)        │
│  ├── analytics-workers       (consumes: all streams)             │
│  └── notification-workers    (consumes: outreach.notifications)  │
└──────────────────────────────────────────────────────────────────┘
```

## Event Schema Standard

Every event follows a consistent envelope:

```json
{
  "event_id": "uuid-v4",
  "event_type": "lead.created",
  "version": "1.0",
  "timestamp": "2026-04-06T10:30:00Z",
  "tenant_id": "uuid",
  "actor": {
    "type": "user",         // user | system | agent
    "id": "uuid"
  },
  "data": {
    // event-specific payload
  },
  "metadata": {
    "source_service": "lead-service",
    "correlation_id": "uuid",  // traces a chain of related events
    "causation_id": "uuid"    // the event that caused this event
  }
}
```

---

## Complete Event Catalog

### Lead Events (Stream: `outreach.leads`)

| Event Type | Trigger | Data Payload | Consumers |
|---|---|---|---|
| `lead.created` | New lead created | `{lead_id, contact_id, company_id, source}` | enrichment-service |
| `lead.batch_created` | Batch import complete | `{batch_id, lead_ids[], count}` | enrichment-service |
| `lead.updated` | Lead fields changed | `{lead_id, changed_fields}` | analytics-service |
| `lead.stage_changed` | Pipeline stage moved | `{lead_id, old_stage, new_stage}` | analytics-service, notification-service |
| `lead.assigned` | Lead assigned to user | `{lead_id, assigned_to, assigned_by}` | notification-service |
| `lead.deleted` | Lead soft-deleted | `{lead_id}` | analytics-service |
| `lead.merged` | Duplicate leads merged | `{surviving_id, merged_ids[]}` | all services |

### Enrichment Events (Stream: `outreach.enrichment`)

| Event Type | Trigger | Data Payload | Consumers |
|---|---|---|---|
| `enrichment.started` | Enrichment job begins | `{job_id, lead_id}` | analytics-service |
| `enrichment.research_complete` | Raw research gathered | `{job_id, lead_id, sources_count}` | — |
| `enrichment.extraction_complete` | Structured data extracted | `{job_id, lead_id, completeness}` | — |
| `enrichment.completed` | Full enrichment done | `{job_id, lead_id, completeness_score}` | scoring-service, notification-service |
| `enrichment.failed` | Enrichment failed | `{job_id, lead_id, error}` | notification-service |
| `lead.enriched` | Lead data enriched (alias) | `{lead_id, enrichment_id}` | scoring-service |

### Scoring Events (Stream: `outreach.enrichment`)

| Event Type | Trigger | Data Payload | Consumers |
|---|---|---|---|
| `lead.scored` | Score calculated | `{lead_id, score, tier, profile}` | campaign-service, notification-service |
| `lead.tier_changed` | Tier changed | `{lead_id, old_tier, new_tier}` | notification-service |

### Campaign Events (Stream: `outreach.campaigns`)

| Event Type | Trigger | Data Payload | Consumers |
|---|---|---|---|
| `campaign.created` | Campaign created | `{campaign_id, name, type}` | — |
| `campaign.generating` | Email generation started | `{campaign_id, lead_count}` | — |
| `campaign.ready` | All emails generated/approved | `{campaign_id}` | notification-service |
| `campaign.launched` | Campaign activated | `{campaign_id, total_leads}` | messaging-service, analytics-service |
| `campaign.paused` | Campaign paused | `{campaign_id, reason}` | messaging-service |
| `campaign.resumed` | Campaign resumed | `{campaign_id}` | messaging-service |
| `campaign.completed` | All messages sent | `{campaign_id, metrics}` | analytics-service, notification-service |
| `campaign.cancelled` | Campaign cancelled | `{campaign_id}` | messaging-service |

### Message Events (Stream: `outreach.messages`)

| Event Type | Trigger | Data Payload | Consumers |
|---|---|---|---|
| `message.generated` | AI generated email | `{message_id, lead_id, campaign_id}` | — |
| `message.approved` | Human approved email | `{message_id, approved_by}` | — |
| `message.queued` | Queued for sending | `{message_id, scheduled_at}` | messaging-service |
| `message.sending` | Send attempt started | `{message_id, provider}` | — |
| `message.sent` | Successfully sent | `{message_id, provider_id, sent_at}` | analytics, scheduler |
| `message.delivered` | Delivery confirmed | `{message_id, delivered_at}` | analytics-service |
| `message.opened` | Email opened | `{message_id, opened_at}` | analytics, scoring |
| `message.clicked` | Link clicked | `{message_id, url, clicked_at}` | analytics, scoring |
| `message.bounced` | Email bounced | `{message_id, bounce_type, reason}` | analytics, suppression |
| `message.failed` | Send failed | `{message_id, error}` | notification-service |
| `message.spam_complaint` | Spam reported | `{message_id}` | suppression-service |

### Reply Events (Stream: `outreach.replies`)

| Event Type | Trigger | Data Payload | Consumers |
|---|---|---|---|
| `reply.received` | Reply detected | `{reply_id, lead_id, campaign_id}` | reply-service |
| `reply.analyzed` | AI analysis complete | `{reply_id, intent, sentiment, urgency}` | notification-service, scoring |
| `reply.response_generated` | AI response ready | `{reply_id, suggested_response}` | notification-service |
| `reply.response_sent` | Response sent | `{reply_id, message_id}` | analytics-service |

### Follow-up Events (Stream: `outreach.messages`)

| Event Type | Trigger | Data Payload | Consumers |
|---|---|---|---|
| `followup.scheduled` | Follow-up scheduled | `{followup_id, lead_id, due_at}` | — |
| `followup.due` | Follow-up is due | `{followup_id, lead_id}` | personalization-service, messaging-service |
| `followup.sent` | Follow-up sent | `{followup_id, message_id}` | analytics-service |
| `followup.cancelled` | Follow-up cancelled | `{followup_id, reason}` | — |

---

## Workflow Definitions

### Workflow 1: Lead Import & Enrichment

```
┌──────────────────────────────────────────────────────────────────┐
│                  LEAD IMPORT & ENRICHMENT WORKFLOW                │
│                                                                  │
│  1. User uploads CSV                                             │
│     │                                                            │
│  2. ├──► Validate file format, size, structure                   │
│     │                                                            │
│  3. ├──► Parse rows, map columns                                 │
│     │                                                            │
│  4. ├──► For each row:                                           │
│     │    ├──► Normalize email, company name                      │
│     │    ├──► Check dedup (existing contact by email)            │
│     │    ├──► Create or update: Company → Contact → Lead         │
│     │    └──► Record in import_batch                             │
│     │                                                            │
│  5. ├──► Emit: lead.batch_created {batch_id, lead_ids[]}         │
│     │                                                            │
│  6. ├──► Enrichment Service receives event                       │
│     │    ├──► Create enrichment_job per lead                     │
│     │    ├──► Queue Celery tasks (batch, max 50 concurrent)      │
│     │    │                                                       │
│  7. │    ├──► For each lead (Celery worker):                     │
│     │    │    ├──► Run Research Agent                             │
│     │    │    │    ├──► SerpAPI: company search (3 queries)       │
│     │    │    │    ├──► Firecrawl: scrape website                 │
│     │    │    │    ├──► Tavily: news search                       │
│     │    │    │    └──► Store raw research_data rows              │
│     │    │    │                                                   │
│     │    │    ├──► Run Enrichment Agent                           │
│     │    │    │    ├──► LLM extracts structured data              │
│     │    │    │    └──► Store enrichment_data                     │
│     │    │    │                                                   │
│     │    │    ├──► Run Insight Agent                              │
│     │    │    │    ├──► LLM generates insights, hooks             │
│     │    │    │    └──► Store ai_insights                         │
│     │    │    │                                                   │
│     │    │    ├──► Update company record with enriched data       │
│     │    │    ├──► Update lead stage: new → enriched              │
│     │    │    └──► Emit: lead.enriched {lead_id}                 │
│     │    │                                                       │
│  8. │    └──► Scoring Service receives lead.enriched              │
│     │         ├──► Run Scoring Agent                              │
│     │         ├──► Store lead_score                               │
│     │         ├──► Update lead stage: enriched → scored           │
│     │         └──► Emit: lead.scored {lead_id, score, tier}      │
│     │                                                            │
│  9. └──► Notification: "Batch enrichment complete: 950/1000"     │
└──────────────────────────────────────────────────────────────────┘
```

### Workflow 2: Campaign Creation & Execution

```
┌──────────────────────────────────────────────────────────────────┐
│               CAMPAIGN CREATION & EXECUTION WORKFLOW              │
│                                                                  │
│  1. User creates campaign                                        │
│     ├──► Define target segment (score, tags, filters)            │
│     ├──► Select/create email template                            │
│     ├──► Configure sequence (steps, delays, conditions)          │
│     ├──► Set schedule (send window, throttle, daily limit)       │
│     └──► Select sender account                                   │
│                                                                  │
│  2. User clicks "Generate Emails"                                │
│     ├──► Campaign status → "generating"                          │
│     ├──► Resolve target segment → list of lead_ids               │
│     ├──► Check suppression list → exclude suppressed             │
│     ├──► Create campaign_lead records                            │
│     │                                                            │
│  3. ├──► For each lead (Celery, max 20 concurrent):              │
│     │    ├──► Load enrichment_data + ai_insights                 │
│     │    ├──► Run Personalization Agent (step 1 only)            │
│     │    ├──► Generate subject + body + variants                 │
│     │    ├──► Store message (status: draft/approved)             │
│     │    └──► If auto-approve: message status → approved         │
│     │                                                            │
│  4. ├──► Campaign status → "ready"                               │
│     ├──► Notify user: "500 emails ready for review"              │
│     │                                                            │
│  5. ├──► User reviews/edits emails (optional)                    │
│     │    └──► Approves individually or bulk-approve              │
│     │                                                            │
│  6. ├──► User clicks "Launch Campaign"                           │
│     │    ├──► Campaign status → "active"                         │
│     │    ├──► Emit: campaign.launched                             │
│     │                                                            │
│  7. ├──► Messaging Service processes approved messages            │
│     │    ├──► Respect schedule: send_window, timezone             │
│     │    ├──► Respect throttle: max_per_day, per_minute          │
│     │    ├──► For each message:                                   │
│     │    │    ├──► Check suppression list (final check)           │
│     │    │    ├──► Inject tracking pixel (open tracking)          │
│     │    │    ├──► Wrap links (click tracking)                    │
│     │    │    ├──► Send via channel (Email provider)              │
│     │    │    ├──► Record: message status → sent                  │
│     │    │    ├──► Record: email_event (type: sent)               │
│     │    │    ├──► Update: lead.first_contacted_at (if first)     │
│     │    │    ├──► Update: campaign metrics (total_sent++)        │
│     │    │    ├──► Schedule follow-up (step 2, +3 days)           │
│     │    │    └──► Emit: message.sent                             │
│     │                                                            │
│  8. ├──► Tracking webhooks process engagement                     │
│     │    ├──► Open: email_event, update campaign metrics          │
│     │    ├──► Click: email_event, update campaign metrics         │
│     │    ├──► Bounce: email_event, update suppression list        │
│     │    └──► Emit: message.opened / message.clicked / etc.       │
│     │                                                            │
│  9. └──► Campaign completes when all sequences done               │
│          └──► Campaign status → "completed"                       │
└──────────────────────────────────────────────────────────────────┘
```

### Workflow 3: Follow-up Execution

```
┌──────────────────────────────────────────────────────────────────┐
│                   FOLLOW-UP EXECUTION WORKFLOW                    │
│                                                                  │
│  1. Celery Beat runs every 5 minutes:                            │
│     └──► Query: follow_ups WHERE status='scheduled'              │
│          AND due_at <= NOW()                                     │
│                                                                  │
│  2. For each due follow-up:                                      │
│     ├──► Check condition:                                        │
│     │    ├──► "no_reply" → has lead replied since last email?    │
│     │    ├──► "no_open" → has lead opened the last email?        │
│     │    └──► "always" → always send                             │
│     │                                                            │
│  3. ├──► If condition NOT met:                                   │
│     │    └──► follow_up status → "condition_not_met"             │
│     │        (lead already replied, skip follow-up)              │
│     │                                                            │
│  4. ├──► If condition met:                                       │
│     │    ├──► Load lead context + conversation history            │
│     │    ├──► Run Personalization Agent (follow-up step N)       │
│     │    ├──► Generate follow-up email content                   │
│     │    ├──► If auto-approve: queue immediately                 │
│     │    ├──► Else: store as draft, notify user                  │
│     │    ├──► Send via Messaging Service                         │
│     │    ├──► follow_up status → "sent"                          │
│     │    ├──► Schedule next follow-up if sequence continues      │
│     │    └──► Emit: followup.sent                                │
│     │                                                            │
│  5. └──► If this was the last step in the sequence:              │
│          └──► campaign_lead status → "completed"                 │
└──────────────────────────────────────────────────────────────────┘
```

### Workflow 4: Reply Processing

```
┌──────────────────────────────────────────────────────────────────┐
│                   REPLY PROCESSING WORKFLOW                       │
│                                                                  │
│  1. Reply detected (Gmail API watch / IMAP poll / Webhook)       │
│     ├──► Extract email headers (In-Reply-To, References)         │
│     ├──► Match to original message_id → lead_id, campaign_id     │
│     ├──► Store inbound message record                            │
│     ├──► Store reply record (analysis_status: pending)           │
│     └──► Emit: reply.received                                    │
│                                                                  │
│  2. Reply Service receives reply.received:                       │
│     ├──► Cancel pending follow-ups for this lead                 │
│     │    (prevents double-sending after reply)                   │
│     │                                                            │
│  3. ├──► Run Reply Analysis Agent:                               │
│     │    ├──► Input: reply content + original email + context    │
│     │    ├──► Output: intent, sentiment, urgency, summary        │
│     │    └──► Store analysis on reply record                     │
│     │                                                            │
│  4. ├──► Based on intent:                                        │
│     │    ├──► "interested" / "meeting_request":                  │
│     │    │    ├──► Update lead tier → Hot (if not already)       │
│     │    │    ├──► Update lead stage → "replied"                 │
│     │    │    ├──► Generate AI suggested response                │
│     │    │    └──► Notify user (HIGH priority)                   │
│     │    │                                                       │
│     │    ├──► "question":                                        │
│     │    │    ├──► Generate AI answer                            │
│     │    │    └──► Notify user (MEDIUM priority)                 │
│     │    │                                                       │
│     │    ├──► "not_interested":                                  │
│     │    │    ├──► Update lead stage → "lost"                    │
│     │    │    ├──► Cancel all follow-ups                         │
│     │    │    └──► Notify user (LOW priority)                    │
│     │    │                                                       │
│     │    ├──► "out_of_office":                                   │
│     │    │    ├──► Parse return date                             │
│     │    │    ├──► Reschedule follow-up after return date        │
│     │    │    └──► Do NOT notify user (automated handling)       │
│     │    │                                                       │
│     │    ├──► "wrong_person":                                    │
│     │    │    ├──► Extract redirected contact info if provided   │
│     │    │    └──► Notify user with suggestion                   │
│     │    │                                                       │
│     │    └──► "unsubscribe":                                     │
│     │         ├──► Add to suppression_list                       │
│     │         ├──► Cancel all follow-ups                         │
│     │         └──► Update lead stage → "archived"                │
│     │                                                            │
│  5. └──► Emit: reply.analyzed                                    │
│          └──► Update campaign reply metrics                      │
└──────────────────────────────────────────────────────────────────┘
```

---

## Messaging Channel Abstraction Layer

### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    MESSAGING ABSTRACTION LAYER                    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Channel Router                              │    │
│  │  message.channel == "email"  ──► EmailChannel            │    │
│  │  message.channel == "whatsapp" ──► WhatsAppChannel       │    │
│  │  message.channel == "linkedin" ──► LinkedInChannel       │    │
│  │  message.channel == "sms" ──► SMSChannel                 │    │
│  └──────────────┬──────────────────────────────────────────┘    │
│                 │                                                │
│  ┌──────────────▼──────────────────────────────────────────┐    │
│  │              EmailChannel                                │    │
│  │                                                          │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │    │
│  │  │  Gmail   │  │ SendGrid │  │   SES    │              │    │
│  │  │ Provider │  │ Provider │  │ Provider │              │    │
│  │  └──────────┘  └──────────┘  └──────────┘              │    │
│  │                                                          │    │
│  │  Provider Selection Logic:                               │    │
│  │  1. Use sender_account provider preference               │    │
│  │  2. Fallback to next provider on failure                 │    │
│  │  3. Round-robin for load distribution                    │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              WhatsAppChannel (Future)                     │    │
│  │  ┌──────────┐                                            │    │
│  │  │  Twilio  │                                            │    │
│  │  │ WhatsApp │                                            │    │
│  │  └──────────┘                                            │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │              LinkedInChannel (Future)                     │    │
│  │  ┌──────────┐  ┌──────────┐                              │    │
│  │  │ LinkedIn │  │ Browser  │                              │    │
│  │  │   API    │  │ Automati │                              │    │
│  │  └──────────┘  └──────────┘                              │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### Channel Interface (Python)

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from enum import Enum
from datetime import datetime

class ChannelType(str, Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    LINKEDIN = "linkedin"
    SMS = "sms"
    SLACK = "slack"

class DeliveryStatus(str, Enum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"

class OutboundMessage(BaseModel):
    message_id: str
    channel: ChannelType
    sender: dict
    recipient: dict  # {email, phone, linkedin_url, etc.}
    subject: str | None = None
    body_html: str | None = None
    body_text: str
    metadata: dict = {}

class DeliveryResult(BaseModel):
    success: bool
    provider: str
    provider_message_id: str | None = None
    status: DeliveryStatus
    error: str | None = None
    sent_at: datetime | None = None

class WebhookEvent(BaseModel):
    event_type: str  # sent, delivered, opened, clicked, bounced, etc.
    provider: str
    provider_message_id: str
    message_id: str | None = None
    timestamp: datetime
    metadata: dict = {}

class MessageChannel(ABC):
    """Abstract base for all messaging channels."""

    channel_type: ChannelType

    @abstractmethod
    async def send(self, message: OutboundMessage) -> DeliveryResult:
        pass

    @abstractmethod
    async def check_status(self, provider_message_id: str) -> DeliveryStatus:
        pass

    @abstractmethod
    async def handle_webhook(self, payload: dict) -> WebhookEvent:
        pass

    @abstractmethod
    async def validate_recipient(self, recipient: dict) -> bool:
        pass

class ChannelRouter:
    """Routes messages to the appropriate channel implementation."""

    def __init__(self):
        self._channels: dict[ChannelType, MessageChannel] = {}

    def register(self, channel: MessageChannel):
        self._channels[channel.channel_type] = channel

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        channel = self._channels.get(message.channel)
        if not channel:
            raise ValueError(f"Channel {message.channel} not registered")
        return await channel.send(message)
```

### Email Provider Implementation (Gmail Example)

```python
class GmailProvider(MessageChannel):
    channel_type = ChannelType.EMAIL

    def __init__(self, credentials_store):
        self.credentials_store = credentials_store

    async def send(self, message: OutboundMessage) -> DeliveryResult:
        creds = await self.credentials_store.get(message.sender["account_id"])
        service = build("gmail", "v1", credentials=creds)

        mime_message = MIMEMultipart("alternative")
        mime_message["To"] = message.recipient["email"]
        mime_message["From"] = message.sender["email"]
        mime_message["Subject"] = message.subject

        # Add tracking pixel
        tracked_html = self._inject_tracking_pixel(
            message.body_html, message.message_id
        )
        # Wrap links for click tracking
        tracked_html = self._wrap_links(tracked_html, message.message_id)

        mime_message.attach(MIMEText(message.body_text, "plain"))
        mime_message.attach(MIMEText(tracked_html, "html"))

        raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode()

        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        return DeliveryResult(
            success=True,
            provider="gmail",
            provider_message_id=result["id"],
            status=DeliveryStatus.SENT,
            sent_at=datetime.utcnow(),
        )
```

---

## Celery Task Configuration

```python
# celery_config.py

from celery import Celery
from celery.schedules import crontab

app = Celery("outreach_ai")

app.conf.update(
    broker_url="redis://redis:6379/0",
    result_backend="redis://redis:6379/1",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # Task routing
    task_routes={
        "enrichment.*": {"queue": "enrichment"},
        "scoring.*": {"queue": "scoring"},
        "messaging.*": {"queue": "messaging"},
        "ai.*": {"queue": "ai"},
        "analytics.*": {"queue": "analytics"},
    },

    # Rate limits per task
    task_annotations={
        "enrichment.research_lead": {"rate_limit": "30/m"},  # max 30 leads/min
        "messaging.send_email": {"rate_limit": "50/m"},       # max 50 emails/min
        "ai.generate_email": {"rate_limit": "20/m"},          # max 20 generations/min
    },

    # Retry policy
    task_default_retry_delay=60,  # 60 seconds
    task_max_retries=3,

    # Concurrency
    worker_concurrency=10,  # per worker process
    worker_prefetch_multiplier=2,

    # Beat schedule (periodic tasks)
    beat_schedule={
        "process-follow-ups": {
            "task": "scheduler.process_due_follow_ups",
            "schedule": 300.0,  # every 5 minutes
        },
        "poll-email-replies": {
            "task": "replies.poll_imap_replies",
            "schedule": 120.0,  # every 2 minutes
        },
        "refresh-analytics": {
            "task": "analytics.refresh_materialized_views",
            "schedule": 900.0,  # every 15 minutes
        },
        "warmup-sender-accounts": {
            "task": "messaging.process_warmups",
            "schedule": crontab(hour=9, minute=0),  # daily at 9 AM UTC
        },
        "daily-engagement-digest": {
            "task": "notifications.send_daily_digest",
            "schedule": crontab(hour=8, minute=0),  # daily at 8 AM UTC
        },
        "cleanup-old-research-data": {
            "task": "maintenance.cleanup_old_research",
            "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
        },
    },
)
```

## Redis Streams Implementation

```python
# events/bus.py

import json
import uuid
from datetime import datetime
from redis.asyncio import Redis

class EventBus:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def publish(
        self,
        stream: str,
        event_type: str,
        data: dict,
        tenant_id: str,
        actor: dict | None = None,
        correlation_id: str | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "event_type": event_type,
            "version": "1.0",
            "timestamp": datetime.utcnow().isoformat(),
            "tenant_id": tenant_id,
            "actor": json.dumps(actor or {"type": "system"}),
            "data": json.dumps(data),
            "correlation_id": correlation_id or event_id,
        }
        await self.redis.xadd(stream, event, maxlen=100000)
        return event_id

    async def subscribe(
        self,
        stream: str,
        group: str,
        consumer: str,
        handler,
        batch_size: int = 10,
    ):
        # Ensure consumer group exists
        try:
            await self.redis.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception:
            pass  # Group already exists

        while True:
            messages = await self.redis.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={stream: ">"},
                count=batch_size,
                block=5000,  # 5 second blocking read
            )
            for stream_name, stream_messages in messages:
                for msg_id, msg_data in stream_messages:
                    try:
                        event = {
                            k.decode(): v.decode() for k, v in msg_data.items()
                        }
                        event["data"] = json.loads(event["data"])
                        event["actor"] = json.loads(event["actor"])
                        await handler(event)
                        await self.redis.xack(stream, group, msg_id)
                    except Exception as e:
                        # Log error, message stays in pending for retry
                        logger.error(f"Failed to process {msg_id}: {e}")
```
