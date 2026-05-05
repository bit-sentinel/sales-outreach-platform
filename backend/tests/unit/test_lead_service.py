"""Unit tests for LeadService – list, create, get, update, delete."""

import uuid
from unittest.mock import MagicMock

import pytest

from tests.unit.conftest import scalar_result, scalars_result
from tests.factories import make_lead, make_company
from app.schemas.lead import LeadCreate, LeadUpdate


def _get_service(mock_db, tenant_id: uuid.UUID | None = None):
    from app.services.lead_service import LeadService
    return LeadService(mock_db, tenant_id or uuid.uuid4())


# ── list_leads ────────────────────────────────────────────────────────────────

async def test_list_leads_empty(mock_db):
    """Empty database returns an empty paginated result."""
    mock_db.execute.side_effect = [
        scalars_result([]),  # count query
        scalars_result([]),  # items query
    ]
    # count query returns 0, items query returns []
    from tests.unit.conftest import scalar_result as sr
    count_result = MagicMock()
    count_result.scalar.return_value = 0
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = []
    mock_db.execute.side_effect = [count_result, items_result]

    svc = _get_service(mock_db)
    page = await svc.list_leads()

    assert page.total == 0
    assert page.items == []
    assert page.total_pages == 0
    assert not page.has_next
    assert not page.has_prev


async def test_list_leads_returns_items(mock_db):
    """Returns correctly paginated LeadResponse objects."""
    tid = uuid.uuid4()
    leads = [make_lead(tenant_id=tid) for _ in range(3)]

    count_result = MagicMock()
    count_result.scalar.return_value = 3
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = leads
    mock_db.execute.side_effect = [count_result, items_result]

    svc = _get_service(mock_db, tenant_id=tid)
    page = await svc.list_leads(page=1, page_size=25)

    assert page.total == 3
    assert len(page.items) == 3
    assert page.total_pages == 1
    assert not page.has_next


async def test_list_leads_pagination(mock_db):
    """has_next is True when more pages exist."""
    count_result = MagicMock()
    count_result.scalar.return_value = 50
    items_result = MagicMock()
    items_result.scalars.return_value.all.return_value = [make_lead() for _ in range(25)]
    mock_db.execute.side_effect = [count_result, items_result]

    svc = _get_service(mock_db)
    page = await svc.list_leads(page=1, page_size=25)

    assert page.total_pages == 2
    assert page.has_next
    assert not page.has_prev


# ── create_lead ───────────────────────────────────────────────────────────────

async def test_create_lead_adds_lead_and_activity(mock_db):
    """create_lead inserts a Lead and a LeadActivity."""
    svc = _get_service(mock_db)
    data = LeadCreate(source="cvent", tags=["event-2026"])

    lead = await svc.create_lead(data)

    assert lead.source == "cvent"
    assert lead.tags == ["event-2026"]
    # add() called for Lead + LeadActivity
    assert mock_db.add.call_count == 2
    assert mock_db.flush.call_count == 2


async def test_create_lead_assigns_tenant(mock_db):
    """The created lead inherits the service's tenant_id."""
    tid = uuid.uuid4()
    svc = _get_service(mock_db, tenant_id=tid)
    data = LeadCreate(source="manual")

    lead = await svc.create_lead(data)
    assert lead.tenant_id == tid


# ── get_lead ──────────────────────────────────────────────────────────────────

async def test_get_lead_not_found(mock_db):
    """Returns None when lead doesn't exist or belongs to another tenant."""
    mock_db.execute.return_value = scalar_result(None)

    svc = _get_service(mock_db)
    result = await svc.get_lead(uuid.uuid4())

    assert result is None


async def test_get_lead_found(mock_db):
    """Returns LeadDetailResponse when lead exists in tenant."""
    tid = uuid.uuid4()
    lead = make_lead(tenant_id=tid)
    mock_db.execute.return_value = scalar_result(lead)

    svc = _get_service(mock_db, tenant_id=tid)
    result = await svc.get_lead(lead.id)

    assert result is not None
    assert result.id == lead.id


# ── update_lead ───────────────────────────────────────────────────────────────

async def test_update_lead_patches_fields(mock_db):
    """update_lead mutates the lead object and flushes."""
    lead = make_lead(status="new")
    mock_db.execute.return_value = scalar_result(lead)

    svc = _get_service(mock_db, tenant_id=lead.tenant_id)
    result = await svc.update_lead(lead.id, LeadUpdate(status="enriched"))

    assert result is not None
    assert result.status == "enriched"
    mock_db.flush.assert_awaited()


async def test_update_lead_not_found(mock_db):
    """Returns None when lead does not belong to tenant."""
    mock_db.execute.return_value = scalar_result(None)

    svc = _get_service(mock_db)
    result = await svc.update_lead(uuid.uuid4(), LeadUpdate(status="enriched"))

    assert result is None
