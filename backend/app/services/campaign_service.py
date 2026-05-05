"""
Campaign service – CRUD, launch, pause, resume, lead management.
"""

import uuid
from datetime import datetime, timezone
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignLead
from app.schemas.campaign import (
    CampaignCreate,
    CampaignDetailResponse,
    CampaignResponse,
    CampaignUpdate,
)
from app.schemas.common import PaginatedData


class CampaignService:
    VALID_TRANSITIONS = {
        "draft": ["active"],
        "active": ["paused", "completed"],
        "paused": ["active", "completed"],
        "completed": ["archived"],
    }

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def list_campaigns(
        self,
        page: int = 1,
        page_size: int = 25,
        status: str | None = None,
    ) -> PaginatedData[CampaignResponse]:
        from app.models.campaign import Message
        query = select(Campaign).where(Campaign.tenant_id == self.tenant_id)
        if status:
            query = query.where(Campaign.status == status)

        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        query = query.order_by(Campaign.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        campaigns = result.scalars().all()

        # Compute live sent_count and total_leads from messages/campaign_leads tables
        # (denormalized counters can be stale)
        from app.models.campaign import CampaignLead
        campaign_ids = [c.id for c in campaigns]
        live_sent: dict = {}
        live_leads: dict = {}
        if campaign_ids:
            sent_rows = await self.db.execute(
                select(Message.campaign_id, func.count())
                .where(Message.campaign_id.in_(campaign_ids))
                .where(Message.status.in_(["sent", "delivered"]))
                .group_by(Message.campaign_id)
            )
            live_sent = {row[0]: row[1] for row in sent_rows.fetchall()}

            lead_rows = await self.db.execute(
                select(CampaignLead.campaign_id, func.count())
                .where(CampaignLead.campaign_id.in_(campaign_ids))
                .group_by(CampaignLead.campaign_id)
            )
            live_leads = {row[0]: row[1] for row in lead_rows.fetchall()}

        items = []
        for c in campaigns:
            c.sent_count = live_sent.get(c.id, 0)
            c.total_leads = live_leads.get(c.id, c.total_leads)
            items.append(CampaignResponse.model_validate(c))

        return PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=ceil(total / page_size) if total > 0 else 0,
            has_next=page * page_size < total,
            has_prev=page > 1,
        )

    async def create_campaign(
        self, data: CampaignCreate, created_by: uuid.UUID
    ) -> Campaign:
        # Snapshot current test mode state at creation time so the badge
        # appears immediately on the draft card and is immune to later toggles.
        from sqlalchemy import select as _select
        from app.models.tenant import Tenant as _Tenant
        tenant = (await self.db.execute(
            _select(_Tenant).where(_Tenant.id == self.tenant_id)
        )).scalar_one_or_none()
        settings = dict(data.settings or {})
        if tenant:
            tm = (tenant.settings or {}).get("test_mode", {"enabled": False, "emails": []})
            settings["test_mode_snapshot"] = tm

        campaign = Campaign(
            tenant_id=self.tenant_id,
            name=data.name,
            description=data.description,
            campaign_type=data.campaign_type,
            vertical=data.vertical,
            sequence=[step.model_dump() for step in data.sequence],
            schedule=data.schedule.model_dump() if data.schedule else None,
            sender_account_id=data.sender_account_id,
            settings=settings,
            created_by=created_by,
        )
        self.db.add(campaign)
        await self.db.flush()
        return campaign

    async def get_campaign(self, campaign_id: uuid.UUID) -> CampaignDetailResponse | None:
        result = await self.db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id, Campaign.tenant_id == self.tenant_id
            )
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            return None
        return CampaignDetailResponse.model_validate(campaign)

    async def update_campaign(
        self, campaign_id: uuid.UUID, data: CampaignUpdate
    ) -> Campaign | None:
        result = await self.db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id, Campaign.tenant_id == self.tenant_id
            )
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            return None

        if campaign.status != "draft":
            # Only allow limited updates for non-draft campaigns
            pass

        update_data = data.model_dump(exclude_unset=True)
        if "sequence" in update_data and update_data["sequence"]:
            update_data["sequence"] = [s.model_dump() for s in data.sequence]
        if "schedule" in update_data and data.schedule:
            update_data["schedule"] = data.schedule.model_dump()

        for key, value in update_data.items():
            setattr(campaign, key, value)
        await self.db.flush()
        return campaign

    async def launch_campaign(self, campaign_id: uuid.UUID) -> Campaign | None:
        return await self._transition(campaign_id, "active")

    async def pause_campaign(self, campaign_id: uuid.UUID) -> Campaign | None:
        return await self._transition(campaign_id, "paused")

    async def resume_campaign(self, campaign_id: uuid.UUID) -> Campaign | None:
        return await self._transition(campaign_id, "active")

    async def _transition(self, campaign_id: uuid.UUID, target: str) -> Campaign | None:
        result = await self.db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id, Campaign.tenant_id == self.tenant_id
            )
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            return None

        allowed = self.VALID_TRANSITIONS.get(campaign.status, [])
        if target not in allowed:
            raise ValueError(
                f"Cannot transition from '{campaign.status}' to '{target}'"
            )

        campaign.status = target
        if target == "active" and not campaign.launched_at:
            campaign.launched_at = datetime.now(timezone.utc)

            from app.tasks.campaign_tasks import execute_campaign
            execute_campaign.delay(str(campaign.id))

        await self.db.flush()
        return campaign

    async def add_leads(self, campaign_id: uuid.UUID, lead_ids: list[uuid.UUID]) -> int:
        count = 0
        for lead_id in lead_ids:
            cl = CampaignLead(
                tenant_id=self.tenant_id,
                campaign_id=campaign_id,
                lead_id=lead_id,
            )
            self.db.add(cl)
            count += 1
        await self.db.flush()

        # Update campaign total_leads count
        result = await self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        campaign = result.scalar_one_or_none()
        if campaign:
            campaign.total_leads = (campaign.total_leads or 0) + count
            await self.db.flush()

        return count

    async def remove_lead(self, campaign_id: uuid.UUID, lead_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(CampaignLead).where(
                CampaignLead.campaign_id == campaign_id,
                CampaignLead.lead_id == lead_id,
                CampaignLead.tenant_id == self.tenant_id,
            )
        )
        cl = result.scalar_one_or_none()
        if cl:
            await self.db.delete(cl)
            await self.db.flush()

    async def get_campaign_report(self, campaign_id: uuid.UUID):
        """Build a comprehensive campaign report with full per-lead email chains."""
        from app.models.campaign import Message, Reply, SenderAccount
        from app.models.lead import Lead, Contact, Company
        from app.config import get_settings as _get_settings
        from app.schemas.campaign import (
            CampaignReport, CampaignReportSequenceStep,
            ReportLead, ReportMessage, ReportReply,
        )

        # ── Campaign ─────────────────────────────────────────────
        result = await self.db.execute(
            select(Campaign).where(
                Campaign.id == campaign_id,
                Campaign.tenant_id == self.tenant_id,
            )
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            return None

        settings_cfg = _get_settings()
        snap = (campaign.settings or {}).get("test_mode_snapshot", {})
        test_mode_enabled = bool(snap.get("enabled", False))
        test_emails = [e["email"] for e in snap.get("emails", []) if e.get("enabled")]

        # ── Sender info ──────────────────────────────────────────
        from_email: str | None = None
        from_name: str | None = None
        if campaign.sender_account_id:
            sa_res = await self.db.execute(
                select(SenderAccount).where(SenderAccount.id == campaign.sender_account_id)
            )
            sa = sa_res.scalar_one_or_none()
            if sa:
                from_email = sa.email
                from_name = sa.display_name
        if not from_email:
            from_email = str(settings_cfg.sendgrid_from_email or settings_cfg.email_default_from or "")
            from_name = settings_cfg.email_default_from_name or ""

        # ── Campaign leads ────────────────────────────────────────
        cl_result = await self.db.execute(
            select(CampaignLead).where(
                CampaignLead.campaign_id == campaign_id,
                CampaignLead.tenant_id == self.tenant_id,
            ).order_by(CampaignLead.created_at)
        )
        campaign_leads = cl_result.scalars().all()
        lead_ids = [cl.lead_id for cl in campaign_leads]

        # ── Leads + Contacts + Companies ──────────────────────────
        lead_map: dict[uuid.UUID, Lead] = {}
        contact_map: dict[uuid.UUID, Contact] = {}
        company_map: dict[uuid.UUID, Company] = {}
        if lead_ids:
            leads_res = await self.db.execute(select(Lead).where(Lead.id.in_(lead_ids)))
            leads_list = leads_res.scalars().all()
            lead_map = {l.id: l for l in leads_list}

            contact_ids = [l.contact_id for l in leads_list if l.contact_id]
            company_ids = [l.company_id for l in leads_list if l.company_id]
            if contact_ids:
                c_res = await self.db.execute(select(Contact).where(Contact.id.in_(contact_ids)))
                contact_map = {c.id: c for c in c_res.scalars().all()}
            if company_ids:
                co_res = await self.db.execute(select(Company).where(Company.id.in_(company_ids)))
                company_map = {co.id: co for co in co_res.scalars().all()}

        # ── Messages for this campaign ────────────────────────────
        msg_result = await self.db.execute(
            select(Message).where(
                Message.campaign_id == campaign_id,
                Message.tenant_id == self.tenant_id,
            ).order_by(Message.created_at)
        )
        all_messages = msg_result.scalars().all()
        # Group by lead_id
        msgs_by_lead: dict[uuid.UUID, list[Message]] = {}
        for m in all_messages:
            msgs_by_lead.setdefault(m.lead_id, []).append(m)

        # ── Replies keyed by original message_id ──────────────────
        msg_ids = [m.id for m in all_messages]
        replies_by_msg: dict[uuid.UUID, list[Reply]] = {}
        if msg_ids:
            rep_result = await self.db.execute(
                select(Reply).where(
                    Reply.message_id.in_(msg_ids),
                    Reply.tenant_id == self.tenant_id,
                ).order_by(Reply.created_at)
            )
            for r in rep_result.scalars().all():
                replies_by_msg.setdefault(r.message_id, []).append(r)

        # ── Outbound responses we sent (direction=outbound, thread context) ──
        # These are Message rows with direction='outbound' whose thread_id matches
        # a reply's thread context – we identify them by sequence_step=None and
        # same lead_id created after a reply.
        # Simpler: look up Message rows that were sent as manual replies
        # (direction='outbound', campaign_id=None or same, after a reply's created_at)
        # We'll store response body on the Reply using responded_at + suggested_response
        # as a proxy (the route handler already sets responded_at on the Reply model).
        # For full response body we look for outbound messages from same thread.
        outbound_resp_map: dict[uuid.UUID, str | None] = {}  # reply.id → response body

        def _step_label(step: int | None) -> str:
            if step is None:
                return "Email"
            if step == 0 or step == 1:
                return "Initial"
            return f"Follow-up {step - 1}"

        # ── Sequence steps ────────────────────────────────────────
        raw_sequence = campaign.sequence or []
        sequence_steps = []
        for s in raw_sequence:
            if isinstance(s, dict):
                sequence_steps.append(CampaignReportSequenceStep(
                    step=s.get("step", 0),
                    delay_days=s.get("delay_days", 0),
                    channel=s.get("channel", "email"),
                    subject_template=s.get("subject_template"),
                    ai_generate=s.get("ai_generate", True),
                ))

        # ── Build leads list ──────────────────────────────────────
        report_leads = []
        cl_status_map = {cl.lead_id: cl.status for cl in campaign_leads}

        for lead_id in lead_ids:
            lead = lead_map.get(lead_id)
            contact = contact_map.get(lead.contact_id) if lead and lead.contact_id else None
            company = company_map.get(lead.company_id) if lead and lead.company_id else None

            effective_email: str | None = None
            if test_mode_enabled and test_emails:
                effective_email = test_emails[0]

            report_messages = []
            for m in msgs_by_lead.get(lead_id, []):
                report_replies = []
                for r in replies_by_msg.get(m.id, []):
                    report_replies.append(ReportReply(
                        id=r.id,
                        received_at=r.created_at,
                        subject=r.subject,
                        body_text=r.body_text,
                        body_html=r.body_html,
                        intent=r.intent,
                        sentiment=r.sentiment,
                        responded_at=r.responded_at,
                        response_body=r.suggested_response if r.responded_at else None,
                    ))
                report_messages.append(ReportMessage(
                    id=m.id,
                    sequence_step=m.sequence_step,
                    step_label=_step_label(m.sequence_step),
                    subject=m.subject,
                    body_html=m.body_html,
                    body_text=m.body_text,
                    status=m.status,
                    sent_at=m.sent_at,
                    ai_generated=m.ai_generated,
                    replies=report_replies,
                ))

            report_leads.append(ReportLead(
                lead_id=lead_id,
                name=f"{contact.first_name} {contact.last_name}".strip() if contact else None,
                email=contact.email if contact else None,
                effective_email=effective_email,
                company=company.name if company else None,
                title=contact.title if contact else None,
                campaign_status=cl_status_map.get(lead_id, "pending"),
                messages=report_messages,
            ))

        # Live counts
        sent_count = sum(1 for m in all_messages if m.status in ("sent", "delivered"))

        return CampaignReport(
            id=campaign.id,
            name=campaign.name,
            description=campaign.description,
            status=campaign.status,
            campaign_type=campaign.campaign_type,
            vertical=campaign.vertical,
            test_mode_enabled=test_mode_enabled,
            test_emails=test_emails,
            from_email=from_email,
            from_name=from_name,
            created_at=campaign.created_at,
            launched_at=campaign.launched_at,
            completed_at=campaign.completed_at,
            total_leads=len(lead_ids),
            sent_count=sent_count,
            open_count=campaign.open_count,
            reply_count=campaign.reply_count,
            bounce_count=campaign.bounce_count,
            sequence=sequence_steps,
            leads=report_leads,
        )
