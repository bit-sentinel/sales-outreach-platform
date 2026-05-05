"""Reply inbox endpoints – list, detail, respond, ingest, AI suggestions."""

import uuid
from datetime import datetime, timezone
from math import ceil

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.api.deps import get_tenant_id, PaginationDep
from app.models.campaign import Reply, Message
from app.schemas.common import APIResponse, PaginatedData
from app.schemas.campaign import ReplyResponse, ReplyRespondRequest

router = APIRouter()


def _enrich(reply: Reply, contacts: dict, campaigns: dict, messages: dict) -> ReplyResponse:
    """Build an enriched ReplyResponse by joining contact/company/campaign/outbound data."""
    contact_name: str | None = None
    company_name: str | None = None
    if reply.lead_id in contacts:
        c = contacts[reply.lead_id]
        contact_name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or None
        company_name = c.get("company_name")

    outbound = messages.get(reply.message_id)
    outbound_subject = outbound.subject if outbound else None
    outbound_body_text = outbound.body_text if outbound else None

    campaign_id = None
    campaign_name = None
    campaign_sent_count = None
    if outbound and outbound.campaign_id:
        campaign_id = outbound.campaign_id
        camp = campaigns.get(outbound.campaign_id)
        if camp:
            campaign_name = camp.name
            campaign_sent_count = camp.sent_count

    ai_analysis = reply.ai_analysis or {}
    return ReplyResponse(
        id=reply.id,
        message_id=reply.message_id,
        lead_id=reply.lead_id,
        channel=reply.channel,
        subject=reply.subject,
        body_text=reply.body_text,
        intent=reply.intent,
        sentiment=reply.sentiment,
        priority=reply.priority,
        is_read=reply.is_read,
        suggested_response=reply.suggested_response,
        created_at=reply.created_at,
        responded_at=reply.responded_at,
        contact_name=contact_name,
        company_name=company_name,
        ai_summary=ai_analysis.get("summary"),
        suggested_action=ai_analysis.get("suggested_action"),
        outbound_subject=outbound_subject,
        outbound_body_text=outbound_body_text,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        campaign_sent_count=campaign_sent_count,
    )


async def _load_enrichment(db: AsyncSession, replies: list[Reply]):
    """Return contacts dict {lead_id → {first_name, last_name, company_name}} and messages dict."""
    from app.models.lead import Lead, Contact, Company

    lead_ids = list({r.lead_id for r in replies})
    message_ids = list({r.message_id for r in replies})

    contacts: dict[uuid.UUID, dict] = {}
    messages: dict[uuid.UUID, Message] = {}

    if lead_ids:
        lead_rows = (await db.execute(select(Lead).where(Lead.id.in_(lead_ids)))).scalars().all()
        contact_ids = [l.contact_id for l in lead_rows if l.contact_id]
        company_ids = [l.company_id for l in lead_rows if l.company_id]

        c_map: dict[uuid.UUID, Contact] = {}
        co_map: dict[uuid.UUID, Company] = {}
        if contact_ids:
            c_rows = (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
            c_map = {c.id: c for c in c_rows}
        if company_ids:
            co_rows = (await db.execute(select(Company).where(Company.id.in_(company_ids)))).scalars().all()
            co_map = {co.id: co for co in co_rows}

        for lead in lead_rows:
            c = c_map.get(lead.contact_id) if lead.contact_id else None
            co = co_map.get(lead.company_id) if lead.company_id else None
            contacts[lead.id] = {
                "first_name": c.first_name if c else "",
                "last_name": c.last_name if c else "",
                "company_name": co.name if co else None,
            }

    if message_ids:
        m_rows = (await db.execute(select(Message).where(Message.id.in_(message_ids)))).scalars().all()
        messages = {m.id: m for m in m_rows}

    # Load campaigns referenced by those messages
    from app.models.campaign import Campaign
    campaigns: dict[uuid.UUID, Campaign] = {}
    campaign_ids = {m.campaign_id for m in messages.values() if m.campaign_id}
    if campaign_ids:
        camp_rows = (await db.execute(select(Campaign).where(Campaign.id.in_(campaign_ids)))).scalars().all()
        campaigns = {c.id: c for c in camp_rows}

    return contacts, campaigns, messages


@router.get("/count")
async def unread_reply_count(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    count = (await db.execute(
        select(func.count()).where(Reply.tenant_id == tenant_id, Reply.is_read == False)  # noqa: E712
    )).scalar() or 0
    return APIResponse(data={"unread": count})


@router.get("", response_model=APIResponse[PaginatedData[ReplyResponse]])
async def list_replies(
    pagination: PaginationDep = Depends(),
    intent: str | None = None,
    priority: str | None = None,
    is_read: bool | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    query = select(Reply).where(Reply.tenant_id == tenant_id)
    if intent:
        query = query.where(Reply.intent == intent)
    if priority:
        query = query.where(Reply.priority == priority)
    if is_read is not None:
        query = query.where(Reply.is_read == is_read)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(Reply.created_at.desc())
    query = query.offset((pagination.page - 1) * pagination.page_size).limit(pagination.page_size)
    rows = (await db.execute(query)).scalars().all()

    contacts, campaigns, messages = await _load_enrichment(db, rows)
    items = [_enrich(r, contacts, campaigns, messages) for r in rows]

    total_pages = ceil(total / pagination.page_size) if total > 0 else 0
    return APIResponse(data=PaginatedData(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=total_pages,
        has_next=pagination.page * pagination.page_size < total,
        has_prev=pagination.page > 1,
    ))


@router.get("/{reply_id}", response_model=APIResponse[ReplyResponse])
async def get_reply(
    reply_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reply).where(Reply.id == reply_id, Reply.tenant_id == tenant_id)
    )
    reply = result.scalar_one_or_none()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    contacts, campaigns, messages = await _load_enrichment(db, [reply])
    return APIResponse(data=_enrich(reply, contacts, campaigns, messages))


@router.patch("/{reply_id}/read")
async def mark_reply_read(
    reply_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reply).where(Reply.id == reply_id, Reply.tenant_id == tenant_id)
    )
    reply = result.scalar_one_or_none()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    reply.is_read = True
    await db.commit()
    return APIResponse(message="Marked as read")


@router.patch("/{reply_id}/archive")
async def archive_reply(
    reply_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Mark reply as read (archive = read + hide from unread inbox)."""
    result = await db.execute(
        select(Reply).where(Reply.id == reply_id, Reply.tenant_id == tenant_id)
    )
    reply = result.scalar_one_or_none()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")
    reply.is_read = True
    await db.commit()
    return APIResponse(message="Archived")


@router.post("/{reply_id}/respond")
async def respond_to_reply(
    reply_id: uuid.UUID,
    body: ReplyRespondRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, To, From, Content
    from app.config import get_settings
    from app.models.lead import Lead, Contact
    from app.models.campaign import SenderAccount

    reply = (await db.execute(
        select(Reply).where(Reply.id == reply_id, Reply.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not reply:
        raise HTTPException(status_code=404, detail="Reply not found")

    # Get original outbound message for subject + sender info
    orig = (await db.execute(
        select(Message).where(Message.id == reply.message_id)
    )).scalar_one_or_none()

    # Resolve recipient (the lead who replied)
    to_email: str | None = None
    lead = (await db.execute(select(Lead).where(Lead.id == reply.lead_id))).scalar_one_or_none()
    if lead and lead.contact_id:
        contact = (await db.execute(select(Contact).where(Contact.id == lead.contact_id))).scalar_one_or_none()
        if contact:
            to_email = contact.email

    if not to_email:
        raise HTTPException(status_code=422, detail="Cannot resolve recipient email for this lead")

    settings = get_settings()
    from_email = settings.sendgrid_from_email or settings.email_default_from
    from_name = settings.email_default_from_name

    if orig and orig.sender_account_id:
        sender = (await db.execute(
            select(SenderAccount).where(SenderAccount.id == orig.sender_account_id)
        )).scalar_one_or_none()
        if sender:
            from_email = sender.email
            from_name = sender.display_name

    # Build Re: subject
    orig_subject = (orig.subject if orig else None) or ""
    reply_subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"

    body_text = body.body_text
    body_html = body.body_html or f"<p>{body_text.replace(chr(10), '<br>')}</p>"

    external_id: str | None = None
    if settings.sendgrid_api_key:
        sg_mail = Mail(from_email=From(from_email, from_name), to_emails=To(to_email), subject=reply_subject)
        sg_mail.content = [Content("text/plain", body_text), Content("text/html", body_html)]
        sg = SendGridAPIClient(settings.sendgrid_api_key)
        try:
            response = sg.send(sg_mail)
            external_id = response.headers.get("X-Message-Id")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Email delivery failed: {e}")

    now = datetime.now(timezone.utc)

    # Record the outbound response as a Message for tracking
    from app.models.campaign import EmailEvent
    import uuid as _uuid
    out_message = Message(
        tenant_id=tenant_id,
        campaign_id=orig.campaign_id if orig else None,
        lead_id=reply.lead_id,
        sender_account_id=orig.sender_account_id if orig else None,
        channel="email",
        direction="outbound",
        subject=reply_subject,
        body_html=body_html,
        body_text=body_text,
        status="sent",
        sent_at=now,
        ai_generated=False,
        message_id=external_id or f"reply-{_uuid.uuid4()}",
    )
    db.add(out_message)
    await db.flush()

    db.add(EmailEvent(
        tenant_id=tenant_id,
        message_id=out_message.id,
        event_type="sent",
    ))

    reply.responded_at = now
    await db.commit()
    return APIResponse(message="Reply sent")


# ── Ingest endpoint – called by the E2E test script after reading IMAP ────────

class ReplyIngest(BaseModel):
    message_id: uuid.UUID        # the outbound Message this is a reply to
    lead_id: uuid.UUID
    subject: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    intent: str | None = "interested"
    sentiment: str | None = "positive"
    priority: str = "high"
    received_at: datetime | None = None


@router.post("/ingest", response_model=APIResponse[ReplyResponse])
async def ingest_reply(
    body: ReplyIngest,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest an inbound reply captured from the sender inbox (e.g. via IMAP).
    Records it in the DB so it appears in the Replies tab and gates campaign sequence conditions.
    """
    # Verify the referenced outbound message belongs to this tenant
    msg_result = await db.execute(
        select(Message).where(Message.id == body.message_id, Message.tenant_id == tenant_id)
    )
    message = msg_result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Referenced outbound message not found")

    reply = Reply(
        tenant_id=tenant_id,
        message_id=body.message_id,
        lead_id=body.lead_id,
        channel="email",
        subject=body.subject,
        body_text=body.body_text,
        body_html=body.body_html,
        intent=body.intent,
        sentiment=body.sentiment,
        priority=body.priority,
        is_read=False,
    )
    db.add(reply)

    # Update campaign reply_count
    if message.campaign_id:
        from app.models.campaign import Campaign
        from sqlalchemy import update
        await db.execute(
            update(Campaign)
            .where(Campaign.id == message.campaign_id)
            .values(reply_count=Campaign.reply_count + 1)
        )

    await db.commit()
    await db.refresh(reply)
    contacts, campaigns, messages = await _load_enrichment(db, [reply])
    return APIResponse(data=_enrich(reply, contacts, campaigns, messages))


@router.get("/{reply_id}/ai-suggestion")
async def get_ai_suggestion(
    reply_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI-powered suggested response for a reply."""
    raise HTTPException(status_code=501, detail="Not implemented")
