"""Analytics endpoints – dashboard KPIs, campaign stats, lead pipeline."""

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.api.deps import get_tenant_id
from app.models.campaign import Campaign
from app.models.lead import Lead, LeadScore
from app.schemas.common import APIResponse

router = APIRouter()


@router.get("/dashboard")
async def dashboard_kpis(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    total_leads = (await db.execute(
        select(func.count()).where(Lead.tenant_id == tenant_id)
    )).scalar() or 0

    hot_leads = (await db.execute(
        select(func.count(func.distinct(LeadScore.lead_id)))
        .where(LeadScore.tenant_id == tenant_id, LeadScore.tier == "hot")
    )).scalar() or 0

    warm_leads = (await db.execute(
        select(func.count(func.distinct(LeadScore.lead_id)))
        .where(LeadScore.tenant_id == tenant_id, LeadScore.tier == "warm")
    )).scalar() or 0

    scored_leads = (await db.execute(
        select(func.count(func.distinct(LeadScore.lead_id)))
        .where(LeadScore.tenant_id == tenant_id)
    )).scalar() or 0

    active_campaigns = (await db.execute(
        select(func.count()).where(Campaign.tenant_id == tenant_id, Campaign.status == "active")
    )).scalar() or 0

    total_campaigns = (await db.execute(
        select(func.count()).where(Campaign.tenant_id == tenant_id)
    )).scalar() or 0

    email_stats = (await db.execute(
        select(
            func.sum(Campaign.sent_count),
            func.sum(Campaign.open_count),
            func.sum(Campaign.reply_count),
            func.sum(Campaign.bounce_count),
        ).where(Campaign.tenant_id == tenant_id)
    )).one()

    sent_total = email_stats[0] or 0
    open_total = email_stats[1] or 0
    reply_total = email_stats[2] or 0
    bounce_total = email_stats[3] or 0

    open_rate = round((open_total / sent_total * 100), 1) if sent_total > 0 else 0.0
    reply_rate = round((reply_total / sent_total * 100), 1) if sent_total > 0 else 0.0
    bounce_rate = round((bounce_total / sent_total * 100), 1) if sent_total > 0 else 0.0

    enriched_leads = (await db.execute(
        select(func.count()).where(
            Lead.tenant_id == tenant_id,
            Lead.enrichment_status.in_(["enriched", "completed"])
        )
    )).scalar() or 0

    return APIResponse(data={
        "total_leads": total_leads,
        "enriched_leads": enriched_leads,
        "scored_leads": scored_leads,
        "hot_leads": hot_leads,
        "warm_leads": warm_leads,
        "active_campaigns": active_campaigns,
        "total_campaigns": total_campaigns,
        "emails_sent_total": sent_total,
        "open_rate": open_rate,
        "reply_rate": reply_rate,
        "bounce_rate": bounce_rate,
        "total_replies": reply_total,
        "actionable_leads": hot_leads + warm_leads,
        "coverage_pct": round(enriched_leads / total_leads * 100) if total_leads > 0 else 0,
    })


@router.get("/lead-pipeline")
async def lead_pipeline(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(Lead.status, func.count().label("cnt"))
        .where(Lead.tenant_id == tenant_id)
        .group_by(Lead.status)
    )).all()
    counts: dict[str, int] = {r.status: r.cnt for r in rows}
    return APIResponse(data={
        "new": counts.get("new", 0),
        "enriching": counts.get("enriching", 0),
        "enriched": counts.get("enriched", 0),
        "scored": counts.get("scored", 0),
        "campaign_active": counts.get("campaign_active", 0),
        "replied": counts.get("replied", 0),
        "converted": counts.get("converted", 0),
        "disqualified": counts.get("disqualified", 0),
    })


@router.get("/score-distribution")
async def score_distribution(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    total_leads = (await db.execute(
        select(func.count()).where(Lead.tenant_id == tenant_id)
    )).scalar() or 0

    rows = (await db.execute(
        select(LeadScore.tier, func.count(func.distinct(LeadScore.lead_id)).label("cnt"))
        .where(LeadScore.tenant_id == tenant_id)
        .group_by(LeadScore.tier)
    )).all()
    counts: dict[str, int] = {r.tier: r.cnt for r in rows}
    scored = sum(counts.values())
    return APIResponse(data={
        "hot": counts.get("hot", 0),
        "warm": counts.get("warm", 0),
        "cold": counts.get("cold", 0),
        "unscored": max(0, total_leads - scored),
    })


@router.get("/hot-leads")
async def hot_leads_endpoint(
    limit: int = Query(default=5, ge=1, le=20),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    score_rows = (await db.execute(
        select(LeadScore.lead_id, LeadScore.overall_score, LeadScore.tier)
        .where(LeadScore.tenant_id == tenant_id)
        .order_by(LeadScore.overall_score.desc())
        .limit(limit * 3)
    )).all()

    seen: set[uuid.UUID] = set()
    top: list = []
    for row in score_rows:
        if row.lead_id not in seen:
            seen.add(row.lead_id)
            top.append(row)
        if len(top) == limit:
            break

    if not top:
        return APIResponse(data=[])

    lead_ids = [r.lead_id for r in top]
    score_map = {r.lead_id: (r.overall_score, r.tier) for r in top}

    leads_result = await db.execute(
        select(Lead).where(Lead.id.in_(lead_ids), Lead.tenant_id == tenant_id)
    )
    leads_by_id = {l.id: l for l in leads_result.scalars().all()}

    result = []
    for lead_id in lead_ids:
        lead = leads_by_id.get(lead_id)
        if not lead:
            continue
        score, tier = score_map[lead_id]
        contact = lead.contact
        company = lead.company
        result.append({
            "id": str(lead.id),
            "name": f"{contact.first_name} {contact.last_name}".strip() if contact else "Unknown",
            "title": contact.title or "" if contact else "",
            "company": company.name if company else "",
            "score": round(score),
            "tier": tier,
            "status": lead.status,
        })
    return APIResponse(data=result)


@router.get("/recent-activity")
async def recent_activity(
    limit: int = Query(default=8, ge=1, le=30),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    from app.models.lead import LeadActivity, Contact
    from app.models.campaign import Message, Reply

    now = datetime.now(timezone.utc)

    def rel_time(dt: datetime) -> str:
        aware = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        secs = int((now - aware).total_seconds())
        if secs < 60: return "Just now"
        if secs < 3600: return f"{secs // 60}m ago"
        if secs < 86400: return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"

    def sort_key(item: dict) -> datetime:
        dt = datetime.fromisoformat(item["created_at"])
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    fetch_n = limit * 2  # fetch more from each source before merging

    items: list[dict] = []

    # ── 1. LeadActivity log ───────────────────────────────────────────────────
    activity_rows = (await db.execute(
        select(LeadActivity)
        .where(LeadActivity.tenant_id == tenant_id)
        .order_by(LeadActivity.created_at.desc())
        .limit(fetch_n)
    )).scalars().all()

    for act in activity_rows:
        items.append({
            "id": str(act.id),
            "type": act.activity_type,
            "title": act.title,
            "description": act.description,
            "time": rel_time(act.created_at),
            "created_at": act.created_at.isoformat(),
        })

    # ── 2. Sent messages ──────────────────────────────────────────────────────
    msg_rows = (await db.execute(
        select(Message, Contact.first_name, Contact.last_name)
        .join(Lead, Message.lead_id == Lead.id, isouter=True)
        .join(Contact, Lead.contact_id == Contact.id, isouter=True)
        .where(Message.tenant_id == tenant_id, Message.status == "sent", Message.direction == "outbound")
        .order_by(Message.sent_at.desc().nullslast(), Message.created_at.desc())
        .limit(fetch_n)
    )).all()

    for msg, first_name, last_name in msg_rows:
        name = f"{first_name or ''} {last_name or ''}".strip() or "Unknown"
        subject = msg.subject or "email"
        ts = msg.sent_at or msg.created_at
        items.append({
            "id": f"msg-{msg.id}",
            "type": "email_sent",
            "title": f"Email sent to {name}",
            "description": subject,
            "time": rel_time(ts),
            "created_at": (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)).isoformat(),
        })

    # ── 3. Replies received ───────────────────────────────────────────────────
    reply_rows = (await db.execute(
        select(Reply, Contact.first_name, Contact.last_name)
        .join(Lead, Reply.lead_id == Lead.id, isouter=True)
        .join(Contact, Lead.contact_id == Contact.id, isouter=True)
        .where(Reply.tenant_id == tenant_id)
        .order_by(Reply.created_at.desc())
        .limit(fetch_n)
    )).all()

    for reply, first_name, last_name in reply_rows:
        name = f"{first_name or ''} {last_name or ''}".strip() or "Unknown"
        intent_label = {
            "interested": "interested",
            "meeting_request": "requested a meeting",
            "question": "asked a question",
            "objection": "raised an objection",
            "not_now": "said not now",
            "unsubscribe": "unsubscribed",
        }.get(reply.intent or "", "replied")
        items.append({
            "id": f"reply-{reply.id}",
            "type": "reply",
            "title": f"{name} {intent_label}",
            "description": reply.subject,
            "time": rel_time(reply.created_at),
            "created_at": reply.created_at.isoformat(),
        })

    # ── Merge-sort by recency, deduplicate by id ───────────────────────────────
    seen: set[str] = set()
    unique: list[dict] = []
    for item in sorted(items, key=sort_key, reverse=True):
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)
        if len(unique) == limit:
            break

    return APIResponse(data=unique)


@router.get("/campaigns/{campaign_id}/stats")
async def campaign_stats(
    campaign_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return APIResponse(data={
        "campaign_id": str(campaign_id),
        "total_leads": 0, "sent": 0, "delivered": 0, "opened": 0,
        "clicked": 0, "replied": 0, "bounced": 0, "unsubscribed": 0,
        "daily_breakdown": [],
    })


@router.get("/email-deliverability")
async def email_deliverability(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return APIResponse(data={"accounts": [], "overall_health": 1.0})


@router.get("/top-campaigns")
async def top_campaigns(
    limit: int = Query(default=10, ge=1, le=50),
    metric: str = Query(default="reply_rate"),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return APIResponse(data=[])


@router.get("/page-data")
async def analytics_page_data(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    from app.models.campaign import Message, Reply

    # Total sent (live from messages table)
    total_sent = (await db.execute(
        select(func.count()).select_from(Message)
        .where(Message.tenant_id == tenant_id, Message.status == "sent")
    )).scalar() or 0

    # Aggregate open/reply/bounce from campaigns
    email_stats = (await db.execute(
        select(
            func.sum(Campaign.open_count),
            func.sum(Campaign.reply_count),
            func.sum(Campaign.sent_count),
            func.sum(Campaign.bounce_count),
        ).where(Campaign.tenant_id == tenant_id)
    )).one()
    open_total = email_stats[0] or 0
    reply_total = email_stats[1] or 0
    sent_total_camps = email_stats[2] or 0

    avg_open_rate = round(open_total / sent_total_camps * 100, 1) if sent_total_camps > 0 else 0.0
    avg_reply_rate = round(reply_total / sent_total_camps * 100, 1) if sent_total_camps > 0 else 0.0

    total_leads = (await db.execute(
        select(func.count()).where(Lead.tenant_id == tenant_id)
    )).scalar() or 0

    # Per-campaign performance (exclude drafts with no sends)
    campaigns_rows = (await db.execute(
        select(Campaign).where(Campaign.tenant_id == tenant_id)
        .order_by(Campaign.created_at.desc())
        .limit(10)
    )).scalars().all()

    campaign_perf = []
    for c in campaigns_rows:
        s = c.sent_count or 0
        open_rate = round((c.open_count or 0) / s * 100, 1) if s > 0 else 0.0
        reply_rate = round((c.reply_count or 0) / s * 100, 1) if s > 0 else 0.0
        campaign_perf.append({
            "name": c.name,
            "openRate": open_rate,
            "replyRate": reply_rate,
            "sent": s,
        })

    # Lead sources (group by lead.source)
    source_rows = (await db.execute(
        select(Lead.source, func.count().label("cnt"))
        .where(Lead.tenant_id == tenant_id)
        .group_by(Lead.source)
        .order_by(func.count().desc())
    )).all()

    source_colors = ['#6366f1', '#22c55e', '#f59e0b', '#ec4899', '#3b82f6', '#14b8a6']
    source_data = []
    for i, r in enumerate(source_rows):
        source_data.append({
            "name": r.source or "Unknown",
            "value": r.cnt,
            "color": source_colors[i % len(source_colors)],
        })

    # Reply intent breakdown
    intent_rows = (await db.execute(
        select(Reply.intent, func.count().label("cnt"))
        .where(Reply.tenant_id == tenant_id, Reply.intent.isnot(None))
        .group_by(Reply.intent)
        .order_by(func.count().desc())
    )).all()

    intent_colors = {
        "interested": "#10b981",
        "meeting_request": "#6366f1",
        "question": "#f59e0b",
        "objection": "#f97316",
        "unsubscribe": "#ef4444",
    }
    intent_labels = {
        "interested": "Interested",
        "meeting_request": "Meeting Req.",
        "question": "Question",
        "objection": "Objection",
        "unsubscribe": "Unsubscribe",
    }
    intent_data = [
        {
            "intent": intent_labels.get(r.intent, r.intent),
            "count": r.cnt,
            "color": intent_colors.get(r.intent, "#94a3b8"),
        }
        for r in intent_rows
    ]

    # Weekly sent breakdown (last 8 weeks)
    from sqlalchemy import text as sql_text
    weekly_rows = (await db.execute(
        sql_text("""
            SELECT
                to_char(date_trunc('week', COALESCE(sent_at, created_at) AT TIME ZONE 'UTC'), 'Mon DD') AS week,
                COUNT(*) AS sent
            FROM messages
            WHERE tenant_id = :tenant_id
              AND status = 'sent'
              AND COALESCE(sent_at, created_at) >= NOW() - INTERVAL '8 weeks'
            GROUP BY date_trunc('week', COALESCE(sent_at, created_at) AT TIME ZONE 'UTC')
            ORDER BY date_trunc('week', COALESCE(sent_at, created_at) AT TIME ZONE 'UTC')
        """),
        {"tenant_id": str(tenant_id)},
    )).all()
    weekly_data = [{"week": r.week, "sent": r.sent} for r in weekly_rows]

    return APIResponse(data={
        "kpis": {
            "total_sent": total_sent,
            "avg_open_rate": avg_open_rate,
            "avg_reply_rate": avg_reply_rate,
            "total_leads": total_leads,
        },
        "campaign_performance": campaign_perf,
        "lead_sources": source_data,
        "reply_intent": intent_data,
        "weekly_sent": weekly_data,
    })


@router.get("/email-performance")
async def email_performance(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Weekly sent / opened / replied breakdown for the last 8 weeks."""
    from app.models.campaign import Message, EmailEvent, Reply
    from sqlalchemy import text as sql_text

    rows = (await db.execute(
        sql_text("""
            WITH weeks AS (
                SELECT generate_series(
                    date_trunc('week', NOW() - INTERVAL '7 weeks'),
                    date_trunc('week', NOW()),
                    INTERVAL '1 week'
                ) AS week_start
            ),
            sent_counts AS (
                SELECT date_trunc('week', COALESCE(sent_at, created_at) AT TIME ZONE 'UTC') AS week_start,
                       COUNT(*) AS sent
                FROM messages
                WHERE tenant_id = :tenant_id
                  AND status = 'sent'
                  AND COALESCE(sent_at, created_at) >= NOW() - INTERVAL '8 weeks'
                GROUP BY 1
            ),
            opened_counts AS (
                SELECT date_trunc('week', ee.created_at AT TIME ZONE 'UTC') AS week_start,
                       COUNT(*) AS opened
                FROM email_events ee
                JOIN messages m ON m.id = ee.message_id
                WHERE m.tenant_id = :tenant_id
                  AND ee.event_type = 'opened'
                  AND ee.created_at >= NOW() - INTERVAL '8 weeks'
                GROUP BY 1
            ),
            replied_counts AS (
                SELECT date_trunc('week', created_at AT TIME ZONE 'UTC') AS week_start,
                       COUNT(*) AS replied
                FROM replies
                WHERE tenant_id = :tenant_id
                  AND created_at >= NOW() - INTERVAL '8 weeks'
                GROUP BY 1
            )
            SELECT
                to_char(w.week_start, 'Mon DD') AS date,
                COALESCE(s.sent, 0)    AS sent,
                COALESCE(o.opened, 0)  AS opened,
                COALESCE(r.replied, 0) AS replied
            FROM weeks w
            LEFT JOIN sent_counts s    ON s.week_start = w.week_start
            LEFT JOIN opened_counts o  ON o.week_start = w.week_start
            LEFT JOIN replied_counts r ON r.week_start = w.week_start
            ORDER BY w.week_start
        """),
        {"tenant_id": str(tenant_id)},
    )).all()

    data = [
        {"date": row.date, "sent": row.sent, "opened": row.opened, "replied": row.replied}
        for row in rows
    ]

    # Aggregate totals for the header stats
    total_sent = sum(r["sent"] for r in data)
    total_opened = sum(r["opened"] for r in data)
    total_replied = sum(r["replied"] for r in data)
    open_rate = round(total_opened / total_sent * 100, 1) if total_sent > 0 else 0.0
    reply_rate = round(total_replied / total_sent * 100, 1) if total_sent > 0 else 0.0

    return APIResponse(data={
        "weekly": data,
        "total_sent": total_sent,
        "open_rate": open_rate,
        "reply_rate": reply_rate,
    })
