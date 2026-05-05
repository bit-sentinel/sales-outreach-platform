"""Unit tests for CampaignService – CRUD and state machine transitions."""

import uuid
from unittest.mock import MagicMock

import pytest

from tests.unit.conftest import scalar_result, scalars_result
from tests.factories import make_campaign
from app.schemas.campaign import (
    CampaignCreate,
    CampaignUpdate,
    SequenceStep,
    CampaignSchedule,
)


def _get_service(mock_db, tenant_id: uuid.UUID | None = None):
    from app.services.campaign_service import CampaignService
    return CampaignService(mock_db, tenant_id or uuid.uuid4())


# ── VALID_TRANSITIONS ─────────────────────────────────────────────────────────

def test_valid_transitions_complete():
    """State machine covers all expected transitions."""
    from app.services.campaign_service import CampaignService

    t = CampaignService.VALID_TRANSITIONS
    assert "active" in t["draft"]
    assert "paused" in t["active"]
    assert "completed" in t["active"]
    assert "active" in t["paused"]
    assert "archived" in t["completed"]


# ── create_campaign ───────────────────────────────────────────────────────────

async def test_create_campaign_sets_fields(mock_db):
    """create_campaign persists a Campaign with the correct attributes."""
    tid = uuid.uuid4()
    user_id = uuid.uuid4()
    svc = _get_service(mock_db, tenant_id=tid)

    data = CampaignCreate(
        name="Q2 Cvent Outreach",
        campaign_type="outbound",
        vertical="events",
        sequence=[SequenceStep(step=1, channel="email", delay_days=0)],
        schedule=CampaignSchedule(),
    )
    campaign = await svc.create_campaign(data, created_by=user_id)

    assert campaign.name == "Q2 Cvent Outreach"
    assert campaign.tenant_id == tid
    assert campaign.created_by == user_id
    # status is set server-side (server_default="draft"); Python value is None until flush
    assert campaign.status in (None, "draft")
    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited()


# ── launch / pause / resume ───────────────────────────────────────────────────

async def test_launch_campaign_transitions_draft_to_active(mock_db):
    """Launching a draft campaign moves it to 'active'."""
    campaign = make_campaign(status="draft")
    mock_db.execute.return_value = scalar_result(campaign)

    svc = _get_service(mock_db, tenant_id=campaign.tenant_id)
    result = await svc.launch_campaign(campaign.id)

    assert result.status == "active"
    assert result.launched_at is not None
    mock_db.flush.assert_awaited()


async def test_pause_active_campaign(mock_db):
    """Pausing an active campaign moves it to 'paused'."""
    campaign = make_campaign(status="active")
    mock_db.execute.return_value = scalar_result(campaign)

    svc = _get_service(mock_db, tenant_id=campaign.tenant_id)
    result = await svc.pause_campaign(campaign.id)

    assert result.status == "paused"


async def test_resume_paused_campaign(mock_db):
    """Resuming a paused campaign moves it back to 'active'."""
    campaign = make_campaign(status="paused")
    mock_db.execute.return_value = scalar_result(campaign)

    svc = _get_service(mock_db, tenant_id=campaign.tenant_id)
    result = await svc.resume_campaign(campaign.id)

    assert result.status == "active"


async def test_invalid_transition_raises(mock_db):
    """Attempting a disallowed transition raises ValueError."""
    campaign = make_campaign(status="draft")
    mock_db.execute.return_value = scalar_result(campaign)

    svc = _get_service(mock_db, tenant_id=campaign.tenant_id)
    with pytest.raises(ValueError, match="Cannot transition from 'draft' to 'paused'"):
        await svc.pause_campaign(campaign.id)


async def test_transition_not_found(mock_db):
    """Returns None when campaign does not belong to the tenant."""
    mock_db.execute.return_value = scalar_result(None)

    svc = _get_service(mock_db)
    result = await svc.launch_campaign(uuid.uuid4())

    assert result is None


# ── add_leads ─────────────────────────────────────────────────────────────────

async def test_add_leads_returns_count(mock_db):
    """add_leads inserts CampaignLead records and returns the count added."""
    campaign = make_campaign()
    # First execute: add_leads → get campaign for total update
    mock_db.execute.return_value = scalar_result(campaign)

    svc = _get_service(mock_db, tenant_id=campaign.tenant_id)
    lead_ids = [uuid.uuid4() for _ in range(3)]
    count = await svc.add_leads(campaign.id, lead_ids)

    assert count == 3
    # mock_db.add called 3 times for CampaignLead rows
    assert mock_db.add.call_count == 3
