"""Campaign management endpoints – CRUD, launch, pause, add leads."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.api.deps import get_current_user, get_tenant_id, PaginationDep
from app.schemas.common import APIResponse, PaginatedData
from app.schemas.campaign import (
    CampaignAddLeads,
    CampaignCreate,
    CampaignDetailResponse,
    CampaignReport,
    CampaignResponse,
    CampaignUpdate,
    MessageDraftResponse,
)
from app.services.campaign_service import CampaignService
from app.api.audit import log_action

router = APIRouter()


@router.get("", response_model=APIResponse[PaginatedData[CampaignResponse]])
async def list_campaigns(
    pagination: PaginationDep = Depends(),
    status_filter: str | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CampaignService(db, tenant_id)
    result = await svc.list_campaigns(
        page=pagination.page, page_size=pagination.page_size, status=status_filter
    )
    return APIResponse(data=result)


@router.post("", response_model=APIResponse[CampaignResponse], status_code=201)
async def create_campaign(
    body: CampaignCreate,
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CampaignService(db, tenant_id)
    campaign = await svc.create_campaign(body, created_by=current_user.id)
    await log_action(db, tenant_id=tenant_id, user_id=current_user.id,
                     action="campaign.create", resource_type="campaign",
                     resource_id=str(campaign.id),
                     details={"name": campaign.name})
    return APIResponse(data=CampaignResponse.model_validate(campaign))


@router.get("/{campaign_id}", response_model=APIResponse[CampaignDetailResponse])
async def get_campaign(
    campaign_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CampaignService(db, tenant_id)
    campaign = await svc.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return APIResponse(data=campaign)


@router.patch("/{campaign_id}", response_model=APIResponse[CampaignResponse])
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CampaignService(db, tenant_id)
    campaign = await svc.update_campaign(campaign_id, body)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return APIResponse(data=CampaignResponse.model_validate(campaign))


@router.post("/{campaign_id}/launch", response_model=APIResponse[CampaignResponse])
async def launch_campaign(
    campaign_id: uuid.UUID,
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CampaignService(db, tenant_id)
    campaign = await svc.launch_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await log_action(db, tenant_id=tenant_id, user_id=current_user.id,
                     action="campaign.launch", resource_type="campaign",
                     resource_id=str(campaign_id),
                     details={"name": campaign.name})
    return APIResponse(data=CampaignResponse.model_validate(campaign))


@router.post("/{campaign_id}/pause", response_model=APIResponse[CampaignResponse])
async def pause_campaign(
    campaign_id: uuid.UUID,
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CampaignService(db, tenant_id)
    campaign = await svc.pause_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await log_action(db, tenant_id=tenant_id, user_id=current_user.id,
                     action="campaign.pause", resource_type="campaign",
                     resource_id=str(campaign_id),
                     details={"name": campaign.name})
    return APIResponse(data=CampaignResponse.model_validate(campaign))


@router.post("/{campaign_id}/resume", response_model=APIResponse[CampaignResponse])
async def resume_campaign(
    campaign_id: uuid.UUID,
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CampaignService(db, tenant_id)
    campaign = await svc.resume_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await log_action(db, tenant_id=tenant_id, user_id=current_user.id,
                     action="campaign.resume", resource_type="campaign",
                     resource_id=str(campaign_id),
                     details={"name": campaign.name})
    return APIResponse(data=CampaignResponse.model_validate(campaign))


@router.post("/{campaign_id}/leads")
async def add_leads_to_campaign(
    campaign_id: uuid.UUID,
    body: CampaignAddLeads,
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CampaignService(db, tenant_id)
    count = await svc.add_leads(campaign_id, body.lead_ids)
    await log_action(db, tenant_id=tenant_id, user_id=current_user.id,
                     action="campaign.add_leads", resource_type="campaign",
                     resource_id=str(campaign_id),
                     details={"leads_added": count})
    return APIResponse(data={"added": count})


@router.delete("/{campaign_id}/leads/{lead_id}", status_code=204)
async def remove_lead_from_campaign(
    campaign_id: uuid.UUID,
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CampaignService(db, tenant_id)
    await svc.remove_lead(campaign_id, lead_id)


# ── Draft messages ───────────────────────────────────────────────────────────

@router.get("/{campaign_id}/messages", response_model=APIResponse[list[MessageDraftResponse]])
async def list_campaign_messages(
    campaign_id: uuid.UUID,
    status: str | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """List messages for a campaign, optionally filtered by status (e.g. draft, sent)."""
    from sqlalchemy import select
    from app.models.campaign import Message
    from app.models.lead import Lead, Contact, Company

    query = select(Message).where(
        Message.campaign_id == campaign_id,
        Message.tenant_id == tenant_id,
    )
    if status:
        query = query.where(Message.status == status)
    query = query.order_by(Message.created_at.desc())

    result = await db.execute(query)
    messages = result.scalars().all()

    # Enrich with lead/contact info in one pass
    lead_ids = list({m.lead_id for m in messages})
    lead_map: dict[uuid.UUID, dict] = {}
    if lead_ids:
        leads_result = await db.execute(select(Lead).where(Lead.id.in_(lead_ids)))
        leads = leads_result.scalars().all()
        contact_ids = [l.contact_id for l in leads if l.contact_id]
        company_ids = [l.company_id for l in leads if l.company_id]

        contacts: dict[uuid.UUID, Contact] = {}
        if contact_ids:
            c_result = await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))
            contacts = {c.id: c for c in c_result.scalars().all()}

        companies: dict[uuid.UUID, Company] = {}
        if company_ids:
            co_result = await db.execute(select(Company).where(Company.id.in_(company_ids)))
            companies = {co.id: co for co in co_result.scalars().all()}

        for lead in leads:
            contact = contacts.get(lead.contact_id) if lead.contact_id else None
            company = companies.get(lead.company_id) if lead.company_id else None
            lead_map[lead.id] = {
                "name": f"{contact.first_name} {contact.last_name}".strip() if contact else None,
                "email": contact.email if contact else None,
                "company": company.name if company else None,
            }

    # Resolve sender info (per-message sender account or settings default)
    from app.models.campaign import SenderAccount
    from app.config import get_settings as _get_settings
    _settings = _get_settings()
    sender_account_ids = list({m.sender_account_id for m in messages if m.sender_account_id})
    sender_map: dict[uuid.UUID, SenderAccount] = {}
    if sender_account_ids:
        sa_result = await db.execute(select(SenderAccount).where(SenderAccount.id.in_(sender_account_ids)))
        sender_map = {s.id: s for s in sa_result.scalars().all()}

    items = []
    for m in messages:
        info = lead_map.get(m.lead_id, {})
        sender = sender_map.get(m.sender_account_id) if m.sender_account_id else None
        from_email = sender.email if sender else str(_settings.sendgrid_from_email or _settings.email_default_from or "")
        from_name = sender.display_name if sender else (_settings.email_default_from_name or "")
        items.append(MessageDraftResponse(
            id=m.id,
            campaign_id=m.campaign_id,
            lead_id=m.lead_id,
            lead_name=info.get("name"),
            lead_email=info.get("email"),
            lead_company=info.get("company"),
            from_email=from_email,
            from_name=from_name,
            sequence_step=m.sequence_step,
            subject=m.subject,
            body_html=m.body_html,
            body_text=m.body_text,
            status=m.status,
            error_message=m.error_message,
            ai_generated=m.ai_generated,
            personalization_hooks=m.personalization_hooks,
            created_at=m.created_at,
        ))

    return APIResponse(data=items)


@router.patch("/{campaign_id}/messages/{message_id}", response_model=APIResponse[MessageDraftResponse])
async def update_campaign_message(
    campaign_id: uuid.UUID,
    message_id: uuid.UUID,
    body: dict,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Edit subject/body of a draft message before sending."""
    from sqlalchemy import select
    from app.models.campaign import Message

    result = await db.execute(
        select(Message).where(
            Message.id == message_id,
            Message.campaign_id == campaign_id,
            Message.tenant_id == tenant_id,
        )
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.status != "draft":
        raise HTTPException(status_code=409, detail=f"Only draft messages can be edited (current status: '{message.status}')")

    if "subject" in body:
        message.subject = body["subject"]
    if "body_text" in body:
        message.body_text = body["body_text"]
        # Rebuild HTML from plain text so SendGrid renders it properly
        html_body = "<br>".join(
            ("<b>" + line + "</b>" if line.strip() == "" else line)
            for line in (body["body_text"] or "").splitlines()
        )
        message.body_html = f'<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#222">{html_body}</div>'

    await db.commit()
    await db.refresh(message)

    return APIResponse(data=MessageDraftResponse(
        id=message.id,
        campaign_id=message.campaign_id,
        lead_id=message.lead_id,
        sequence_step=message.sequence_step,
        subject=message.subject,
        body_html=message.body_html,
        body_text=message.body_text,
        status=message.status,
        ai_generated=message.ai_generated,
        personalization_hooks=message.personalization_hooks,
        created_at=message.created_at,
    ))


@router.post("/{campaign_id}/messages/{message_id}/send", response_model=APIResponse[MessageDraftResponse])
async def send_campaign_message(
    campaign_id: uuid.UUID,
    message_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Queue a draft message for immediate sending."""
    from sqlalchemy import select
    from app.models.campaign import Message

    result = await db.execute(
        select(Message).where(
            Message.id == message_id,
            Message.campaign_id == campaign_id,
            Message.tenant_id == tenant_id,
        )
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.status not in ("draft",):
        raise HTTPException(status_code=409, detail=f"Message is already '{message.status}', cannot send")

    from app.tasks.email_tasks import send_email
    send_email.delay(str(message_id))

    return APIResponse(data=MessageDraftResponse(
        id=message.id,
        campaign_id=message.campaign_id,
        lead_id=message.lead_id,
        sequence_step=message.sequence_step,
        subject=message.subject,
        body_html=message.body_html,
        body_text=message.body_text,
        status="queued",
        ai_generated=message.ai_generated,
        personalization_hooks=message.personalization_hooks,
        created_at=message.created_at,
    ))


# ── Step advancement (test/debug utility) ────────────────────────────────────

@router.post("/{campaign_id}/advance")
async def advance_campaign_leads(
    campaign_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Dispatch process_campaign_lead for every 'active' CampaignLead in the
    campaign, triggering AI generation for their next sequence step.
    Useful during testing to move past the Celery-beat delay window.
    """
    from sqlalchemy import select
    from app.models.campaign import CampaignLead
    from app.tasks.campaign_tasks import process_campaign_lead

    result = await db.execute(
        select(CampaignLead).where(
            CampaignLead.campaign_id == campaign_id,
            CampaignLead.tenant_id == tenant_id,
            CampaignLead.status == "active",
        )
    )
    leads = result.scalars().all()

    dispatched = 0
    for cl in leads:
        process_campaign_lead.delay(str(cl.id))
        dispatched += 1

    return APIResponse(data={"dispatched": dispatched, "campaign_id": str(campaign_id)})


# ── Campaign Report ────────────────────────────────────────────────────────────

@router.get("/{campaign_id}/report", response_model=APIResponse[CampaignReport])
async def get_campaign_report(
    campaign_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Return a comprehensive report for a single campaign."""
    svc = CampaignService(db, tenant_id)
    report = await svc.get_campaign_report(campaign_id)
    if not report:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return APIResponse(data=report)

