"""Integration tests for leads endpoints – /api/v1/leads and /api/v1/companies"""

import pytest
from tests.integration.conftest import skip_no_db

pytestmark = [pytest.mark.asyncio, skip_no_db]


# ── Helper ────────────────────────────────────────────────────────────────────

async def _create_company(client, headers, *, name="TechCo", domain="techco.io"):
    resp = await client.post(
        "/api/v1/companies",
        json={"name": name, "domain": domain, "industry": "SaaS"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


# ── GET /leads ────────────────────────────────────────────────────────────────

async def test_list_leads_requires_auth(client):
    resp = await client.get("/api/v1/leads")
    assert resp.status_code == 401


async def test_list_leads_empty(client, auth_headers):
    resp = await client.get("/api/v1/leads", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == 0
    assert body["items"] == []


# ── POST /leads ───────────────────────────────────────────────────────────────

async def test_create_lead_minimal(client, auth_headers):
    resp = await client.post(
        "/api/v1/leads",
        json={"source": "cvent"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    lead = resp.json()["data"]
    assert lead["source"] == "cvent"
    assert lead["status"] == "new"
    assert lead["id"]


async def test_create_lead_with_company(client, auth_headers):
    company = await _create_company(client, auth_headers)

    resp = await client.post(
        "/api/v1/leads",
        json={"source": "import", "company_id": company["id"], "tags": ["q2", "hot"]},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    lead = resp.json()["data"]
    assert lead["company_id"] == company["id"]


# ── GET /leads/{id} ───────────────────────────────────────────────────────────

async def test_get_lead_found(client, auth_headers):
    created = (
        await client.post("/api/v1/leads", json={"source": "test"}, headers=auth_headers)
    ).json()["data"]

    resp = await client.get(f"/api/v1/leads/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == created["id"]


async def test_get_lead_not_found(client, auth_headers):
    import uuid
    resp = await client.get(f"/api/v1/leads/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


# ── PUT /leads/{id} ───────────────────────────────────────────────────────────

async def test_update_lead_status(client, auth_headers):
    lead_id = (
        await client.post("/api/v1/leads", json={"source": "update-test"}, headers=auth_headers)
    ).json()["data"]["id"]

    resp = await client.put(
        f"/api/v1/leads/{lead_id}",
        json={"status": "enriched"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "enriched"


# ── DELETE /leads/{id} ────────────────────────────────────────────────────────

async def test_delete_lead(client, auth_headers):
    lead_id = (
        await client.post("/api/v1/leads", json={"source": "delete-test"}, headers=auth_headers)
    ).json()["data"]["id"]

    resp = await client.delete(f"/api/v1/leads/{lead_id}", headers=auth_headers)
    assert resp.status_code in (200, 204)

    # Confirm gone
    get = await client.get(f"/api/v1/leads/{lead_id}", headers=auth_headers)
    assert get.status_code == 404


# ── Tenant isolation ─────────────────────────────────────────────────────────

async def test_lead_tenant_isolation(client):
    """A lead created by tenant-A is invisible to tenant-B."""
    async def _register_and_get_headers(email: str, tenant: str) -> dict:
        r = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "IsolationPass1!",
                "first_name": "T",
                "last_name": "T",
                "tenant_name": tenant,
            },
        )
        token = r.json()["data"]["access_token"]
        return {"Authorization": f"Bearer {token}"}

    headers_a = await _register_and_get_headers("tenanta@example.com", "Tenant A")
    headers_b = await _register_and_get_headers("tenantb@example.com", "Tenant B")

    lead_id = (
        await client.post("/api/v1/leads", json={"source": "iso"}, headers=headers_a)
    ).json()["data"]["id"]

    resp = await client.get(f"/api/v1/leads/{lead_id}", headers=headers_b)
    assert resp.status_code == 404
