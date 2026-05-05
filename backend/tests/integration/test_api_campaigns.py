"""Integration tests for campaign endpoints – /api/v1/campaigns"""

import pytest
from tests.integration.conftest import skip_no_db

pytestmark = [pytest.mark.asyncio, skip_no_db]


_CAMPAIGN_PAYLOAD = {
    "name": "Q2 Cvent Outreach",
    "campaign_type": "outbound",
    "vertical": "events",
    "sequence": [
        {"step": 1, "channel": "email", "delay_days": 0, "ai_generate": True},
        {"step": 2, "channel": "email", "delay_days": 3, "ai_generate": True},
    ],
    "schedule": {
        "timezone": "UTC",
        "send_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "send_start_hour": 9,
        "send_end_hour": 17,
    },
}


# ── GET /campaigns ────────────────────────────────────────────────────────────

async def test_list_campaigns_requires_auth(client):
    resp = await client.get("/api/v1/campaigns")
    assert resp.status_code == 401


async def test_list_campaigns_empty(client, auth_headers):
    resp = await client.get("/api/v1/campaigns", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


# ── POST /campaigns ───────────────────────────────────────────────────────────

async def test_create_campaign(client, auth_headers):
    resp = await client.post(
        "/api/v1/campaigns",
        json=_CAMPAIGN_PAYLOAD,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["name"] == "Q2 Cvent Outreach"
    assert data["status"] == "draft"
    assert data["id"]


async def test_create_campaign_missing_sequence_returns_422(client, auth_headers):
    resp = await client.post(
        "/api/v1/campaigns",
        json={"name": "No Sequence"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ── GET /campaigns/{id} ───────────────────────────────────────────────────────

async def test_get_campaign(client, auth_headers):
    campaign_id = (
        await client.post("/api/v1/campaigns", json=_CAMPAIGN_PAYLOAD, headers=auth_headers)
    ).json()["data"]["id"]

    resp = await client.get(f"/api/v1/campaigns/{campaign_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == campaign_id


async def test_get_campaign_not_found(client, auth_headers):
    import uuid
    resp = await client.get(f"/api/v1/campaigns/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


# ── Campaign lifecycle ────────────────────────────────────────────────────────

async def test_launch_then_pause_campaign(client, auth_headers):
    campaign_id = (
        await client.post("/api/v1/campaigns", json=_CAMPAIGN_PAYLOAD, headers=auth_headers)
    ).json()["data"]["id"]

    # Launch: draft → active
    launch = await client.post(
        f"/api/v1/campaigns/{campaign_id}/launch", headers=auth_headers
    )
    assert launch.status_code == 200
    assert launch.json()["data"]["status"] == "active"

    # Pause: active → paused
    pause = await client.post(
        f"/api/v1/campaigns/{campaign_id}/pause", headers=auth_headers
    )
    assert pause.status_code == 200
    assert pause.json()["data"]["status"] == "paused"

    # Resume: paused → active
    resume = await client.post(
        f"/api/v1/campaigns/{campaign_id}/resume", headers=auth_headers
    )
    assert resume.status_code == 200
    assert resume.json()["data"]["status"] == "active"


async def test_invalid_transition_returns_400(client, auth_headers):
    """Pausing a draft campaign should return 400."""
    campaign_id = (
        await client.post("/api/v1/campaigns", json=_CAMPAIGN_PAYLOAD, headers=auth_headers)
    ).json()["data"]["id"]

    resp = await client.post(
        f"/api/v1/campaigns/{campaign_id}/pause", headers=auth_headers
    )
    assert resp.status_code == 400
