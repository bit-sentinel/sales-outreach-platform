"""
E2E Outreach Automation Loop Tasks.

Beat schedule (registered in celery_app.py):
  - run_automation_loop       daily at configured UTC hour, Mon–Thu only
  - run_health_monitor        every 4 hours
  - run_performance_analysis  every Monday at 08:00 UTC
  - draft_reply_response      triggered ad-hoc when an interested reply is ingested
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


def _make_session_factory():
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


def _add_business_days(start_dt: datetime, days: int) -> datetime:
    """Skip Fri/Sat/Sun when adding days."""
    result = start_dt
    added = 0
    while added < days:
        result += timedelta(days=1)
        if result.weekday() < 4:  # Mon=0 … Thu=3
            added += 1
    return result


def _is_valid_send_window() -> bool:
    """Return True if now is Mon–Thu and between 08:00–17:00 UTC (covers US/EU business hours)."""
    now = datetime.now(timezone.utc)
    return now.weekday() < 4 and 8 <= now.hour < 17


# ── Main Loop ────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=1, default_retry_delay=300, name="app.tasks.orchestrator_tasks.run_automation_loop")
def run_automation_loop(self):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_automation_loop_async())
    finally:
        loop.close()


async def _run_automation_loop_async():
    from sqlalchemy import select, update, func as sqlfunc
    from app.models.automation import AutomationConfig
    from app.models.campaign import Campaign, CampaignLead, Message, SenderAccount
    from app.models.lead import Lead, Contact, Company, EnrichmentData, AIInsight, ResearchData
    from app.agents.orchestrator_agent import OutreachOrchestratorAgent
    from app.agents.personalization_agent import PersonalizationAgent
    from app.tasks.personalization_payloads import build_personalization_payload
    from app.tasks.email_tasks import send_email
    from app.config import get_settings

    settings = get_settings()
    session_factory = _make_session_factory()

    async with session_factory() as db:
        # ── 1. Load config ────────────────────────────────────────────────────
        cfg_row = (await db.execute(
            select(AutomationConfig).order_by(AutomationConfig.created_at).limit(1)
        )).scalar_one_or_none()

        if not cfg_row or not cfg_row.loop_enabled:
            logger.info("automation_loop: disabled — skipping")
            return

        tenant_id = cfg_row.tenant_id
        max_leads = cfg_row.max_leads_per_run
        max_acct_daily = cfg_row.max_emails_per_account_daily
        alert_emails = [e.strip() for e in cfg_row.alert_emails.split(",") if e.strip()]

        # ── 2. Check test mode (read from tenant settings) ────────────────────
        from app.models.tenant import Tenant
        tenant_row = (await db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )).scalar_one_or_none()
        tenant_settings = tenant_row.settings or {} if tenant_row else {}
        test_mode_cfg = tenant_settings.get("test_mode", {})
        test_mode_active = test_mode_cfg.get("enabled", False)
        test_mode_emails = [e for e in test_mode_cfg.get("emails", []) if e.get("enabled")]

        # ── 3. Day/time guard — bypass entirely in test mode ─────────────────
        if not test_mode_active and not _is_valid_send_window():
            logger.info("automation_loop: outside send window — skipping")
            return

        # ── 3. Find active sender accounts with quota remaining ───────────────
        active_senders = (await db.execute(
            select(SenderAccount)
            .where(
                SenderAccount.tenant_id == tenant_id,
                SenderAccount.is_active == True,
                SenderAccount.sent_today < sqlfunc.least(SenderAccount.daily_limit, max_acct_daily),
            )
            .order_by(SenderAccount.sent_today)  # pick least-loaded first
        )).scalars().all()

        if not active_senders:
            logger.warning("automation_loop: no sender accounts with quota — aborting")
            _send_alert(alert_emails, "No Sender Accounts Available",
                        "The automation loop ran but found no active sender accounts with quota remaining for today. "
                        "Check Settings → Email Accounts and ensure at least one inbox has capacity.", settings)
            return

        # ── 4. Find candidate leads ───────────────────────────────────────────
        #  - Has a valid contact with email
        #  - Not currently in an active/pending campaign
        #  - Not contacted within the last 30 days
        now_utc = datetime.now(timezone.utc)
        thirty_days_ago = now_utc - timedelta(days=30)

        # Leads that ARE in an active campaign right now
        active_lead_ids_result = await db.execute(
            select(CampaignLead.lead_id)
            .where(
                CampaignLead.tenant_id == tenant_id,
                CampaignLead.status.in_(["active", "pending"]),
            )
        )
        active_lead_ids = {r for r in active_lead_ids_result.scalars().all()}

        # Leads contacted recently (any outbound message in last 30 days)
        recent_lead_ids_result = await db.execute(
            select(Message.lead_id)
            .where(
                Message.tenant_id == tenant_id,
                Message.direction == "outbound",
                Message.sent_at >= thirty_days_ago,
            )
        )
        recent_lead_ids = {r for r in recent_lead_ids_result.scalars().all()}

        excluded_ids = active_lead_ids | recent_lead_ids

        # Candidate leads query — limit 100 to score
        candidate_leads = (await db.execute(
            select(Lead)
            .where(
                Lead.tenant_id == tenant_id,
                Lead.id.notin_(excluded_ids) if excluded_ids else True,
                Lead.contact_id.isnot(None),
            )
            .limit(100)
        )).scalars().all()

        if not candidate_leads:
            logger.info("automation_loop: no candidate leads found — nothing to do")
            _update_run_summary(db, cfg_row, {"status": "no_candidates", "leads_selected": 0})
            await db.commit()
            return

        # ── 5. Build scoring context for each candidate ───────────────────────
        scoring_candidates = []
        lead_context_map: dict[str, dict] = {}  # lead_id → full context

        for lead in candidate_leads:
            contact = (await db.execute(
                select(Contact).where(Contact.id == lead.contact_id)
            )).scalar_one_or_none() if lead.contact_id else None

            if not contact or not contact.email:
                continue

            company = (await db.execute(
                select(Company).where(Company.id == lead.company_id)
            )).scalar_one_or_none() if lead.company_id else None

            insights = (await db.execute(
                select(AIInsight)
                .where(AIInsight.lead_id == lead.id)
                .order_by(AIInsight.created_at.desc())
                .limit(5)
            )).scalars().all()

            research_rows = (await db.execute(
                select(ResearchData)
                .where(ResearchData.lead_id == lead.id)
                .order_by(ResearchData.created_at.desc())
                .limit(3)
            )).scalars().all()

            enrich_rows = (await db.execute(
                select(EnrichmentData)
                .where(EnrichmentData.lead_id == lead.id)
                .order_by(EnrichmentData.created_at.desc())
                .limit(5)
            )).scalars().all()

            # Last contact date
            last_msg = (await db.execute(
                select(Message.sent_at)
                .where(
                    Message.lead_id == lead.id,
                    Message.direction == "outbound",
                    Message.sent_at.isnot(None),
                )
                .order_by(Message.sent_at.desc())
                .limit(1)
            )).scalar_one_or_none()

            days_since = None
            if last_msg:
                days_since = (now_utc - last_msg.replace(tzinfo=timezone.utc)).days

            # Build signal list from insights
            signals = []
            enrichment_summary = ""
            for ins in insights:
                content = ins.content or ""
                if any(kw in content.lower() for kw in ["cvent", "event", "conference", "summit"]):
                    signals.append(content[:120])
                enrichment_summary = (enrichment_summary + " " + content[:60]).strip()

            research_data, enrichment_data = build_personalization_payload(
                insights, research_rows, enrich_rows
            )

            ctx = {
                "lead": lead,
                "contact": contact,
                "company": company,
                "insights": insights,
                "research_data": research_data,
                "enrichment_data": enrichment_data,
                "enrichment_summary": enrichment_summary[:300],
            }
            lead_context_map[str(lead.id)] = ctx

            scoring_candidates.append({
                "lead_id": str(lead.id),
                "contact": {
                    "first_name": contact.first_name,
                    "last_name": contact.last_name,
                    "title": contact.title,
                    "email": contact.email,
                },
                "company": {
                    "name": company.name if company else "",
                    "industry": company.industry if company else "",
                    "employee_count": company.employee_count if company else None,
                },
                "signals": signals,
                "enrichment_summary": enrichment_summary[:300],
                "days_since_last_contact": days_since or "never contacted",
                "campaign_history": "never enrolled" if lead.id not in active_lead_ids else "previously enrolled",
            })

        if not scoring_candidates:
            logger.info("automation_loop: no scorable candidates (missing contact/email)")
            return

        # ── 6. AI lead selection ──────────────────────────────────────────────
        orchestrator = OutreachOrchestratorAgent()
        selected = await orchestrator.score_and_select_leads(scoring_candidates, max_leads=max_leads)

        # Load latest strategy insights to inform copywriting
        from app.models.automation import StrategyInsight
        latest_insights = (await db.execute(
            select(StrategyInsight)
            .where(
                StrategyInsight.tenant_id == tenant_id,
                StrategyInsight.insight_type == "weekly_summary",
            )
            .order_by(StrategyInsight.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        strategy_notes = (latest_insights.summary_text or "") if latest_insights else ""

        # ── 7. For each selected lead: plan → generate → review → schedule ────
        campaigns_created = 0
        emails_queued = 0
        sender_idx = 0  # round-robin across active senders

        for selection in selected:
            lead_id = selection.get("lead_id")
            ctx = lead_context_map.get(lead_id)
            if not ctx:
                continue

            lead = ctx["lead"]
            contact = ctx["contact"]
            company = ctx["company"]
            recommended_angle = selection.get("recommended_angle", "save_time")
            signal_highlights = selection.get("signal_highlights", [])

            try:
                # ── 7a. Plan campaign ──────────────────────────────────────────
                plan = await orchestrator.plan_campaign(
                    lead_id=lead_id,
                    contact={
                        "first_name": contact.first_name,
                        "last_name": contact.last_name,
                        "title": contact.title,
                    },
                    company={
                        "name": company.name if company else "",
                        "industry": company.industry if company else "",
                        "employee_count": company.employee_count if company else None,
                    },
                    enrichment_summary=ctx["enrichment_summary"],
                    signal_highlights=signal_highlights,
                    recommended_angle=recommended_angle,
                )

                steps = plan.get("steps", [])
                if not steps:
                    continue

                # ── 7b. Pick sender account (round-robin least-loaded) ─────────
                sender = active_senders[sender_idx % len(active_senders)]
                sender_idx += 1

                # ── 7c. Build sequence for campaign ───────────────────────────
                # In test mode use delay_days=1 so process_follow_ups fires in 1 min
                sequence = []
                for s in steps:
                    sequence.append({
                        "step": s["step"],
                        "delay_days": 1 if test_mode_active else s.get("delay_days", 0),
                        "angle": s.get("angle", recommended_angle),
                        "condition": "no_reply" if s["step"] > 1 else None,
                    })

                # ── 7d. Create campaign in DB ─────────────────────────────────
                campaign_settings: dict = {
                    "auto_generated": True,
                    "loop_run_at": now_utc.isoformat(),
                }
                if test_mode_active:
                    # Bake the current test mode snapshot so process_campaign_lead
                    # redirects sends to test inboxes and uses minute-scale delays
                    campaign_settings["test_mode_snapshot"] = {
                        "enabled": True,
                        "emails": test_mode_emails,
                    }

                campaign = Campaign(
                    id=uuid.uuid4(),
                    tenant_id=lead.tenant_id,
                    name=plan.get("campaign_name", f"Auto - {contact.first_name} {now_utc.strftime('%b %Y')}"),
                    description=f"Auto-generated by E2E loop. Angle: {recommended_angle}. {plan.get('rationale', '')}",
                    status="draft",
                    campaign_type="outbound",
                    sequence=sequence,
                    settings=campaign_settings,
                    sender_account_id=sender.id,
                    created_by=uuid.UUID("00000000-0000-0000-0000-000000000001"),  # system user
                    total_leads=1,
                )
                db.add(campaign)
                await db.flush()

                # ── 7e. Create campaign lead ───────────────────────────────────
                cl = CampaignLead(
                    id=uuid.uuid4(),
                    tenant_id=lead.tenant_id,
                    campaign_id=campaign.id,
                    lead_id=lead.id,
                    status="active",
                    current_step=0,
                )
                db.add(cl)
                await db.flush()

                # ── 7f. Build sender_info dict ─────────────────────────────────
                sender_info = {
                    "sender_first_name": settings.sender_first_name,
                    "sender_last_name": "",
                    "sender_email": sender.email,
                    "sender_display_name": sender.display_name or "",
                    "sender_calendar_link": settings.sender_calendar_link or "",
                    "company_site_url": settings.company_site_url,
                }

                lead_data_str = str({
                    "first_name": contact.first_name,
                    "last_name": contact.last_name,
                    "email": contact.email,
                    "title": contact.title,
                    "department": contact.department,
                    "location": contact.location,
                    "company": {
                        "name": company.name if company else "",
                        "industry": company.industry if company else "",
                        "employee_count": company.employee_count if company else None,
                        "location": company.location if company else "",
                        "description": company.description if company else "",
                    } if company else {},
                })

                # ── 7g. Generate step-0 email (with QA loop up to 2 retries) ──
                step_cfg = sequence[0]
                personalization_agent = PersonalizationAgent()
                rewrite_notes = ""
                email_content = None
                approved = False

                for attempt in range(3):
                    content = await personalization_agent.run(
                        lead_id=lead_id,
                        tenant_id=str(lead.tenant_id),
                        step_config={**step_cfg, "step": 1, "rewrite_notes": rewrite_notes, "strategy_notes": strategy_notes},
                        lead_data=lead_data_str,
                        research_data=ctx["research_data"],
                        enrichment_data=ctx["enrichment_data"],
                        insights=[{"content": i.content} for i in ctx["insights"]],
                        sender_info=sender_info,
                    )

                    if content.get("parse_error"):
                        logger.warning("automation_loop: parse error on step 0 for lead %s", lead_id)
                        break

                    # QA review
                    review = await orchestrator.review_email(
                        subject=content.get("subject", ""),
                        body_text=content.get("body_text", ""),
                        step=1,
                        contact_first_name=contact.first_name or "",
                        company_name=company.name if company else "",
                    )

                    if review.get("approved", False) or attempt == 2:
                        email_content = content
                        approved = review.get("approved", False)
                        logger.info(
                            "automation_loop: email for %s %s — score=%s approved=%s (attempt %d)",
                            contact.first_name, company.name if company else "", review.get("score"), approved, attempt + 1
                        )
                        break
                    else:
                        rewrite_notes = review.get("rewrite_notes", "")
                        logger.info(
                            "automation_loop: rewriting email for %s — score=%s issues=%s",
                            contact.first_name, review.get("score"), review.get("issues")
                        )

                if not email_content:
                    logger.warning("automation_loop: failed to generate email for lead %s — skipping", lead_id)
                    await db.rollback()
                    continue

                # ── 7h. Schedule the send ──────────────────────────────────────
                if test_mode_active:
                    # In test mode: send immediately (5-second delay so DB commits first)
                    send_eta = now_utc + timedelta(seconds=5)
                else:
                    # Production: respect business hours window
                    send_eta = _next_business_send_time(now_utc)

                msg = Message(
                    id=uuid.uuid4(),
                    tenant_id=lead.tenant_id,
                    campaign_id=campaign.id,
                    lead_id=lead.id,
                    sender_account_id=sender.id,
                    channel="email",
                    direction="outbound",
                    sequence_step=0,
                    subject=email_content.get("subject"),
                    body_html=email_content.get("body_html"),
                    body_text=email_content.get("body_text"),
                    status="queued",
                    ai_generated=True,
                    ai_model="claude",
                    personalization_hooks=email_content.get("personalization_hooks"),
                )
                db.add(msg)
                await db.flush()

                # Dispatch send_email with ETA
                send_email.apply_async(
                    args=[str(msg.id)],
                    eta=send_eta,
                )

                # Update CampaignLead for next step (follow-up will be handled by process_follow_ups)
                next_step_delay = sequence[1]["delay_days"] if len(sequence) > 1 else 3
                cl.current_step = 1
                cl.status = "active"
                if test_mode_active:
                    # delay_days=1 → 1 minute in test mode (process_campaign_lead handles this)
                    cl.next_action_at = send_eta + timedelta(minutes=next_step_delay)
                else:
                    cl.next_action_at = _add_business_days(send_eta, next_step_delay)

                # Activate campaign
                campaign.status = "active"
                campaign.launched_at = now_utc

                await db.flush()
                campaigns_created += 1
                emails_queued += 1
                logger.info(
                    "automation_loop: queued email for %s %s via %s (campaign %s)",
                    contact.first_name, contact.last_name, sender.email, campaign.id
                )

            except Exception as lead_exc:
                logger.error("automation_loop: error processing lead %s: %s", lead_id, lead_exc, exc_info=True)
                await db.rollback()
                continue

        # ── 8. Save run summary ───────────────────────────────────────────────
        summary = {
            "status": "completed",
            "run_at": now_utc.isoformat(),
            "candidates_evaluated": len(scoring_candidates),
            "leads_selected": len(selected),
            "campaigns_created": campaigns_created,
            "emails_queued": emails_queued,
        }
        cfg_row.last_run_at = now_utc
        cfg_row.last_run_summary = summary
        await db.commit()
        logger.info("automation_loop: completed — %s", summary)


def _next_business_send_time(now: datetime) -> datetime:
    """
    Return the next valid send datetime (Mon–Thu, 10:00–16:00 UTC).
    Adds a 30–90 min jitter so emails don't all arrive at the same second.
    """
    import random
    send = now.replace(second=0, microsecond=0)

    # If outside send window, advance to next valid slot
    for _ in range(7):
        if send.weekday() < 4 and 10 <= send.hour < 16:
            break
        if send.weekday() >= 4 or send.hour >= 16:
            # Move to next Mon if Fri/Sat/Sun or after hours
            days_ahead = (7 - send.weekday()) % 7 or 1
            if send.weekday() >= 4:
                days_ahead = (7 - send.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
            send = (send + timedelta(days=days_ahead)).replace(hour=10, minute=0)
        elif send.hour < 10:
            send = send.replace(hour=10, minute=0)

    jitter = random.randint(30, 90)
    return send + timedelta(minutes=jitter)


# ── Health Monitor ────────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=1, name="app.tasks.orchestrator_tasks.run_health_monitor")
def run_health_monitor(self):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_health_monitor_async())
    finally:
        loop.close()


async def _run_health_monitor_async():
    from sqlalchemy import select
    from app.models.automation import AutomationConfig, HealthAlert
    from app.models.campaign import SenderAccount
    from app.config import get_settings

    settings = get_settings()
    session_factory = _make_session_factory()

    async with session_factory() as db:
        cfg = (await db.execute(
            select(AutomationConfig).order_by(AutomationConfig.created_at).limit(1)
        )).scalar_one_or_none()

        tenant_id = cfg.tenant_id if cfg else None
        alert_emails = [e.strip() for e in (cfg.alert_emails if cfg else "snehdeep@launchhouse.events,cto@launchhouse.events").split(",") if e.strip()]

        issues: list[tuple[str, str, str]] = []  # (component, severity, message)

        # ── 1. SendGrid connectivity ──────────────────────────────────────────
        try:
            if settings.sendgrid_api_key:
                from sendgrid import SendGridAPIClient
                sg = SendGridAPIClient(settings.sendgrid_api_key)
                resp = sg.client.mail_settings.get()
                if resp.status_code not in (200, 201):
                    issues.append(("sendgrid", "warning", f"SendGrid API returned status {resp.status_code}"))
            else:
                issues.append(("sendgrid", "critical", "SendGrid API key is not configured"))
        except Exception as e:
            issues.append(("sendgrid", "critical", f"SendGrid API unreachable: {e}"))

        # ── 2. Anthropic API connectivity ─────────────────────────────────────
        try:
            if settings.anthropic_api_key:
                import anthropic
                client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                client.models.list()
            else:
                issues.append(("anthropic", "critical", "Anthropic API key is not configured"))
        except Exception as e:
            issues.append(("anthropic", "critical", f"Anthropic API unreachable: {e}"))

        # ── 3. IMAP connectivity for each sender account ───────────────────────
        if tenant_id:
            senders = (await db.execute(
                select(SenderAccount)
                .where(SenderAccount.tenant_id == tenant_id, SenderAccount.is_active == True, SenderAccount.imap_host.isnot(None))
            )).scalars().all()

            for sender in senders:
                try:
                    import imaplib
                    imap = imaplib.IMAP4_SSL(sender.imap_host, timeout=10)
                    imap.login(sender.imap_user or sender.email, sender.imap_password or "")
                    imap.logout()
                except Exception as e:
                    issues.append(("imap", "warning", f"IMAP failed for {sender.email}: {e}"))

        # ── 4. Record alerts & send notifications ─────────────────────────────
        now_utc = datetime.now(timezone.utc)

        for component, severity, message in issues:
            logger.warning("health_monitor: [%s] %s — %s", severity.upper(), component, message)
            if tenant_id:
                alert = HealthAlert(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    component=component,
                    severity=severity,
                    message=message,
                )
                db.add(alert)

        if issues:
            await db.commit()
            _send_alert(
                alert_emails,
                f"LaunchHouse Outreach — {len(issues)} System Alert(s)",
                "\n".join(f"[{sev.upper()}] {comp}: {msg}" for comp, sev, msg in issues),
                settings,
            )
        else:
            await db.commit()
            logger.info("health_monitor: all systems healthy")


# ── Performance Analyst (Gap 3) ───────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=1, name="app.tasks.orchestrator_tasks.run_performance_analysis")
def run_performance_analysis(self):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_performance_analysis_async())
    finally:
        loop.close()


async def _run_performance_analysis_async():
    from sqlalchemy import select, func as sqlfunc
    from app.models.automation import AutomationConfig, StrategyInsight
    from app.models.campaign import Campaign, Message, Reply, EmailEvent
    from app.agents.orchestrator_agent import OutreachOrchestratorAgent
    from app.config import get_settings

    settings = get_settings()
    session_factory = _make_session_factory()

    async with session_factory() as db:
        cfg = (await db.execute(
            select(AutomationConfig).order_by(AutomationConfig.created_at).limit(1)
        )).scalar_one_or_none()

        if not cfg:
            return

        tenant_id = cfg.tenant_id
        alert_emails = [e.strip() for e in cfg.alert_emails.split(",") if e.strip()]
        now_utc = datetime.now(timezone.utc)
        period_start = now_utc - timedelta(days=30)

        # ── Gather metrics ─────────────────────────────────────────────────────
        total_sent = (await db.execute(
            select(sqlfunc.count(Message.id)).where(
                Message.tenant_id == tenant_id,
                Message.direction == "outbound",
                Message.sent_at >= period_start,
                Message.status.in_(["sent", "delivered"]),
            )
        )).scalar() or 0

        total_opened = (await db.execute(
            select(sqlfunc.count(EmailEvent.id)).where(
                EmailEvent.tenant_id == tenant_id,
                EmailEvent.event_type == "opened",
                EmailEvent.created_at >= period_start,
            )
        )).scalar() or 0

        replies_by_intent = {}
        reply_rows = (await db.execute(
            select(Reply.intent, sqlfunc.count(Reply.id))
            .where(Reply.tenant_id == tenant_id, Reply.created_at >= period_start)
            .group_by(Reply.intent)
        )).all()
        for intent, count in reply_rows:
            replies_by_intent[intent or "unknown"] = count

        positive_replies = sum(
            v for k, v in replies_by_intent.items()
            if k in ("interested", "meeting_request", "question")
        )

        # Per-step performance
        step_stats = {}
        step_rows = (await db.execute(
            select(Message.sequence_step, sqlfunc.count(Message.id))
            .where(
                Message.tenant_id == tenant_id,
                Message.direction == "outbound",
                Message.sent_at >= period_start,
            )
            .group_by(Message.sequence_step)
        )).all()
        for step, count in step_rows:
            step_stats[f"step_{step}_sent"] = count

        performance_data = {
            "period": f"{period_start.date()} to {now_utc.date()}",
            "total_emails_sent": total_sent,
            "total_opens": total_opened,
            "open_rate": f"{(total_opened / total_sent * 100):.1f}%" if total_sent else "0%",
            "positive_replies": positive_replies,
            "positive_reply_rate": f"{(positive_replies / total_sent * 100):.1f}%" if total_sent else "0%",
            "replies_by_intent": replies_by_intent,
            "per_step_stats": step_stats,
        }

        # Load previous insight summaries
        prev_insights = (await db.execute(
            select(StrategyInsight.summary_text)
            .where(
                StrategyInsight.tenant_id == tenant_id,
                StrategyInsight.insight_type == "weekly_summary",
            )
            .order_by(StrategyInsight.created_at.desc())
            .limit(3)
        )).scalars().all()

        # ── Generate insights via AI ───────────────────────────────────────────
        orchestrator = OutreachOrchestratorAgent()
        insights = await orchestrator.generate_weekly_insights(
            performance_data=performance_data,
            previous_insights=[s for s in prev_insights if s],
        )

        # ── Save insight ───────────────────────────────────────────────────────
        insight_row = StrategyInsight(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            insight_type="weekly_summary",
            insight_data={
                "performance": performance_data,
                "insights": insights,
            },
            period_start=period_start,
            period_end=now_utc,
            summary_text=insights.get("summary", ""),
        )
        db.add(insight_row)
        await db.commit()

        # ── Send weekly digest ─────────────────────────────────────────────────
        digest_body = insights.get("email_digest") or insights.get("summary", "No digest available.")
        _send_alert(
            alert_emails,
            f"LaunchHouse Outreach — Weekly Performance Digest ({now_utc.strftime('%b %d, %Y')})",
            digest_body,
            settings,
        )
        logger.info("performance_analysis: completed and digest sent")


# ── Reply Response Drafter (Gap 2) ────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=2, default_retry_delay=30, name="app.tasks.orchestrator_tasks.draft_reply_response")
def draft_reply_response(self, reply_id: str):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_draft_reply_response_async(reply_id))
    finally:
        loop.close()


async def _draft_reply_response_async(reply_id: str):
    from sqlalchemy import select
    from app.models.campaign import Reply, Message
    from app.models.lead import Lead, Contact, Company
    from app.agents.orchestrator_agent import OutreachOrchestratorAgent
    from app.config import get_settings

    settings = get_settings()
    session_factory = _make_session_factory()

    async with session_factory() as db:
        reply = (await db.execute(
            select(Reply).where(Reply.id == uuid.UUID(reply_id))
        )).scalar_one_or_none()

        if not reply:
            logger.warning("draft_reply_response: reply %s not found", reply_id)
            return

        if reply.intent not in ("interested", "meeting_request", "question"):
            return

        # Fetch original message
        original_msg = (await db.execute(
            select(Message).where(Message.id == reply.message_id)
        )).scalar_one_or_none()

        lead = (await db.execute(
            select(Lead).where(Lead.id == reply.lead_id)
        )).scalar_one_or_none()

        contact = (await db.execute(
            select(Contact).where(Contact.id == lead.contact_id)
        )).scalar_one_or_none() if lead and lead.contact_id else None

        company = (await db.execute(
            select(Company).where(Company.id == lead.company_id)
        )).scalar_one_or_none() if lead and lead.company_id else None

        orchestrator = OutreachOrchestratorAgent()
        ai_analysis = reply.ai_analysis or {}

        draft = await orchestrator.draft_reply_response(
            original_subject=original_msg.subject or "" if original_msg else "",
            original_body=original_msg.body_text or "" if original_msg else "",
            reply_body=reply.body_text or "",
            contact_first_name=contact.first_name if contact else "",
            contact_last_name=contact.last_name if contact else "",
            company_name=company.name if company else "",
            intent=reply.intent or "interested",
            questions=ai_analysis.get("questions", []),
            sender_name=settings.sender_first_name,
        )

        # Store the polished draft in suggested_response
        reply.suggested_response = draft.get("body_text", "")
        await db.commit()

        logger.info(
            "draft_reply_response: drafted response for reply %s (intent=%s)",
            reply_id, reply.intent
        )


# ── Helper: send alert email via SendGrid ────────────────────────────────────

def _send_alert(recipients: list[str], subject: str, body: str, settings) -> None:
    """Best-effort alert via SendGrid. Non-fatal if it fails."""
    try:
        if not settings.sendgrid_api_key or not recipients:
            return
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        from_email = settings.sendgrid_from_email or settings.email_default_from
        for recipient in recipients:
            msg = Mail(
                from_email=from_email,
                to_emails=recipient,
                subject=f"[LaunchHouse Outreach] {subject}",
                plain_text_content=body,
            )
            sg = SendGridAPIClient(settings.sendgrid_api_key)
            sg.send(msg)
        logger.info("_send_alert: sent to %s", recipients)
    except Exception as e:
        logger.warning("_send_alert: failed to send alert email: %s", e)
