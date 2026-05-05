"""Test data factories — build model instances with sensible defaults.

Uses proper SQLAlchemy constructors so _sa_instance_state is initialised
and ORM-instrumented attributes work correctly in unit tests.
"""

import uuid
from datetime import datetime, timezone

from app.models.tenant import Tenant, User
from app.models.lead import Company, Contact, Lead
from app.models.campaign import Campaign

_now = datetime(2026, 4, 6, 12, 0, 0, tzinfo=timezone.utc)


def make_tenant(
    *,
    id: uuid.UUID | None = None,
    name: str = "Acme Corp",
    slug: str = "acme-corp",
    plan: str = "pro",
) -> Tenant:
    return Tenant(
        id=id or uuid.uuid4(),
        name=name,
        slug=slug,
        plan=plan,
        settings={},
        is_active=True,
        created_at=_now,
        updated_at=_now,
    )


def make_user(
    *,
    id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    email: str = "admin@acme.com",
    first_name: str = "Alice",
    last_name: str = "Smith",
    role: str = "owner",
    password_hash: str = "$argon2id$v=19$m=65536,t=3,p=4$fakesalt$fakehash",
) -> User:
    return User(
        id=id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        email=email,
        password_hash=password_hash,
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_active=True,
        last_login_at=None,
        avatar_url=None,
        created_at=_now,
        updated_at=_now,
    )


def make_company(
    *,
    id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    name: str = "TechStart Inc",
    domain: str = "techstart.io",
    industry: str = "SaaS",
) -> Company:
    return Company(
        id=id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        name=name,
        domain=domain,
        industry=industry,
        employee_count=50,
        revenue_range="1M-10M",
        location="San Francisco, CA",
        description="A tech startup",
        logo_url=None,
        linkedin_url=None,
        website_url=f"https://{domain}",
        tags=[],
        custom_fields={},
        created_at=_now,
        updated_at=_now,
    )


def make_lead(
    *,
    id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    status: str = "new",
    source: str = "import",
) -> Lead:
    return Lead(
        id=id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        company_id=company_id,
        contact_id=contact_id,
        status=status,
        source=source,
        assigned_to=None,
        tags=[],
        custom_fields={},
        enrichment_status="pending",
        enriched_at=None,
        created_at=_now,
        updated_at=_now,
    )


def make_campaign(
    *,
    id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    name: str = "Q2 Outreach",
    status: str = "draft",
    campaign_type: str = "outbound",
) -> Campaign:
    return Campaign(
        id=id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        name=name,
        description="Test campaign",
        status=status,
        campaign_type=campaign_type,
        vertical="events",
        sequence=[{"step": 1, "channel": "email", "delay_days": 0, "ai_generate": True}],
        schedule={"timezone": "UTC", "send_days": ["monday"], "send_start_hour": 9, "send_end_hour": 17},
        sender_account_id=None,
        settings={},
        created_by=uuid.uuid4(),
        total_leads=0,
        sent_count=0,
        open_count=0,
        click_count=0,
        reply_count=0,
        bounce_count=0,
        launched_at=None,
        created_at=_now,
        updated_at=_now,
    )



