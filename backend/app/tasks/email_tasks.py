"""
Email delivery and tracking Celery tasks.
"""

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


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


def _check_message_test_mode(message_id: str) -> bool:
    """Synchronous check: return True if the message belongs to a test-mode campaign."""
    try:
        import asyncio, uuid
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy import select
        from app.config import get_settings
        from app.models.campaign import Message, Campaign

        async def _check():
            settings = get_settings()
            engine = create_async_engine(str(settings.database_url), pool_size=2)
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with factory() as db:
                msg = (await db.execute(
                    select(Message).where(Message.id == uuid.UUID(message_id))
                )).scalar_one_or_none()
                if not msg or not msg.campaign_id:
                    return False
                campaign = (await db.execute(
                    select(Campaign).where(Campaign.id == msg.campaign_id)
                )).scalar_one_or_none()
                if not campaign:
                    return False
                return bool((campaign.settings or {}).get("test_mode_snapshot", {}).get("enabled", False))

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_check())
        finally:
            loop.close()
    except Exception:
        return False


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email(self, message_id: str):
    """Send a single email via the configured provider.

    Waits a random 5-10 minute delay before sending to mimic human pacing
    and avoid triggering spam filters on burst sends.
    """
    import random
    import time

    # Skip the pacing delay when the campaign is in test mode (instant delivery for testing)
    _is_test = _check_message_test_mode(message_id)
    if _is_test:
        logger.info("send_email: test mode — skipping pacing delay for message %s", message_id)
    else:
        delay_seconds = random.randint(5, 10) * 60
        logger.info(
            "send_email: queued message %s — waiting %d min before sending",
            message_id,
            delay_seconds // 60,
        )
        time.sleep(delay_seconds)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_send_email_async(message_id))
    finally:
        loop.close()


async def _send_email_async(message_id: str):
    import uuid
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.models.campaign import Message, SenderAccount, EmailEvent
    from app.models.lead import Lead, Contact
    from app.events import get_event_bus
    from app.config import get_settings

    settings = get_settings()
    session_factory = _make_session_factory()

    async with session_factory() as db:
        result = await db.execute(
            select(Message).where(Message.id == uuid.UUID(message_id))
        )
        message = result.scalar_one_or_none()
        if not message or message.status not in ("draft", "queued"):
            return

        message.status = "sending"
        await db.commit()

        try:
            # Resolve recipient email.
            # Priority: test_email_override on CampaignLead → real Contact email.
            to_email: str | None = None

            if message.campaign_id:
                from app.models.campaign import CampaignLead
                cl_result = await db.execute(
                    select(CampaignLead).where(
                        CampaignLead.campaign_id == message.campaign_id,
                        CampaignLead.lead_id == message.lead_id,
                    )
                )
                cl = cl_result.scalar_one_or_none()
                if cl:
                    to_email = (cl.personalization_data or {}).get("test_email_override") or None

            if not to_email:
                lead_result = await db.execute(select(Lead).where(Lead.id == message.lead_id))
                lead = lead_result.scalar_one_or_none()
                if lead and lead.contact_id:
                    contact_result = await db.execute(select(Contact).where(Contact.id == lead.contact_id))
                    contact = contact_result.scalar_one_or_none()
                    if contact:
                        to_email = contact.email

            if not to_email:
                raise ValueError("No recipient email found for lead")

            # Get sender account — prefer SENDGRID_FROM_EMAIL env override
            from_email = settings.sendgrid_from_email or settings.email_default_from
            from_name = settings.email_default_from_name
            sender = None
            if message.sender_account_id:
                sender_result = await db.execute(
                    select(SenderAccount).where(SenderAccount.id == message.sender_account_id)
                )
                sender = sender_result.scalar_one_or_none()
                if sender:
                    from_email = sender.email
                    from_name = settings.email_default_from_name or "LaunchHouse Events"

            # ── Send via SendGrid ───────────────────────────────────────────────
            external_id: str | None = None
            if settings.sendgrid_api_key:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail, To, From, Content

                subject = message.subject or ""
                if not subject and message.sequence_step and message.sequence_step > 0 and message.campaign_id:
                    # No subject on a follow-up — find previous step's subject as fallback
                    from app.models.campaign import Message as Msg
                    prev = (await db.execute(
                        select(Msg).where(
                            Msg.campaign_id == message.campaign_id,
                            Msg.lead_id == message.lead_id,
                            Msg.sequence_step == message.sequence_step - 1,
                            Msg.subject.isnot(None),
                        )
                    )).scalar_one_or_none()
                    if prev and prev.subject:
                        subject = f"Re: {prev.subject}"
                subject = subject or "(no subject)"

                sg_message = Mail(
                    from_email=From(from_email, from_name),
                    to_emails=To(to_email),
                    subject=subject,
                )
                if message.body_html:
                    sg_message.content = [
                        Content("text/plain", message.body_text or ""),
                        Content("text/html", message.body_html),
                    ]
                else:
                    sg_message.content = [Content("text/plain", message.body_text or "")]

                sg = SendGridAPIClient(settings.sendgrid_api_key)
                try:
                    response = sg.send(sg_message)
                except Exception as sg_err:
                    body = getattr(getattr(sg_err, 'body', None), 'decode', lambda e='utf-8': str(getattr(sg_err, 'body', '')))('utf-8') if hasattr(getattr(sg_err, 'body', None), 'decode') else str(getattr(sg_err, 'body', sg_err))
                    logger.error("SendGrid error %s body: %s", type(sg_err).__name__, body)
                    raise
                external_id = response.headers.get("X-Message-Id") or f"sg-{uuid.uuid4()}"
                logger.info(
                    "SendGrid sent message %s → %s (status %s)",
                    message_id,
                    to_email,
                    response.status_code,
                )
            else:
                # No provider configured – log and mark as sent anyway for local dev
                logger.warning(
                    "No SENDGRID_API_KEY set – email NOT delivered. Would have sent to %s: %s",
                    to_email,
                    message.subject,
                )
                external_id = f"mock-{uuid.uuid4()}"

            message.status = "sent"
            message.sent_at = datetime.now(timezone.utc)
            message.message_id = external_id

            # Record email event
            event = EmailEvent(
                tenant_id=message.tenant_id,
                message_id=message.id,
                event_type="sent",
            )
            db.add(event)

            # Update sender daily count
            if sender:
                sender.sent_today = (sender.sent_today or 0) + 1

            # Increment campaign sent_count
            if message.campaign_id:
                from app.models.campaign import Campaign
                from sqlalchemy import update
                await db.execute(
                    update(Campaign)
                    .where(Campaign.id == message.campaign_id)
                    .values(sent_count=Campaign.sent_count + 1)
                )

            await db.commit()

            # Emit event – best-effort, never crash the task over a bus failure.
            # Always create a fresh EventBus so its Redis client is bound to the
            # current event loop (the singleton returned by get_event_bus() may
            # have been created in a previous task's now-closed loop).
            try:
                from app.events import EventBus
                bus = EventBus()
                await bus.publish(
                    "email_events",
                    "email.sent",
                    {"message_id": message_id, "lead_id": str(message.lead_id)},
                    tenant_id=str(message.tenant_id),
                )
            except Exception as bus_err:
                logger.warning("Failed to publish email.sent event (non-fatal): %s", bus_err)

        except Exception as e:
            logger.error("Failed to send message %s: %s", message_id, e)
            message.status = "failed"
            message.error_message = str(e)[:1000]
            await db.commit()
            raise


@celery_app.task
def check_replies():
    """Periodic task – check for new email replies across all sender accounts."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_check_replies_async())
    finally:
        loop.close()


async def _check_replies_async():
    import imaplib
    import email as email_lib
    import re
    from datetime import datetime, timedelta, timezone
    from email.utils import parsedate_to_datetime
    from email.header import decode_header as _decode_header
    from sqlalchemy import select, update
    from app.models.campaign import Message, Reply, Campaign, CampaignLead, SenderAccount
    from app.models.lead import Lead, Contact
    from app.models.tenant import Tenant
    from app.config import get_settings

    settings = get_settings()
    session_factory = _make_session_factory()

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _header_str(raw) -> str:
        parts = _decode_header(raw or "")
        out = []
        for part, enc in parts:
            if isinstance(part, bytes):
                out.append(part.decode(enc or "utf-8", errors="replace"))
            else:
                out.append(str(part))
        return "".join(out)

    def _body_text(msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        return ""

    async with session_factory() as db:
        # ── Build shared lookup tables (built once, used by all inboxes) ─────

        lead_rows = (await db.execute(select(Lead))).scalars().all()
        lead_by_id: dict = {l.id: l for l in lead_rows}
        contact_ids = [l.contact_id for l in lead_rows if l.contact_id]
        contacts = {}
        if contact_ids:
            c_rows = (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
            contacts = {c.id: c for c in c_rows}
        email_to_lead: dict[str, Lead] = {}
        for lead in lead_rows:
            if lead.contact_id and lead.contact_id in contacts:
                c = contacts[lead.contact_id]
                if c.email:
                    email_to_lead[c.email.lower()] = lead

        test_email_set: set[str] = set()
        try:
            all_tenants = (await db.execute(select(Tenant))).scalars().all()
            for t in all_tenants:
                if (t.settings or {}).get("test_mode", {}).get("enabled"):
                    for e in (t.settings or {}).get("test_mode", {}).get("emails", []):
                        if e.get("enabled") and e.get("email"):
                            test_email_set.add(e["email"].lower())
        except Exception as _te_err:
            logger.warning("check_replies: test mode email set build failed (non-fatal): %s", _te_err)

        msg_rows = (await db.execute(
            select(Message).where(Message.status == "sent", Message.direction == "outbound")
        )).scalars().all()
        subject_to_message: dict[str, Message] = {}
        for m in msg_rows:
            if m.subject:
                subject_to_message[m.subject.lower().strip()] = m

        # ── Build list of IMAP accounts to poll ───────────────────────────────
        # All active SenderAccounts with IMAP credentials configured in DB
        sa_rows = (await db.execute(
            select(SenderAccount).where(
                SenderAccount.imap_user.isnot(None),
                SenderAccount.imap_password.isnot(None),
                SenderAccount.is_active == True,  # noqa: E712
            )
        )).scalars().all()

        seen_users: set[str] = set()
        inbox_list: list[dict] = []
        from app.services.crypto import decrypt_secret, is_encrypted
        for sa in sa_rows:
            if sa.imap_user and sa.imap_user.lower() not in seen_users:
                raw_pw = sa.imap_password or ""
                pw = decrypt_secret(raw_pw) if raw_pw and is_encrypted(raw_pw) else raw_pw
                inbox_list.append({
                    "imap_host": sa.imap_host or "imap.gmail.com",
                    "imap_user": sa.imap_user,
                    "imap_password": pw,
                })
                seen_users.add(sa.imap_user.lower())

        if not inbox_list:
            logger.debug("check_replies: no IMAP accounts configured, skipping")
            return

        # ── Poll each inbox ───────────────────────────────────────────────────
        for inbox in inbox_list:
            imap_host = inbox["imap_host"]
            imap_user = inbox["imap_user"]
            imap_password = inbox["imap_password"]

            try:
                imap = imaplib.IMAP4_SSL(imap_host, 993)
                imap.login(imap_user, imap_password)
                imap.select("INBOX")
                cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
                since_date = cutoff.strftime("%d-%b-%Y")
                status, data = imap.search(None, f'SINCE "{since_date}"')
                if status != "OK" or not data[0]:
                    imap.logout()
                    logger.info("check_replies: [%s] no messages in last 6 hours", imap_user)
                    continue
                msg_nums = data[0].split()
            except Exception as exc:
                logger.warning("check_replies: IMAP connect failed for %s: %s", imap_user, exc)
                continue

            ingested_nums: list = []
            for num in msg_nums:
                try:
                    _, raw = imap.fetch(num, "(BODY.PEEK[])")
                    raw_bytes = raw[0][1] if raw and raw[0] else None
                    if not raw_bytes:
                        continue
                    parsed = email_lib.message_from_bytes(raw_bytes)
                    try:
                        msg_dt = parsedate_to_datetime(parsed.get("Date", ""))
                        if msg_dt.tzinfo is None:
                            msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                        if msg_dt < cutoff:
                            continue
                    except Exception:
                        pass
                    from_raw = parsed.get("From", "")
                    from_email_match = re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", from_raw, re.I)
                    if not from_email_match:
                        continue
                    from_email = from_email_match.group(0).lower()

                    is_test_reply = from_email in test_email_set
                    lead = email_to_lead.get(from_email) if not is_test_reply else None
                    if not lead and not is_test_reply:
                        continue

                    subject = _header_str(parsed.get("Subject", ""))

                    # Self-loop guard: skip outbound emails that land in the sender's own inbox
                    if is_test_reply and from_email == imap_user.lower():
                        if not re.match(r"^Re:\s*", subject, re.I):
                            continue
                    # Also guard for real accounts: skip emails sent FROM this inbox account
                    if not is_test_reply and from_email == imap_user.lower():
                        continue

                    bare = re.sub(r"^(Re:\s*)+", "", subject, flags=re.I).strip()
                    orig_message = subject_to_message.get(bare.lower())
                    if not orig_message:
                        orig_message = next(
                            (v for k, v in subject_to_message.items() if bare.lower().startswith(k[:30])),
                            None,
                        )
                    if not orig_message:
                        logger.info("check_replies: [%s] no outbound match for subject '%s'", imap_user, bare)
                        continue

                    if is_test_reply:
                        lead = lead_by_id.get(orig_message.lead_id)
                        if not lead:
                            continue
                        try:
                            cl_check = (await db.execute(
                                select(CampaignLead).where(
                                    CampaignLead.lead_id == lead.id,
                                    CampaignLead.campaign_id == orig_message.campaign_id,
                                )
                            )).scalar_one_or_none()
                            if cl_check:
                                mapped_email = (cl_check.personalization_data or {}).get("test_email_override", "")
                                if mapped_email.lower() != from_email:
                                    continue
                        except Exception:
                            pass

                    existing = (await db.execute(
                        select(Reply).where(
                            Reply.lead_id == lead.id,
                            Reply.message_id == orig_message.id,
                        )
                    )).scalar_one_or_none()
                    if existing:
                        ingested_nums.append(num)
                        continue

                    body = _body_text(parsed)

                    intent = "interested"
                    sentiment = "neutral"
                    priority = "medium"
                    suggested_response = None
                    ai_analysis_data = None
                    try:
                        from app.agents.reply_analysis_agent import ReplyAnalysisAgent
                        agent = ReplyAnalysisAgent()
                        analysis = await agent.run(
                            reply_text=body,
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
                        logger.warning("check_replies: AI analysis failed (non-fatal): %s", agent_exc)

                    reply = Reply(
                        tenant_id=lead.tenant_id,
                        message_id=orig_message.id,
                        lead_id=lead.id,
                        channel="email",
                        subject=subject,
                        body_text=body,
                        intent=intent,
                        sentiment=sentiment,
                        priority=priority,
                        suggested_response=suggested_response,
                        ai_analysis=ai_analysis_data,
                        is_read=False,
                    )
                    db.add(reply)
                    await db.flush()  # get reply.id before dispatching task

                    if orig_message.campaign_id:
                        await db.execute(
                            update(Campaign)
                            .where(Campaign.id == orig_message.campaign_id)
                            .values(reply_count=Campaign.reply_count + 1)
                        )

                    # Gap 2: auto-draft a polished response for interested/meeting replies
                    if intent in ("interested", "meeting_request", "question"):
                        try:
                            from app.tasks.orchestrator_tasks import draft_reply_response
                            draft_reply_response.apply_async(args=[str(reply.id)], countdown=30)
                            logger.info("check_replies: queued reply-response draft for reply %s (intent=%s)", reply.id, intent)
                        except Exception as _gap2_err:
                            logger.warning("check_replies: Gap 2 dispatch failed (non-fatal): %s", _gap2_err)

                    ingested_nums.append(num)
                    logger.info("check_replies: [%s] ingested reply from %s re '%s'", imap_user, from_email, bare)

                except Exception as exc:
                    logger.warning("check_replies: [%s] error processing msg %s: %s", imap_user, num, exc)

            await db.commit()

            for num in ingested_nums:
                try:
                    imap.store(num, "+FLAGS", "\\Seen")
                except Exception:
                    pass

            try:
                imap.logout()
            except Exception:
                pass


@celery_app.task
def check_sender_health():
    """Periodic task – check deliverability health of sender accounts."""
    pass


@celery_app.task
def reset_daily_counts():
    """Periodic task – reset sent_today counter on all sender accounts."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_reset_daily_counts_async())
    finally:
        loop.close()


async def _reset_daily_counts_async():
    from sqlalchemy import update
    from app.models.campaign import SenderAccount

    session_factory = _make_session_factory()
    async with session_factory() as db:
        await db.execute(update(SenderAccount).values(sent_today=0))
        await db.commit()
