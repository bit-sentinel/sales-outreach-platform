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
