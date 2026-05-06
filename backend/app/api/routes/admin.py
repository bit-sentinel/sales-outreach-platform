"""Admin endpoints – sender accounts, team management, API keys, AI config, audit log."""

import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.api.deps import get_current_user, get_tenant_id, require_role, PaginationDep
from app.schemas.common import APIResponse
from app.models.tenant import AuditLog, User, Tenant, ApiKey
from app.models.campaign import SenderAccount

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class SenderAccountCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)
    provider: str = Field(pattern="^(gmail|sendgrid|ses|smtp)$")
    daily_limit: int = Field(default=150, ge=1, le=2000)
    imap_host: str | None = None
    imap_user: str | None = None
    imap_password: str | None = None


class SenderAccountUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    daily_limit: int | None = Field(default=None, ge=1, le=2000)
    is_active: bool | None = None
    imap_host: str | None = None
    imap_user: str | None = None
    imap_password: str | None = None


class UserInviteRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: str = Field(default="member", pattern="^(admin|member|viewer)$")
    temp_password: str = Field(min_length=8, max_length=128)


class RoleUpdateRequest(BaseModel):
    role: str = Field(pattern="^(owner|admin|member|viewer)$")


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class AIConfigUpdate(BaseModel):
    model: str | None = None
    tone: str | None = None
    email_length: int | None = Field(default=None, ge=50, le=400)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None


# ── Sender Accounts ──────────────────────────────────────────────────────────

@router.get("/sender-accounts")
async def list_sender_accounts(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(SenderAccount)
        .where(SenderAccount.tenant_id == tenant_id)
        .order_by(SenderAccount.created_at)
    )).scalars().all()

    return APIResponse(data=[
        {
            "id": str(r.id),
            "email": r.email,
            "display_name": r.display_name,
            "provider": r.provider,
            "daily_limit": r.daily_limit,
            "sent_today": r.sent_today,
            "warmup_stage": r.warmup_stage,
            "is_active": r.is_active,
            "health_score": round(r.health_score * 100),
            "last_health_check": r.last_health_check.isoformat() if r.last_health_check else None,
            "created_at": r.created_at.isoformat(),
            "imap_host": r.imap_host,
            "imap_user": r.imap_user,
            "has_imap": bool(r.imap_user and r.imap_password),
        }
        for r in rows
    ])


@router.post("/sender-accounts", status_code=201)
async def create_sender_account(
    body: SenderAccountCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    acct = SenderAccount(
        tenant_id=tenant_id,
        email=body.email,
        display_name=body.display_name,
        provider=body.provider,
        daily_limit=body.daily_limit,
        imap_host=body.imap_host or None,
        imap_user=body.imap_user or None,
        imap_password=body.imap_password or None,
    )
    db.add(acct)
    await db.commit()
    await db.refresh(acct)
    return APIResponse(data={
        "id": str(acct.id),
        "email": acct.email,
        "display_name": acct.display_name,
        "provider": acct.provider,
        "daily_limit": acct.daily_limit,
        "sent_today": acct.sent_today,
        "warmup_stage": acct.warmup_stage,
        "is_active": acct.is_active,
        "health_score": round(acct.health_score * 100),
        "last_health_check": None,
        "created_at": acct.created_at.isoformat(),
        "imap_host": acct.imap_host,
        "imap_user": acct.imap_user,
        "has_imap": bool(acct.imap_user and acct.imap_password),
    })


@router.patch("/sender-accounts/{account_id}")
async def update_sender_account(
    account_id: uuid.UUID,
    body: SenderAccountUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    acct = (await db.execute(
        select(SenderAccount).where(
            SenderAccount.id == account_id,
            SenderAccount.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Sender account not found")
    if body.display_name is not None:
        acct.display_name = body.display_name
    if body.daily_limit is not None:
        acct.daily_limit = body.daily_limit
    if body.is_active is not None:
        acct.is_active = body.is_active
    if body.imap_host is not None:
        acct.imap_host = body.imap_host or None
    if body.imap_user is not None:
        acct.imap_user = body.imap_user or None
    if body.imap_password is not None:
        acct.imap_password = body.imap_password or None
    await db.commit()
    return APIResponse(message="Updated")


@router.delete("/sender-accounts/{account_id}", status_code=204)
async def delete_sender_account(
    account_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    acct = (await db.execute(
        select(SenderAccount).where(
            SenderAccount.id == account_id,
            SenderAccount.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if not acct:
        raise HTTPException(status_code=404, detail="Sender account not found")
    await db.delete(acct)
    await db.commit()


# ── Team / Users ─────────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(User)
        .where(User.tenant_id == tenant_id, User.is_active == True)
        .order_by(User.created_at)
    )).scalars().all()

    return APIResponse(data=[
        {
            "id": str(u.id),
            "first_name": u.first_name,
            "last_name": u.last_name,
            "email": u.email,
            "role": u.role,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat(),
        }
        for u in rows
    ])


@router.post("/users", status_code=201)
async def invite_user(
    body: UserInviteRequest,
    current_user=Depends(require_role("admin", "owner")),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(User).where(User.email == body.email)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    from passlib.hash import argon2
    new_user = User(
        tenant_id=tenant_id,
        email=body.email,
        password_hash=argon2.hash(body.temp_password),
        first_name=body.first_name,
        last_name=body.last_name,
        role=body.role,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return APIResponse(data={
        "id": str(new_user.id),
        "first_name": new_user.first_name,
        "last_name": new_user.last_name,
        "email": new_user.email,
        "role": new_user.role,
    })


@router.patch("/users/{user_id}/role")
async def change_user_role(
    user_id: uuid.UUID,
    body: RoleUpdateRequest,
    current_user=Depends(require_role("admin", "owner")),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    user = (await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = body.role
    await db.commit()
    return APIResponse(message="Role updated")


@router.delete("/users/{user_id}", status_code=204)
async def remove_user(
    user_id: uuid.UUID,
    current_user=Depends(require_role("admin", "owner")),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    user = (await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    await db.commit()


# ── API Keys ─────────────────────────────────────────────────────────────────

@router.get("/api-keys")
async def list_api_keys(
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(ApiKey)
        .where(ApiKey.tenant_id == tenant_id, ApiKey.is_active == True)
        .order_by(ApiKey.created_at)
    )).scalars().all()

    return APIResponse(data=[
        {
            "id": str(k.id),
            "name": k.name,
            "key_prefix": k.key_prefix,
            "scopes": k.scopes or [],
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "created_at": k.created_at.isoformat(),
        }
        for k in rows
    ])


@router.post("/api-keys", status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest,
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    raw_key = f"oai-{secrets.token_urlsafe(32)}"
    prefix = raw_key[:12]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = ApiKey(
        tenant_id=tenant_id,
        user_id=current_user.id,
        name=body.name,
        key_hash=key_hash,
        key_prefix=prefix,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return APIResponse(data={
        "id": str(api_key.id),
        "name": api_key.name,
        "key": raw_key,  # shown once only
        "key_prefix": prefix,
        "created_at": api_key.created_at.isoformat(),
    })


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    key = (await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.is_active = False
    await db.commit()


# ── Tenant / AI Config ───────────────────────────────────────────────────────

@router.get("/tenant")
async def get_tenant_settings(
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    s = tenant.settings or {}
    return APIResponse(data={
        "name": tenant.name,
        "plan": tenant.plan,
        "ai_config": {
            "model": s.get("ai_model", "claude-sonnet"),
            "tone": s.get("ai_tone", "Professional & Concise"),
            "email_length": s.get("ai_email_length", 160),
        },
    })


@router.patch("/tenant/ai-config")
async def update_ai_config(
    body: AIConfigUpdate,
    current_user=Depends(require_role("admin", "owner")),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    settings = dict(tenant.settings or {})
    if body.model is not None:
        settings["ai_model"] = body.model
    if body.tone is not None:
        settings["ai_tone"] = body.tone
    if body.email_length is not None:
        settings["ai_email_length"] = body.email_length
    if body.anthropic_api_key is not None:
        settings["anthropic_api_key"] = body.anthropic_api_key
    if body.openai_api_key is not None:
        settings["openai_api_key"] = body.openai_api_key

    from sqlalchemy.orm.attributes import flag_modified
    tenant.settings = settings
    flag_modified(tenant, "settings")
    await db.commit()
    return APIResponse(message="AI config saved")


# ── Test Mode ────────────────────────────────────────────────────────────────

class TestModeToggle(BaseModel):
    enabled: bool


class TestEmailAdd(BaseModel):
    email: EmailStr
    label: str = Field(default="", max_length=100)


class TestEmailToggle(BaseModel):
    enabled: bool


@router.get("/test-mode")
async def get_test_mode(
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    s = tenant.settings or {}
    return APIResponse(data=s.get("test_mode", {"enabled": False, "emails": []}))


@router.patch("/test-mode/toggle")
async def toggle_test_mode(
    body: TestModeToggle,
    current_user=Depends(require_role("admin", "owner")),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    from sqlalchemy.orm.attributes import flag_modified
    settings = dict(tenant.settings or {})
    tm = dict(settings.get("test_mode", {"enabled": False, "emails": []}))
    tm["enabled"] = body.enabled
    settings["test_mode"] = tm
    tenant.settings = settings
    flag_modified(tenant, "settings")
    await db.commit()
    return APIResponse(message=f"Test mode {'enabled' if body.enabled else 'disabled'}")


@router.post("/test-mode/emails", status_code=201)
async def add_test_email(
    body: TestEmailAdd,
    current_user=Depends(require_role("admin", "owner")),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    settings = dict(tenant.settings or {})
    tm = dict(settings.get("test_mode", {"enabled": False, "emails": []}))
    emails = list(tm.get("emails", []))

    if any(e["email"].lower() == body.email.lower() for e in emails):
        raise HTTPException(status_code=409, detail="Email already in test list")

    entry = {
        "id": str(uuid.uuid4()),
        "email": body.email,
        "label": body.label,
        "enabled": True,
    }
    from sqlalchemy.orm.attributes import flag_modified
    emails.append(entry)
    tm["emails"] = emails
    settings["test_mode"] = tm
    tenant.settings = settings
    flag_modified(tenant, "settings")
    await db.commit()
    return APIResponse(data=entry)


@router.patch("/test-mode/emails/{email_id}")
async def toggle_test_email(
    email_id: str,
    body: TestEmailToggle,
    current_user=Depends(require_role("admin", "owner")),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    settings = dict(tenant.settings or {})
    tm = dict(settings.get("test_mode", {"enabled": False, "emails": []}))
    emails = list(tm.get("emails", []))
    for e in emails:
        if e["id"] == email_id:
            e["enabled"] = body.enabled
            break
    from sqlalchemy.orm.attributes import flag_modified
    tm["emails"] = emails
    settings["test_mode"] = tm
    tenant.settings = settings
    flag_modified(tenant, "settings")
    await db.commit()
    return APIResponse(message="Updated")


@router.delete("/test-mode/emails/{email_id}", status_code=204)
async def delete_test_email(
    email_id: str,
    current_user=Depends(require_role("admin", "owner")),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )).scalar_one_or_none()
    settings = dict(tenant.settings or {})
    tm = dict(settings.get("test_mode", {"enabled": False, "emails": []}))
    from sqlalchemy.orm.attributes import flag_modified
    tm["emails"] = [e for e in tm.get("emails", []) if e["id"] != email_id]
    settings["test_mode"] = tm
    tenant.settings = settings
    flag_modified(tenant, "settings")
    await db.commit()


@router.post("/test-mode/flush")
async def flush_test_data(
    current_user=Depends(require_role("admin", "owner")),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete all data generated during test mode runs:
      - Replies linked to test-mode messages
      - EmailEvents linked to test-mode messages
      - Messages sent to test email overrides
      - FollowUps scheduled for test campaign_leads
      - Reset CampaignLead state (clear test_email_override, status→pending, step→0)
      - Recompute campaign sent_count and reply_count
    Identifies test data via CampaignLead.personalization_data->>'test_email_override'.
    """
    from sqlalchemy import delete as sql_delete, update as sql_update, func as sql_func
    from app.models.campaign import (
        CampaignLead, Message, Reply, EmailEvent, FollowUp, Campaign,
    )

    # 1. Find all campaign_leads for this tenant that have a test_email_override
    cl_rows = (await db.execute(
        select(CampaignLead).where(
            CampaignLead.tenant_id == tenant_id,
            CampaignLead.personalization_data.op("->>")(
                "test_email_override"
            ).isnot(None),
        )
    )).scalars().all()

    if not cl_rows:
        return APIResponse(data={"deleted": {"replies": 0, "messages": 0, "events": 0, "follow_ups": 0, "campaign_leads_reset": 0}})

    cl_ids = [cl.id for cl in cl_rows]
    lead_ids = list({cl.lead_id for cl in cl_rows})
    campaign_ids = list({cl.campaign_id for cl in cl_rows})

    # 2. Find messages for these (campaign_id, lead_id) pairs
    msg_rows = (await db.execute(
        select(Message).where(
            Message.tenant_id == tenant_id,
            Message.lead_id.in_(lead_ids),
            Message.campaign_id.in_(campaign_ids),
        )
    )).scalars().all()
    msg_ids = [m.id for m in msg_rows]

    counts = {"replies": 0, "messages": 0, "events": 0, "follow_ups": 0, "campaign_leads_reset": 0}

    if msg_ids:
        # 3. Delete Replies linked to these messages
        r = await db.execute(
            sql_delete(Reply).where(
                Reply.tenant_id == tenant_id,
                Reply.message_id.in_(msg_ids),
            )
        )
        counts["replies"] = r.rowcount

        # 4. Delete EmailEvents linked to these messages
        r = await db.execute(
            sql_delete(EmailEvent).where(
                EmailEvent.tenant_id == tenant_id,
                EmailEvent.message_id.in_(msg_ids),
            )
        )
        counts["events"] = r.rowcount

        # 5. Delete the Messages themselves
        r = await db.execute(
            sql_delete(Message).where(
                Message.tenant_id == tenant_id,
                Message.id.in_(msg_ids),
            )
        )
        counts["messages"] = r.rowcount

    # 6. Delete FollowUps for these campaign_leads
    r = await db.execute(
        sql_delete(FollowUp).where(
            FollowUp.tenant_id == tenant_id,
            FollowUp.campaign_lead_id.in_(cl_ids),
        )
    )
    counts["follow_ups"] = r.rowcount

    # 7. Reset CampaignLeads — clear override, rewind to pending/step 0
    for cl in cl_rows:
        pd = dict(cl.personalization_data or {})
        pd.pop("test_email_override", None)
        cl.personalization_data = pd if pd else None
        cl.status = "pending"
        cl.current_step = 0
        cl.next_action_at = None
    counts["campaign_leads_reset"] = len(cl_rows)

    await db.flush()

    # 8. Recompute sent_count and reply_count for affected campaigns
    for cid in campaign_ids:
        sent = (await db.execute(
            select(sql_func.count()).select_from(Message).where(
                Message.campaign_id == cid,
                Message.status == "sent",
            )
        )).scalar() or 0
        replies = (await db.execute(
            select(sql_func.count()).select_from(Reply).join(
                Message, Reply.message_id == Message.id
            ).where(Message.campaign_id == cid)
        )).scalar() or 0
        await db.execute(
            sql_update(Campaign)
            .where(Campaign.id == cid)
            .values(sent_count=sent, reply_count=replies)
        )

    await db.commit()
    return APIResponse(data={"deleted": counts})


# ── Activity Log ─────────────────────────────────────────────────────────────

@router.get("/activity")
async def list_activity(
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(desc(AuditLog.created_at))
        .limit(limit)
    )).scalars().all()

    user_ids = list({r.user_id for r in rows if r.user_id})
    email_map: dict[uuid.UUID, str] = {}
    if user_ids:
        users = (await db.execute(
            select(User.id, User.email).where(User.id.in_(user_ids))
        )).all()
        email_map = {u.id: u.email for u in users}

    return APIResponse(data=[
        {
            "id": str(r.id),
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "details": r.details,
            "ip_address": r.details.get("ip") if r.details else None,
            "user_agent": r.details.get("user_agent") if r.details else None,
            "user_email": email_map.get(r.user_id, "system") if r.user_id else "system",
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ])
