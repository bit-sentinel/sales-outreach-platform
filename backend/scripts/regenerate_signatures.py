#!/usr/bin/env python
"""
Regenerate draft email signatures with new emoji icon format.
Updates all draft messages in campaigns with the new signature style.
"""

import os
import sys
import asyncio
from uuid import UUID

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import async_session_factory
from app.models import Message, Campaign
from app.tools.email_renderer import render_email_html, render_email_plain, _strip_llm_signature
from sqlalchemy import select, func

# Sender details
SENDER_NAME = "Sameera Gurung"
SENDER_COMPANY = "LaunchHouse Events"
SENDER_ROLE = "Cvent Registration & Event Technology Operations"
SENDER_SITE_URL = "https://launchhouse.events/"
SENDER_CALENDAR_LINK = "https://calendar.app.google/Aycv6qmqjNk4qJpJ7"
SENDER_PHONE = "+1 (571) 444-8523"
SENDER_EMAIL = "sam@launchhouse.events"


async def regenerate_signatures():
    """Regenerate all draft messages with new signature."""
    async with async_session_factory() as session:
        # Get all draft messages with campaign_id
        stmt = (
            select(Message)
            .where(Message.status == "draft")
            .where(Message.campaign_id.isnot(None))
        )
        result = await session.execute(stmt)
        draft_messages = result.scalars().all()
        
        print(f"Found {len(draft_messages)} draft messages to update")
        
        updated_count = 0
        for msg in draft_messages:
            try:
                # Get campaign for context
                campaign_stmt = select(Campaign).where(Campaign.id == msg.campaign_id)
                campaign_result = await session.execute(campaign_stmt)
                campaign = campaign_result.scalar_one_or_none()
                
                campaign_name = campaign.name if campaign else "Unknown"
                print(f"\nProcessing: {msg.subject[:50]}... ({campaign_name})")
                
                # Extract body content without signature
                # The body_html contains the full email with signature from render_email_html
                body_content = _strip_llm_signature(msg.body_text or "")
                
                if not body_content.strip():
                    print(f"  ⚠️  Empty body content, skipping")
                    continue
                
                # Regenerate HTML with new signature
                new_body_html = render_email_html(
                    body_text=body_content,
                    sender_name=SENDER_NAME,
                    sender_company=SENDER_COMPANY,
                    sender_role=SENDER_ROLE,
                    sender_site_url=SENDER_SITE_URL,
                    sender_calendar_link=SENDER_CALENDAR_LINK,
                    sender_phone=SENDER_PHONE,
                    sender_email=SENDER_EMAIL,
                    header_style="slim",
                    compact_signature=False,
                )
                
                # Regenerate plain text with new signature
                new_body_text = render_email_plain(
                    body_text=body_content,
                    sender_name=SENDER_NAME,
                    sender_site_url=SENDER_SITE_URL,
                    sender_phone=SENDER_PHONE,
                    sender_email=SENDER_EMAIL,
                )
                
                # Update message
                msg.body_html = new_body_html
                msg.body_text = new_body_text
                await session.flush()
                
                print(f"  ✓ Updated successfully")
                updated_count += 1
                
            except Exception as e:
                print(f"  ✗ Error: {str(e)}")
                continue
        
        # Commit all changes
        if updated_count > 0:
            await session.commit()
            print(f"\n✓ Successfully updated {updated_count} messages")
        else:
            await session.rollback()
            print(f"\nNo messages were updated")


if __name__ == "__main__":
    asyncio.run(regenerate_signatures())
