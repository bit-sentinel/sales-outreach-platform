#!/usr/bin/env python
"""
Regenerate all draft messages by re-running PersonalizationAgent with the
latest system prompt and copywriting framework.

Gathers the same lead context (contact, company, enrichment, research, insights)
that campaign_tasks uses, then calls the agent and updates body_html / body_text / subject.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.campaign import Campaign, Message, SenderAccount
from app.models.lead import AIInsight, Contact, Company, EnrichmentData, Lead
from app.models.lead import ResearchData as ResearchDataModel
from app.tasks.personalization_payloads import build_personalization_payload
from app.agents.personalization_agent import PersonalizationAgent


def _make_session_factory():
    settings = get_settings()
    engine = create_async_engine(
        str(settings.database_url),
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def regenerate():
    session_factory = _make_session_factory()
    settings = get_settings()

    async with session_factory() as db:
        result = await db.execute(
            select(Message)
            .where(Message.status == "draft")
            .where(Message.campaign_id.isnot(None))
        )
        drafts = result.scalars().all()
        print(f"Found {len(drafts)} draft messages to regenerate\n")

        updated = 0
        failed = 0

        for msg in drafts:
            try:
                # ── Campaign ──────────────────────────────────────────────────
                campaign = (await db.execute(
                    select(Campaign).where(Campaign.id == msg.campaign_id)
                )).scalar_one_or_none()
                if not campaign:
                    print(f"  SKIP  no campaign for msg {msg.id}")
                    continue

                # ── Lead → contact + company ──────────────────────────────────
                lead = (await db.execute(
                    select(Lead).where(Lead.id == msg.lead_id)
                )).scalar_one_or_none()

                contact = None
                company = None
                if lead:
                    if lead.contact_id:
                        contact = (await db.execute(
                            select(Contact).where(Contact.id == lead.contact_id)
                        )).scalar_one_or_none()
                    if lead.company_id:
                        company = (await db.execute(
                            select(Company).where(Company.id == lead.company_id)
                        )).scalar_one_or_none()

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

                # ── Enrichment / research / insights ──────────────────────────
                research_data = None
                enrichment_data = None
                insights_rows = []
                if lead:
                    insights_rows = (await db.execute(
                        select(AIInsight)
                        .where(AIInsight.lead_id == lead.id)
                        .order_by(AIInsight.created_at.desc())
                        .limit(10)
                    )).scalars().all()

                    research_rows = (await db.execute(
                        select(ResearchDataModel)
                        .where(ResearchDataModel.lead_id == lead.id)
                        .order_by(ResearchDataModel.created_at.desc())
                        .limit(5)
                    )).scalars().all()

                    enrich_rows = (await db.execute(
                        select(EnrichmentData)
                        .where(EnrichmentData.lead_id == lead.id)
                        .order_by(EnrichmentData.created_at.desc())
                        .limit(10)
                    )).scalars().all()

                    research_data, enrichment_data = build_personalization_payload(
                        insights_rows, research_rows, enrich_rows
                    )

                # ── Sender info ───────────────────────────────────────────────
                sender_info = {
                    "sender_first_name": settings.sender_first_name,
                    "sender_last_name": "",
                    "sender_email": str(settings.sendgrid_from_email or settings.email_default_from),
                    "sender_calendar_link": settings.sender_calendar_link or "",
                    "company_site_url": settings.company_site_url,
                }
                if campaign.sender_account_id:
                    sender = (await db.execute(
                        select(SenderAccount)
                        .where(SenderAccount.id == campaign.sender_account_id)
                    )).scalar_one_or_none()
                    if sender:
                        sender_info = {
                            "sender_first_name": settings.sender_first_name,
                            "sender_last_name": "",
                            "sender_email": sender.email,
                            "sender_display_name": sender.display_name or "",
                            "sender_calendar_link": settings.sender_calendar_link or "",
                            "company_site_url": settings.company_site_url,
                        }

                # ── Previous email context (for follow-up steps) ──────────────
                previous_email_subject = None
                previous_email_body = None
                step = msg.sequence_step or 0
                if step > 0:
                    prev = (await db.execute(
                        select(Message)
                        .where(
                            Message.lead_id == msg.lead_id,
                            Message.campaign_id == msg.campaign_id,
                            Message.direction == "outbound",
                            Message.sequence_step == step - 1,
                        )
                        .order_by(Message.created_at.desc())
                        .limit(1)
                    )).scalar_one_or_none()
                    if prev:
                        previous_email_subject = prev.subject
                        previous_email_body = prev.body_text

                # ── Call PersonalizationAgent ─────────────────────────────────
                step_config = {"step": step + 1}   # agent expects 1-indexed step
                agent = PersonalizationAgent()
                content = await agent.run(
                    lead_id=str(msg.lead_id),
                    tenant_id=str(msg.tenant_id),
                    step_config=step_config,
                    lead_data=str(lead_data) if lead_data else None,
                    research_data=research_data,
                    enrichment_data=enrichment_data,
                    insights=[{"content": i.content} for i in insights_rows] if insights_rows else None,
                    sender_info=sender_info,
                    previous_email_subject=previous_email_subject,
                    previous_email_body=previous_email_body,
                )

                if content.get("parse_error"):
                    print(f"  ERR   parse error for msg {msg.id} — {content.get('raw_response','')[:80]}")
                    failed += 1
                    continue

                msg.subject = content.get("subject") or msg.subject
                msg.body_html = content.get("body_html") or msg.body_html
                msg.body_text = content.get("body_text") or msg.body_text
                await db.flush()

                label = contact.first_name if contact else str(msg.lead_id)[:8]
                print(f"  OK    [{campaign.name}] step={step} {label} — {(msg.subject or '')[:60]}")
                updated += 1

            except Exception as e:
                import traceback
                print(f"  ERR   msg {msg.id}: {e}")
                traceback.print_exc()
                failed += 1
                continue

        if updated > 0:
            await session_factory().close()
            async with session_factory() as commit_db:
                # Re-fetch and commit
                pass
            await db.commit()
            print(f"\nDone. Regenerated {updated} messages, {failed} failed.")
        else:
            await db.rollback()
            print(f"\nNothing regenerated. {failed} failed.")


if __name__ == "__main__":
    asyncio.run(regenerate())
