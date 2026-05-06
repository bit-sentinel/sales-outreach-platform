"""Pydantic schemas for campaigns, messages, templates, replies."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Campaign ────────────────────────────────────────

class SequenceStep(BaseModel):
    step: int
    channel: str = "email"
    delay_days: int = 0
    subject_template: str | None = None
    body_template: str | None = None
    ai_generate: bool = True
    condition: str | None = None


class CampaignSchedule(BaseModel):
    timezone: str = "UTC"
    send_days: list[str] = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    send_start_hour: int = Field(default=9, ge=0, le=23)
    send_end_hour: int = Field(default=17, ge=0, le=23)


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    campaign_type: str = "outbound"
    vertical: str | None = None
    sequence: list[SequenceStep]
    schedule: CampaignSchedule | None = None
    sender_account_id: uuid.UUID | None = None
    settings: dict | None = None


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    sequence: list[SequenceStep] | None = None
    schedule: CampaignSchedule | None = None
    settings: dict | None = None


class CampaignResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    campaign_type: str
    vertical: str | None
    total_leads: int
    sent_count: int
    sequence_steps: int
    open_count: int
    click_count: int
    reply_count: int
    bounce_count: int
    launched_at: datetime | None
    created_at: datetime
    settings: dict | None = None

    model_config = {"from_attributes": True}


class CampaignDetailResponse(CampaignResponse):
    sequence: list[dict]
    schedule: dict | None
    settings: dict | None


class CampaignAddLeads(BaseModel):
    lead_ids: list[uuid.UUID] = Field(min_length=1, max_length=5000)


# ── Message Draft (for review UI) ──────────────────

class MessageDraftResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID | None
    lead_id: uuid.UUID
    lead_name: str | None = None
    lead_email: str | None = None
    lead_company: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    sequence_step: int | None
    subject: str | None
    body_html: str | None
    body_text: str | None
    status: str
    error_message: str | None = None
    ai_generated: bool
    personalization_hooks: list | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

class MessageResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID | None
    lead_id: uuid.UUID
    channel: str
    direction: str
    subject: str | None
    body_text: str | None
    status: str
    ai_generated: bool
    sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Template ────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    subject: str = Field(min_length=1, max_length=500)
    body_html: str
    body_text: str | None = None
    category: str | None = None
    variables: list[str] = []


class TemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    subject: str
    body_html: str
    body_text: str | None
    variables: list | None
    category: str | None
    is_ai_generated: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Reply ───────────────────────────────────────────

class ReplyResponse(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    lead_id: uuid.UUID
    channel: str
    subject: str | None
    body_text: str | None
    intent: str | None
    sentiment: str | None
    priority: str
    is_read: bool
    suggested_response: str | None
    created_at: datetime
    responded_at: datetime | None
    response_body: str | None = None
    # Enriched – populated by the route handler
    contact_name: str | None = None
    company_name: str | None = None
    ai_summary: str | None = None
    suggested_action: str | None = None
    # Thread context – the original outbound email
    outbound_subject: str | None = None
    outbound_body_text: str | None = None
    # Campaign context
    campaign_id: uuid.UUID | None = None
    campaign_name: str | None = None
    campaign_sent_count: int | None = None

    model_config = {"from_attributes": True}


class ReplyRespondRequest(BaseModel):
    body_text: str = Field(min_length=1)
    body_html: str | None = None
    use_ai_suggestion: bool = False


# ── Sender Account ──────────────────────────────────

# ── Campaign Report ─────────────────────────────────

class ReportReply(BaseModel):
    id: uuid.UUID
    received_at: datetime
    subject: str | None
    body_text: str | None
    body_html: str | None
    intent: str | None
    sentiment: str | None
    responded_at: datetime | None
    response_body: str | None  # body of the outbound reply we sent back


class ReportMessage(BaseModel):
    id: uuid.UUID
    sequence_step: int | None
    step_label: str  # "Initial", "Follow-up 1", "Follow-up 2", etc.
    subject: str | None
    body_html: str | None
    body_text: str | None
    status: str
    sent_at: datetime | None
    ai_generated: bool
    replies: list[ReportReply]


class ReportLead(BaseModel):
    lead_id: uuid.UUID
    name: str | None
    email: str | None
    effective_email: str | None  # overridden email in test mode
    company: str | None
    title: str | None
    campaign_status: str
    messages: list[ReportMessage]


class CampaignReportSequenceStep(BaseModel):
    step: int
    delay_days: int
    channel: str
    subject_template: str | None
    ai_generate: bool


class CampaignReport(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    campaign_type: str
    vertical: str | None
    test_mode_enabled: bool
    test_emails: list[str]
    from_email: str | None
    from_name: str | None
    created_at: datetime
    launched_at: datetime | None
    completed_at: datetime | None
    total_leads: int
    sent_count: int
    open_count: int
    reply_count: int
    bounce_count: int
    sequence: list[CampaignReportSequenceStep]
    leads: list[ReportLead]


# ── Sender Account ─────────────────────────────────

class SenderAccountCreate(BaseModel):
    email: str
    display_name: str
    provider: str  # gmail, sendgrid, ses
    daily_limit: int = 50


class SenderAccountResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    provider: str
    daily_limit: int
    sent_today: int
    warmup_stage: int
    is_active: bool
    health_score: float
    created_at: datetime

    model_config = {"from_attributes": True}
