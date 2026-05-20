"""
Campaign execution Celery tasks – process follow-ups, execute sequences.
"""

import asyncio

from app.celery_app import celery_app
from app.tasks.personalization_payloads import build_personalization_payload


def _make_session_factory():
    """Create a fresh engine + session factory for this OS process / event loop."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import get_settings
    settings = get_settings()
    engine = create_async_engine(
        str(settings.database_url),
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def execute_campaign(self, campaign_id: str):
    """Launch campaign – generate personalized emails for all leads in the campaign."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_execute_campaign_async(campaign_id))
    finally:
        loop.close()


async def _execute_campaign_async(campaign_id: str):
    import uuid
    from sqlalchemy import select
    from app.models.campaign import Campaign, CampaignLead

    session_factory = _make_session_factory()
    async with session_factory() as db:
        result = await db.execute(
            select(CampaignLead).where(
                CampaignLead.campaign_id == uuid.UUID(campaign_id),
                CampaignLead.status == "pending",
            )
        )
        campaign_leads = result.scalars().all()

        for cl in campaign_leads:
            # Dispatch individual lead processing
            process_campaign_lead.delay(str(cl.id))


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_campaign_lead(self, campaign_lead_id: str):
    """Process a single lead in a campaign – generate and schedule email."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_process_campaign_lead_async(campaign_lead_id))
    finally:
        loop.close()


async def _process_campaign_lead_async(campaign_lead_id: str):
    import uuid
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.models.campaign import Campaign, CampaignLead, Message
    from app.models.lead import Lead, Contact, Company

    session_factory = _make_session_factory()
    async with session_factory() as db:
        result = await db.execute(
            select(CampaignLead).where(CampaignLead.id == uuid.UUID(campaign_lead_id))
        )
        cl = result.scalar_one_or_none()
        if not cl:
            return

        # Get campaign sequence
        campaign_result = await db.execute(
            select(Campaign).where(Campaign.id == cl.campaign_id)
        )
        campaign = campaign_result.scalar_one_or_none()
        if not campaign or campaign.status != "active":
            return

        sequence = campaign.sequence or []
        current_step = cl.current_step or 0

        if current_step >= len(sequence):
            cl.status = "completed"
            await db.commit()
            return

        step = sequence[current_step]

        # Check conditional logic: skip step if condition is "no_reply" and a reply exists
        # Scope to THIS campaign only — replies from other campaigns must not affect this sequence.
        if step.get("condition") == "no_reply" and current_step > 0:
            from app.models.campaign import Reply
            reply_result = await db.execute(
                select(Reply)
                .join(Message, Reply.message_id == Message.id)
                .where(
                    Reply.lead_id == cl.lead_id,
                    Message.campaign_id == cl.campaign_id,
                )
                .limit(1)
            )
            if reply_result.scalar_one_or_none():
                # Lead replied within this campaign – mark completed, skip step
                cl.status = "completed"
                await db.commit()
                return

        # Fetch lead + contact + company for personalization context
        lead_result = await db.execute(select(Lead).where(Lead.id == cl.lead_id))
        lead = lead_result.scalar_one_or_none()

        contact = None
        company = None
        if lead:
            if lead.contact_id:
                contact_result = await db.execute(select(Contact).where(Contact.id == lead.contact_id))
                contact = contact_result.scalar_one_or_none()
            if lead.company_id:
                company_result = await db.execute(select(Company).where(Company.id == lead.company_id))
                company = company_result.scalar_one_or_none()

        lead_data = None
        if contact:
            lead_data = {
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "email": contact.email,
                "title": contact.title,
                "department": contact.department,
                "location": contact.location,
            }
        if company:
            company_data = {
                "name": company.name,
                "industry": company.industry,
                "employee_count": company.employee_count,
                "location": company.location,
                "description": company.description,
            }
            if lead_data:
                lead_data["company"] = company_data
            else:
                lead_data = {"company": company_data}

        # Pull enrichment data for this lead (events, news, signals)
        enrichment_data = None
        research_data = None
        if lead:
            from app.models.lead import AIInsight, ResearchData as ResearchDataModel, EnrichmentData
            insight_result = await db.execute(
                select(AIInsight).where(AIInsight.lead_id == lead.id).order_by(AIInsight.created_at.desc()).limit(10)
            )
            insights_rows = insight_result.scalars().all()
            # Also pull raw research data (events, news found by research agent)
            research_result = await db.execute(
                select(ResearchDataModel).where(ResearchDataModel.lead_id == lead.id).order_by(ResearchDataModel.created_at.desc()).limit(5)
            )
            research_rows = research_result.scalars().all()
            # Pull structured enrichment data
            enrich_result = await db.execute(
                select(EnrichmentData).where(EnrichmentData.lead_id == lead.id).order_by(EnrichmentData.created_at.desc()).limit(10)
            )
            enrich_rows = enrich_result.scalars().all()
            research_data, enrichment_data = build_personalization_payload(
                insights_rows,
                research_rows,
                enrich_rows,
            )

        # Sender info — default from settings, override from SenderAccount if linked
        from app.config import get_settings as _get_settings
        _settings = _get_settings()
        sender_info = {
            "sender_first_name": _settings.sender_first_name,
            "sender_last_name": "",
            "sender_email": str(_settings.sendgrid_from_email or _settings.email_default_from),
            "sender_calendar_link": _settings.sender_calendar_link,
            "company_site_url": _settings.company_site_url,
        }
        if campaign.sender_account_id:
            from app.models.campaign import SenderAccount
            sender_result = await db.execute(
                select(SenderAccount).where(SenderAccount.id == campaign.sender_account_id)
            )
            sender = sender_result.scalar_one_or_none()
            if sender:
                sender_info = {
                    "sender_first_name": _settings.sender_first_name,
                    "sender_last_name": "",
                    "sender_email": sender.email,
                    "sender_calendar_link": _settings.sender_calendar_link or "",
                    "company_site_url": _settings.company_site_url,
                }

        # Find previous email (subject + body) so the follow-up can reference what was actually said
        previous_email_subject = None
        previous_email_body = None
        if current_step > 0:
            prev_result = await db.execute(
                select(Message).where(
                    Message.lead_id == cl.lead_id,
                    Message.campaign_id == campaign.id,
                    Message.direction == "outbound",
                    Message.sequence_step == current_step - 1,
                ).order_by(Message.created_at.desc()).limit(1)
            )
            prev_msg = prev_result.scalar_one_or_none()
            if prev_msg:
                previous_email_subject = prev_msg.subject
                previous_email_body = prev_msg.body_text

        # Detect if lead has replied *within this campaign* to route to reply handlers.
        # Must be scoped to this campaign — replies from other campaigns must not affect this sequence.
        reply_intent = None
        from app.models.campaign import Reply
        reply_result = await db.execute(
            select(Reply)
            .join(Message, Reply.message_id == Message.id)
            .where(
                Reply.lead_id == cl.lead_id,
                Message.campaign_id == cl.campaign_id,
            )
            .order_by(Reply.created_at.desc())
            .limit(1)
        )
        latest_reply = reply_result.scalar_one_or_none()
        if latest_reply:
            reply_intent = latest_reply.intent

        # For step 0: check if the lead has v3 outreach intelligence (Outreach tab).
        # If so, use that pre-generated subject + body directly — it's already optimised
        # for this specific lead. Fall back to PersonalizationAgent if not available.
        email_content = None
        if current_step == 0 and contact and contact.email:
            from app.agents.v3.cache import AgentResultCache
            from app.agents.v3.contracts import CacheScope, SignalType
            _arc = AgentResultCache(session_factory=_make_session_factory())
            _outreach_r = await _arc.get(SignalType.OUTREACH, CacheScope.CONTACT, contact.email)
            if _outreach_r and _outreach_r.is_usable():
                _pl = _outreach_r.payload or {}
                _subj = _pl.get("subject_line", "").strip()
                _body = _pl.get("email_body", "").strip()
                if _subj and _body:
                    from app.tools.email_renderer import render_email_html, render_email_plain
                    _html = render_email_html(
                        body_text=_body,
                        sender_name=sender_info.get("sender_first_name", ""),
                        sender_company="LaunchHouse Events",
                        sender_site_url=sender_info.get("company_site_url", "https://launchhouse.events/"),
                        sender_calendar_link=sender_info.get("sender_calendar_link") or "",
                    )
                    _plain = render_email_plain(
                        body_text=_body,
                        sender_name=sender_info.get("sender_first_name", ""),
                        sender_site_url=sender_info.get("company_site_url", "https://launchhouse.events/"),
                        sender_calendar_link=sender_info.get("sender_calendar_link") or "",
                    )
                    email_content = {
                        "subject": _subj,
                        "body_html": _html,
                        "body_text": _plain,
                        "personalization_hooks": ["source: v3_outreach_intelligence"],
                        "template_used": "v3 outreach intelligence",
                        "tone": "professional",
                    }

        if email_content is None:
            # Generate personalized email via AI using the full template playbook
            from app.agents.personalization_agent import PersonalizationAgent
            agent = PersonalizationAgent()
            email_content = await agent.run(
                lead_id=str(cl.lead_id),
                tenant_id=str(cl.tenant_id),
                step_config=step,
                lead_data=str(lead_data) if lead_data else None,
                research_data=research_data,
                sender_info=str(sender_info) if sender_info else None,
                previous_email_subject=previous_email_subject,
                previous_email_body=previous_email_body,
                reply_intent=reply_intent,
            )

        # ── Test mode: round-robin email override ─────────────────────────────
        # Use the snapshot captured at launch time — immune to mid-campaign toggles.
        # Writes the override into cl.personalization_data so send_email can read it.
        try:
            _tm = (campaign.settings or {}).get("test_mode_snapshot", {})
            if _tm.get("enabled"):
                _enabled = [e["email"] for e in _tm.get("emails", []) if e.get("enabled")]
                if _enabled:
                    _all_ids = (await db.execute(
                        select(CampaignLead.id)
                        .where(CampaignLead.campaign_id == campaign.id)
                        .order_by(CampaignLead.created_at)
                    )).scalars().all()
                    try:
                        _idx = list(_all_ids).index(cl.id)
                    except ValueError:
                        _idx = 0
                    _test_email = _enabled[_idx % len(_enabled)]
                    _pd = dict(cl.personalization_data or {})
                    _pd["test_email_override"] = _test_email
                    cl.personalization_data = _pd
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(cl, "personalization_data")
        except Exception as _tm_err:
            import logging as _log
            import traceback as _tb
            _log.getLogger(__name__).error("Test mode override failed: %s\n%s", _tm_err, _tb.format_exc())

        # Create message record as DRAFT – user reviews before sending
        hooks = email_content.get("personalization_hooks") or []
        template_used = email_content.get("template_used")
        if template_used:
            hooks = list(hooks) + [f"template: {template_used}"]

        message = Message(
            tenant_id=cl.tenant_id,
            campaign_id=campaign.id,
            lead_id=cl.lead_id,
            sender_account_id=campaign.sender_account_id,
            channel="email",
            direction="outbound",
            sequence_step=current_step,
            subject=email_content.get("subject", ""),
            body_html=email_content.get("body_html", ""),
            body_text=email_content.get("body_text", ""),
            status="draft",
            ai_generated=True,
            personalization_hooks=hooks,
        )
        db.add(message)

        # Advance campaign lead step
        cl.status = "active"
        cl.current_step = current_step + 1

        # Schedule FollowUp for the NEXT step if one exists
        next_step_idx = current_step + 1
        if next_step_idx < len(sequence):
            from datetime import timedelta
            next_delay = sequence[next_step_idx].get("delay_days", 1)
            _test_mode_active = (campaign.settings or {}).get("test_mode_snapshot", {}).get("enabled", False)
            if _test_mode_active:
                delta = timedelta(minutes=max(next_delay, 1))
            else:
                delta = timedelta(days=max(next_delay, 1))
            from app.models.campaign import FollowUp
            follow_up = FollowUp(
                tenant_id=cl.tenant_id,
                campaign_lead_id=cl.id,
                step_number=next_step_idx,
                scheduled_at=datetime.now(timezone.utc) + delta,
                status="scheduled",
            )
            db.add(follow_up)

        await db.flush()
        message_id_str = str(message.id)
        await db.commit()

        # Mark the FollowUp record as sent now that the message was committed.
        # Only follow-up steps (current_step > 0) have a FollowUp row.
        if current_step > 0:
            from app.models.campaign import FollowUp
            from sqlalchemy import update as _update
            await db.execute(
                _update(FollowUp)
                .where(
                    FollowUp.campaign_lead_id == cl.id,
                    FollowUp.step_number == current_step,
                    FollowUp.status == "processing",
                )
                .values(status="sent", sent_message_id=message.id)
            )
            await db.commit()

        # All emails remain as drafts regardless of step — manual send required


@celery_app.task
def process_follow_ups():
    """Periodic task – find and send due follow-ups."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_process_follow_ups_async())
    finally:
        loop.close()


async def _process_follow_ups_async():
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select, update as _update
    from app.models.campaign import FollowUp

    session_factory = _make_session_factory()
    async with session_factory() as db:
        now = datetime.now(timezone.utc)

        # Reset follow-ups stuck in "processing" for over an hour back to "scheduled"
        # so they are retried. This handles task crashes or mid-flight failures.
        # Use updated_at (when status was last changed) not scheduled_at, so we
        # don't reset a follow-up that is currently being processed.
        stale_cutoff = now - timedelta(hours=1)
        await db.execute(
            _update(FollowUp)
            .where(
                FollowUp.status == "processing",
                FollowUp.updated_at <= stale_cutoff,
            )
            .values(status="scheduled")
        )
        await db.commit()

        result = await db.execute(
            select(FollowUp).where(
                FollowUp.status == "scheduled",
                FollowUp.scheduled_at <= now,
            ).limit(100)
        )
        follow_ups = result.scalars().all()

        for fu in follow_ups:
            fu.status = "processing"
            await db.commit()
            process_campaign_lead.delay(str(fu.campaign_lead_id))
