"""
SendGrid Inbound Parse webhook – receives replies for ALL sender accounts.

Configure in SendGrid dashboard:
  Host: launch-house.uk
  URL:  https://launch-house.uk/api/v1/webhooks/sendgrid/inbound?secret=<SENDGRID_WEBHOOK_SECRET>
  Check "POST the raw, full MIME message" — OFF (use default form fields)
"""

import json
import logging
import re

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_secret() -> str:
    from app.config import get_settings
    return get_settings().sendgrid_webhook_secret


def _strip_re(subject: str) -> str:
    return re.sub(r"^(Re:\s*)+", "", subject, flags=re.I).strip()


def _parse_in_reply_to(raw_headers: str) -> str | None:
    for line in raw_headers.splitlines():
        if line.lower().startswith("in-reply-to:"):
            m = re.search(r"<([^>]+)>", line)
            if m:
                return m.group(1)
    return None


@router.post("/sendgrid/inbound")
async def sendgrid_inbound(
    request: Request,
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """
    Receives inbound emails from SendGrid Inbound Parse for any sender account.
    Always returns 200 so SendGrid doesn't retry — we log and swallow errors.
    """
    from app.models.campaign import Message, Reply, Campaign, CampaignLead
    from app.models.lead import Lead, Contact
    from sqlalchemy import update

    # ── Verify secret token ──────────────────────────────────────────
    expected = _get_secret()
    if expected and secret != expected:
        logger.warning("sendgrid_inbound: invalid secret token")
        return {"status": "unauthorized"}

    # ── Parse multipart form ─────────────────────────────────────────
    try:
        form = await request.form()
    except Exception as e:
        logger.warning("sendgrid_inbound: failed to parse form: %s", e)
        return {"status": "error", "detail": "bad form data"}

    # `envelope` is a JSON string: {"from": "...", "to": ["..."]}
    envelope_raw = form.get("envelope", "{}")
    try:
        envelope = json.loads(envelope_raw)
    except Exception:
        envelope = {}

    from_email: str = (envelope.get("from") or "").lower().strip()
    subject: str = form.get("subject", "") or ""
    body_text: str = form.get("text", "") or ""
    body_html: str = form.get("html", "") or ""
    raw_headers: str = form.get("headers", "") or ""

    if not from_email:
        return {"status": "ignored", "reason": "no sender"}

    logger.info("sendgrid_inbound: from=%s subject=%r", from_email, subject)

    # ── Match to an outbound Message ─────────────────────────────────
    # Strategy 1: In-Reply-To header → Message.message_id (SendGrid's X-Message-Id)
    orig_message = None
    in_reply_to = _parse_in_reply_to(raw_headers)
    if in_reply_to:
        result = await db.execute(
            select(Message).where(
                Message.message_id == in_reply_to,
                Message.direction == "outbound",
                Message.status.in_(["sent", "delivered"]),
            )
        )
        orig_message = result.scalar_one_or_none()

    # Strategy 2: subject line matching
    if not orig_message and subject:
        bare = _strip_re(subject)
        if bare:
            result = await db.execute(
                select(Message)
                .where(
                    Message.subject.ilike(bare),
                    Message.direction == "outbound",
                    Message.status.in_(["sent", "delivered"]),
                )
                .order_by(Message.sent_at.desc())
                .limit(1)
            )
            orig_message = result.scalar_one_or_none()

    if not orig_message:
        logger.info("sendgrid_inbound: no matching outbound message for subject=%r in_reply_to=%r", subject, in_reply_to)
        return {"status": "ignored", "reason": "no matching outbound message"}

    # ── Test mode check ──────────────────────────────────────────────
    # If the sender is a test email, validate it maps to this lead/campaign.
    if orig_message.campaign_id:
        campaign_res = await db.execute(
            select(Campaign).where(Campaign.id == orig_message.campaign_id)
        )
        campaign = campaign_res.scalar_one_or_none()
        if campaign:
            snap = (campaign.settings or {}).get("test_mode_snapshot", {})
            if snap.get("enabled"):
                test_emails = {e["email"].lower() for e in snap.get("emails", []) if e.get("enabled")}
                if from_email in test_emails:
                    # Verify this lead was mapped to this test email
                    cl_res = await db.execute(
                        select(CampaignLead).where(
                            CampaignLead.lead_id == orig_message.lead_id,
                            CampaignLead.campaign_id == orig_message.campaign_id,
                        )
                    )
                    cl = cl_res.scalar_one_or_none()
                    if cl:
                        mapped = (cl.personalization_data or {}).get("test_email_override", "").lower()
                        if mapped and mapped != from_email:
                            logger.info(
                                "sendgrid_inbound: test reply from %s but lead mapped to %s — skipping",
                                from_email, mapped,
                            )
                            return {"status": "ignored", "reason": "test email mismatch"}

    # ── Duplicate check ──────────────────────────────────────────────
    existing = (await db.execute(
        select(Reply).where(
            Reply.lead_id == orig_message.lead_id,
            Reply.message_id == orig_message.id,
        )
    )).scalar_one_or_none()
    if existing:
        logger.info("sendgrid_inbound: duplicate reply for message %s", orig_message.id)
        return {"status": "duplicate"}

    # ── AI analysis ──────────────────────────────────────────────────
    intent = "interested"
    sentiment = "neutral"
    priority = "medium"
    suggested_response = None
    ai_analysis_data = None
    try:
        from app.agents.reply_analysis_agent import ReplyAnalysisAgent
        agent = ReplyAnalysisAgent()
        analysis = await agent.run(
            reply_text=body_text,
            original_message=orig_message.body_text,
        )
        if not analysis.get("parse_error"):
            intent = analysis.get("intent", "interested")
            sentiment = analysis.get("sentiment", "neutral")
            priority = analysis.get("priority", "medium")
            suggested_response = analysis.get("suggested_response")
            ai_analysis_data = {
                "key_points": analysis.get("key_points", []),
                "suggested_action": analysis.get("suggested_action"),
                "objections": analysis.get("objections", []),
                "questions": analysis.get("questions", []),
                "meeting_requested": analysis.get("meeting_requested", False),
                "reply_handler_template": analysis.get("reply_handler_template", "none"),
            }
    except Exception as agent_exc:
        logger.warning("sendgrid_inbound: AI analysis failed (non-fatal): %s", agent_exc)

    # ── Store Reply ──────────────────────────────────────────────────
    reply = Reply(
        tenant_id=orig_message.tenant_id,
        message_id=orig_message.id,
        lead_id=orig_message.lead_id,
        channel="email",
        subject=subject,
        body_text=body_text,
        body_html=body_html or None,
        intent=intent,
        sentiment=sentiment,
        priority=priority,
        suggested_response=suggested_response,
        ai_analysis=ai_analysis_data,
        is_read=False,
    )
    db.add(reply)

    if orig_message.campaign_id:
        await db.execute(
            update(Campaign)
            .where(Campaign.id == orig_message.campaign_id)
            .values(reply_count=Campaign.reply_count + 1)
        )

    await db.commit()
    logger.info(
        "sendgrid_inbound: ingested reply from=%s subject=%r intent=%s",
        from_email, subject, intent,
    )
    return {"status": "ok"}
