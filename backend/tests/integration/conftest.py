"""
Integration-test fixtures.

Requires a running PostgreSQL instance. Set TEST_DATABASE_URL or ensure:
  postgres is reachable at postgresql+asyncpg://outreach:outreach@localhost:5432/outreachai_test

Tests in this package are automatically skipped when the database is
unreachable (detected at fixture-setup time).
"""

import os
import asyncio

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://outreach:outreach@localhost:5432/outreachai_test",
)


def _db_available() -> bool:
    """Quick TCP probe to see if postgres is up."""
    import socket
    host = "localhost"
    port = 5432
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


skip_no_db = pytest.mark.skipif(
    not _db_available(),
    reason="PostgreSQL not available – skipping integration tests",
)


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create tables once per test session, drop after."""
    from app.db.base import Base

    engine = create_async_engine(TEST_DB_URL, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """
    Function-scoped session wrapped in a SAVEPOINT that is rolled back
    after each test, keeping the DB clean without re-creating tables.
    """
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    """AsyncClient wired to the FastAPI app with the test DB session."""
    from app.main import create_app
    from app.db import get_db

    app = create_app()

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client):
    """Register a fresh user and return Authorization headers."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "testuser@example.com",
            "password": "SecurePass123!",
            "first_name": "Test",
            "last_name": "User",
            "tenant_name": "Test Tenant",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
