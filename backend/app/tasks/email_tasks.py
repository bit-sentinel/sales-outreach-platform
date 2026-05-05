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


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email(self, message_id: str):
    """Send a single email via the configured provider."""
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
                    from_name = sender.display_name

            # ── Send via SendGrid ───────────────────────────────────────────────
            external_id: str | None = None
            if settings.sendgrid_api_key:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail, To, From, Content

                subject = message.subject or "(no subject)"

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
    from email.header import decode_header as _decode_header
    from sqlalchemy import select
    from app.models.campaign import Message, Reply, Campaign
    from app.models.lead import Lead, Contact
    from app.config import get_settings

    settings = get_settings()
    if not settings.gmail_imap_user or not settings.gmail_app_password:
        logger.debug("check_replies: GMAIL_IMAP_USER not configured, skipping")
        return

    session_factory = _make_session_factory()

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

    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.login(settings.gmail_imap_user, settings.gmail_app_password)
        imap.select("INBOX")
        status, data = imap.search(None, "UNSEEN")
        if status != "OK" or not data[0]:
            imap.logout()
            return
        msg_nums = data[0].split()
    except Exception as exc:
        logger.warning("check_replies: IMAP connect/search failed: %s", exc)
        return

    async with session_factory() as db:
        # Build email→lead lookup from real contact emails
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

        # ── Test mode: build test-email set for fast lookup ───────────────────
        # If any tenant has test mode enabled we also accept replies from their
        # configured test email addresses and route them back to the real lead
        # via the test_email_override stored on CampaignLead.personalization_data.
        from app.models.campaign import CampaignLead
        from app.models.tenant import Tenant
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

        # Build subject→message lookup (sent messages only)
        msg_rows = (await db.execute(
            select(Message).where(Message.status == "sent", Message.direction == "outbound")
        )).scalars().all()
        subject_to_message: dict[str, Message] = {}
        for m in msg_rows:
            if m.subject:
                subject_to_message[m.subject.lower().strip()] = m

        ingested_nums: list = []
        for num in msg_nums:
            try:
                # BODY.PEEK[] fetches without marking the message as \Seen — we only
                # mark it SEEN explicitly after a successful DB commit so that any
                # failure mid-processing leaves the email UNSEEN for the next poll.
                _, raw = imap.fetch(num, "(BODY.PEEK[])")
                raw_bytes = raw[0][1] if raw and raw[0] else None
                if not raw_bytes:
                    continue
                parsed = email_lib.message_from_bytes(raw_bytes)
                from_raw = parsed.get("From", "")
                from_email_match = re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", from_raw, re.I)
                if not from_email_match:
                    continue
                from_email = from_email_match.group(0).lower()

                # Determine lead. Normal mode: look up by real contact email.
                # Test mode: from_email is a test inbox — match by subject first,
                # then resolve lead from the outbound message's lead_id.
                is_test_reply = from_email in test_email_set
                lead = email_to_lead.get(from_email) if not is_test_reply else None
                if not lead and not is_test_reply:
                    continue  # not a tracked lead

                subject = _header_str(parsed.get("Subject", ""))

                # Self-loop guard: when the test inbox is the same as the IMAP
                # account (sam sends to sam), the original outbound email also
                # lands in sam's inbox with FROM=sam. Skip it — only process
                # genuine replies that carry a "Re:" prefix.
                if is_test_reply and from_email == settings.gmail_imap_user.lower():
                    if not re.match(r"^Re:\s*", subject, re.I):
                        continue  # original sent email in own inbox, not a reply

                # Strip "Re: " prefix(es) to find original subject
                bare = re.sub(r"^(Re:\s*)+", "", subject, flags=re.I).strip()
                orig_message = subject_to_message.get(bare.lower())
                if not orig_message:
                    orig_message = next(
                        (v for k, v in subject_to_message.items() if bare.lower().startswith(k[:30])),
                        None,
                    )
                if not orig_message:
                    logger.info("check_replies: no outbound message matched subject '%s' — will retry", bare)
                    continue

                # In test mode, resolve lead from the outbound message instead of
                # from_email, then verify the campaign_lead has the matching override.
                if is_test_reply:
                    lead = lead_by_id.get(orig_message.lead_id)
                    if not lead:
                        logger.info("check_replies: test reply — lead %s not found", orig_message.lead_id)
                        continue
                    # Safety check: confirm this lead was actually mapped to this test email
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
                                logger.info(
                                    "check_replies: test reply from %s but lead %s mapped to %s — skipping",
                                    from_email, lead.id, mapped_email,
                                )
                                continue
                    except Exception:
                        pass  # if check fails, proceed anyway

                # Check if reply already ingested
                existing = (await db.execute(
                    select(Reply).where(
                        Reply.lead_id == lead.id,
                        Reply.message_id == orig_message.id,
                    )
                )).scalar_one_or_none()
                if existing:
                    ingested_nums.append(num)  # already stored — safe to mark SEEN
                    continue

                body = _body_text(parsed)

                # Run AI analysis to determine intent/sentiment/priority
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
                    logger.warning("check_replies: AI analysis failed: %s", agent_exc)

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

                if orig_message.campaign_id:
                    from sqlalchemy import update
                    await db.execute(
                        update(Campaign)
                        .where(Campaign.id == orig_message.campaign_id)
                        .values(reply_count=Campaign.reply_count + 1)
                    )

                ingested_nums.append(num)
                logger.info("check_replies: ingested reply from %s re '%s'", from_email, bare)
            except Exception as exc:
                logger.warning("check_replies: error processing message %s: %s", num, exc)

        await db.commit()

        # Mark successfully processed messages as \Seen only after the DB commit.
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
