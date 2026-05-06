"""
OutreachAI – SQLAlchemy Models: Campaigns, Messages, Emails, Replies.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SenderAccount(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "sender_accounts"

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # gmail, sendgrid, ses
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    daily_limit: Mapped[int] = mapped_column(Integer, server_default="50")
    # IMAP credentials for reply polling
    imap_host: Mapped[str | None] = mapped_column(String(255))
    imap_user: Mapped[str | None] = mapped_column(String(255))
    imap_password: Mapped[str | None] = mapped_column(Text)
    sent_today: Mapped[int] = mapped_column(Integer, server_default="0")
    warmup_stage: Mapped[int] = mapped_column(Integer, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    health_score: Mapped[float] = mapped_column(Float, server_default="1.0")
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Campaign(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(50), server_default="draft", nullable=False
    )  # draft, active, paused, completed, archived
    campaign_type: Mapped[str] = mapped_column(String(50), server_default="outbound")
    vertical: Mapped[str | None] = mapped_column(String(50))  # sales, partnerships, recruitment, etc.

    # Sequence configuration
    sequence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="[]")
    schedule: Mapped[dict | None] = mapped_column(JSONB)
    settings: Mapped[dict | None] = mapped_column(JSONB, server_default="{}")

    # Sender
    sender_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sender_accounts.id")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Stats (denormalized for performance)
    total_leads: Mapped[int] = mapped_column(Integer, server_default="0")
    sent_count: Mapped[int] = mapped_column(Integer, server_default="0")
    open_count: Mapped[int] = mapped_column(Integer, server_default="0")
    click_count: Mapped[int] = mapped_column(Integer, server_default="0")
    reply_count: Mapped[int] = mapped_column(Integer, server_default="0")
    bounce_count: Mapped[int] = mapped_column(Integer, server_default="0")

    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def sequence_steps(self) -> int:
        """Number of steps in the campaign sequence."""
        seq = self.sequence or []
        return len(seq) if isinstance(seq, list) else 1

    # Relationships
    campaign_leads: Mapped[list["CampaignLead"]] = relationship(
        back_populates="campaign", lazy="selectin"
    )
    messages: Mapped[list["Message"]] = relationship(back_populates="campaign", lazy="selectin")


class CampaignLead(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "campaign_leads"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), server_default="pending", nullable=False
    )  # pending, active, completed, replied, bounced, unsubscribed, paused
    current_step: Mapped[int] = mapped_column(Integer, server_default="0")
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    personalization_data: Mapped[dict | None] = mapped_column(JSONB)

    campaign: Mapped["Campaign"] = relationship(back_populates="campaign_leads")


class EmailTemplate(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "email_templates"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str | None] = mapped_column(Text)
    variables: Mapped[list | None] = mapped_column(JSONB, server_default="[]")
    category: Mapped[str | None] = mapped_column(String(50))
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class Message(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "messages"

    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    sender_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sender_accounts.id")
    )
    channel: Mapped[str] = mapped_column(String(50), server_default="email")
    direction: Mapped[str] = mapped_column(String(10), server_default="outbound")
    sequence_step: Mapped[int | None] = mapped_column(Integer)

    # Email-specific
    subject: Mapped[str | None] = mapped_column(String(500))
    body_html: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str | None] = mapped_column(Text)

    # Tracking
    message_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(50), server_default="draft", nullable=False
    )  # draft, queued, sending, sent, delivered, bounced, failed

    # AI metadata
    ai_generated: Mapped[bool] = mapped_column(Boolean, server_default="false")
    ai_model: Mapped[str | None] = mapped_column(String(50))
    personalization_hooks: Mapped[list | None] = mapped_column(JSONB)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    campaign: Mapped["Campaign | None"] = relationship(back_populates="messages")
    email_events: Mapped[list["EmailEvent"]] = relationship(
        back_populates="message", lazy="selectin"
    )


class EmailEvent(Base, UUIDPrimaryKeyMixin, TenantMixin):
    __tablename__ = "email_events"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # sent, delivered, opened, clicked, bounced, complained, unsubscribed
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    message: Mapped["Message"] = relationship(back_populates="email_events")


class FollowUp(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "follow_ups"

    campaign_lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaign_leads.id"), nullable=False, index=True
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(50), server_default="scheduled")
    sent_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cancelled_reason: Mapped[str | None] = mapped_column(String(100))


class Reply(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "replies"

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False, index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(50), server_default="email")
    subject: Mapped[str | None] = mapped_column(String(500))
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)

    # AI analysis
    intent: Mapped[str | None] = mapped_column(String(50))
    sentiment: Mapped[str | None] = mapped_column(String(20))
    ai_analysis: Mapped[dict | None] = mapped_column(JSONB)
    suggested_response: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), server_default="medium")
    is_read: Mapped[bool] = mapped_column(Boolean, server_default="false")
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_body: Mapped[str | None] = mapped_column(Text)


class SuppressionList(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "suppression_list"

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)  # unsubscribed, bounced, complained
    source: Mapped[str | None] = mapped_column(String(100))
