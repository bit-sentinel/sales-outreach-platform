#!/usr/bin/env python
"""
Re-render all draft messages through the latest branded HTML template.
- compact_signature=True (no calendar button)
- Dynamic sender name from campaign's SenderAccount
"""

import os
import re
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import async_session_factory
from app.models import Message, Campaign
from app.tools.email_renderer import render_email_html, render_email_plain, _strip_llm_signature
from sqlalchemy import select

SENDER_COMPANY = "LaunchHouse Events"
SENDER_ROLE = "Cvent Registration & Event Technology Operations"
SENDER_SITE_URL = "https://launchhouse.events/"
SENDER_PHONE = "+1 (571) 444-8523"

_SENDER_NAME_MAP: dict[str, str] = {
    "sam@launchhouse.events": "Sameera Gurung",
    "sam@launchhouse.in": "Sameera Gurung",
}


def _resolve_sender_name(email: str, display_name: str = "") -> str:
    e = (email or "").lower().strip()
    if e in _SENDER_NAME_MAP:
        return _SENDER_NAME_MAP[e]
    if display_name:
        return display_name
    username = e.split("@")[0]
    return " ".join(p.capitalize() for p in re.split(r"[._\-]", username)) or "Sameera Gurung"


def _extract_body_only(text: str) -> str:
    """Strip every signature layer from plain text, leaving only the email body."""
    from app.tools.email_renderer import _strip_llm_signature

    # 1. Strip from "Best," (handles branded plain-text sig)
    body = _strip_llm_signature(text)

    # 2. Strip from "--" email separator if present
    body = re.sub(r'\n--\n.*$', '', body, flags=re.DOTALL).strip()

    # 3. Strip trailing paragraphs that look like a contact/name block:
    #    - contains an email address (@), OR
    #    - all lines are short and end without sentence punctuation
    paragraphs = re.split(r'\n\s*\n', body)
    while len(paragraphs) > 1:
        last = paragraphs[-1].strip()
        lines = [l.strip() for l in last.splitlines() if l.strip()]
        if not lines:
            paragraphs.pop()
            continue
        has_email = any('@' in l for l in lines)
        looks_like_sig = all(
            len(l) < 60 and not re.search(r'[.?!]$', l)
            for l in lines
        ) and len(lines) <= 5
        if has_email or looks_like_sig:
            paragraphs.pop()
        else:
            break

    return '\n\n'.join(paragraphs).strip()


async def regenerate():
    async with async_session_factory() as session:
        stmt = (
            select(Message)
            .where(Message.status == "draft")
            .where(Message.campaign_id.isnot(None))
        )
        result = await session.execute(stmt)
        drafts = result.scalars().all()
        print(f"Found {len(drafts)} draft messages")

        updated = 0
        skipped = 0
        for msg in drafts:
            try:
                campaign_result = await session.execute(
                    select(Campaign).where(Campaign.id == msg.campaign_id)
                )
                campaign = campaign_result.scalar_one_or_none()

                sender_email = "sam@launchhouse.events"
                sender_display = ""
                if campaign and campaign.sender_account_id:
                    from app.models.campaign import SenderAccount
                    sa_result = await session.execute(
                        select(SenderAccount).where(SenderAccount.id == campaign.sender_account_id)
                    )
                    sa = sa_result.scalar_one_or_none()
                    if sa:
                        sender_email = sa.email or sender_email
                        sender_display = sa.display_name or ""

                sender_name = _resolve_sender_name(sender_email, sender_display)

                # Use body_text (plain) as source — strip ALL signature layers
                raw = re.sub(r"<[^>]+>", "", msg.body_text or "").strip()
                raw = _extract_body_only(raw)

                if not raw:
                    print(f"  SKIP (empty): {msg.subject}")
                    skipped += 1
                    continue

                new_html = render_email_html(
                    body_text=raw,
                    sender_name=sender_name,
                    sender_company=SENDER_COMPANY,
                    sender_role=SENDER_ROLE,
                    sender_site_url=SENDER_SITE_URL,
                    sender_calendar_link="",
                    sender_phone=SENDER_PHONE,
                    sender_email=sender_email,
                    header_style="slim",
                    compact_signature=True,
                )
                new_text = render_email_plain(
                    body_text=raw,
                    sender_name=sender_name,
                    sender_site_url=SENDER_SITE_URL,
                    sender_phone=SENDER_PHONE,
                    sender_email=sender_email,
                )

                msg.body_html = new_html
                msg.body_text = new_text
                await session.flush()

                campaign_name = campaign.name if campaign else "?"
                print(f"  OK  [{campaign_name}] step={msg.sequence_step} — {(msg.subject or '')[:60]}")
                updated += 1

            except Exception as e:
                print(f"  ERR {msg.id}: {e}")
                continue

        if updated > 0:
            await session.commit()
            print(f"\nDone. Updated {updated} messages, skipped {skipped}.")
        else:
            await session.rollback()
            print(f"\nNothing updated (skipped {skipped}).")


if __name__ == "__main__":
    asyncio.run(regenerate())
