"""Integration tests for auth endpoints – /api/v1/auth/*"""

import pytest
from tests.integration.conftest import skip_no_db

pytestmark = [pytest.mark.asyncio, skip_no_db]


# ── POST /auth/register ───────────────────────────────────────────────────────

async def test_register_returns_201_with_tokens(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "SecurePass123!",
            "first_name": "Alice",
            "last_name": "Smith",
            "tenant_name": "Alice Corp",
        },
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"


async def test_register_duplicate_email_returns_422_or_400(client):
    payload = {
        "email": "dup@example.com",
        "password": "SecurePass123!",
        "first_name": "X",
        "last_name": "Y",
        "tenant_name": "Corp",
    }
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code in (400, 409, 422)


async def test_register_rejects_weak_password(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "123",  # too short
            "first_name": "W",
            "last_name": "P",
            "tenant_name": "Corp",
        },
    )
    assert resp.status_code == 422


# ── POST /auth/login ──────────────────────────────────────────────────────────

async def test_login_valid_credentials(client):
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "SecurePass123!",
            "first_name": "L",
            "last_name": "U",
            "tenant_name": "Login Corp",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "SecurePass123!"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


async def test_login_wrong_password_returns_401(client):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrong@example.com",
            "password": "CorrectPass123!",
            "first_name": "W",
            "last_name": "P",
            "tenant_name": "WrongCorp",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "BadPass999!"},
    )
    assert resp.status_code == 401


async def test_login_unknown_email_returns_401(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "AnyPass123!"},
    )
    assert resp.status_code == 401


# ── GET /auth/me ──────────────────────────────────────────────────────────────

async def test_get_me_with_valid_token(client, auth_headers):
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["email"] == "testuser@example.com"
    assert data["first_name"] == "Test"


async def test_get_me_without_token_returns_401(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


# ── POST /auth/refresh ────────────────────────────────────────────────────────

async def test_refresh_token_returns_new_tokens(client):
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@example.com",
            "password": "RefreshPass123!",
            "first_name": "R",
            "last_name": "T",
            "tenant_name": "Refresh Corp",
        },
    )
    refresh_token = reg.json()["data"]["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["access_token"]


async def test_refresh_with_garbage_token_returns_401(client):
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not.a.valid.token"},
    )
    assert resp.status_code == 401
