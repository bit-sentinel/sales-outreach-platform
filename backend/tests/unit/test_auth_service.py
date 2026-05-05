"""Unit tests for AuthService – register, login, token verification, refresh."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from jose import jwt

from tests.unit.conftest import scalar_result
from tests.factories import make_user, make_tenant


# ── Helpers ───────────────────────────────────────────────────────────────────

SECRET = "test-secret-key-that-is-long-enough-32chars!"
_ARGON_HASH = "$argon2id$v=19$m=65536,t=3,p=4$fakesalt$fakehashvalue"


def _get_auth(mock_db):
    """Import AuthService AFTER env vars are set."""
    from app.services.auth_service import AuthService
    return AuthService(mock_db)


# ── register ──────────────────────────────────────────────────────────────────

async def test_register_creates_tenant_and_user(mock_db):
    """Successful registration: creates tenant + user, returns token pair."""
    mock_db.execute.return_value = scalar_result(None)  # no existing user

    with patch("app.services.auth_service.argon2.hash", return_value=_ARGON_HASH):
        auth = _get_auth(mock_db)
        result = await auth.register(
            email="new@example.com",
            password="securepass",
            first_name="Jane",
            last_name="Doe",
            tenant_name="New Co",
        )

    assert result.access_token
    assert result.refresh_token
    assert result.token_type == "bearer"
    # add() called twice: tenant + user
    assert mock_db.add.call_count == 2
    assert mock_db.flush.call_count == 2


async def test_register_raises_on_duplicate_email(mock_db):
    """Registering with an existing email raises ValueError."""
    existing_user = make_user(email="dup@example.com")
    mock_db.execute.return_value = scalar_result(existing_user)

    auth = _get_auth(mock_db)
    with pytest.raises(ValueError, match="Email already registered"):
        await auth.register(
            email="dup@example.com",
            password="securepass",
            first_name="John",
            last_name="Doe",
            tenant_name="Some Co",
        )

    mock_db.add.assert_not_called()


# ── login ─────────────────────────────────────────────────────────────────────

async def test_login_success(mock_db):
    """Valid credentials: returns a TokenResponse and updates last_login_at."""
    user = make_user(email="user@example.com")
    mock_db.execute.return_value = scalar_result(user)

    with patch("app.services.auth_service.argon2.verify", return_value=True):
        auth = _get_auth(mock_db)
        result = await auth.login("user@example.com", "correctpass")

    assert result is not None
    assert result.access_token
    assert result.refresh_token
    mock_db.flush.assert_awaited()


async def test_login_wrong_password(mock_db):
    """Wrong password returns None without modifying the user."""
    user = make_user()
    mock_db.execute.return_value = scalar_result(user)

    with patch("app.services.auth_service.argon2.verify", return_value=False):
        auth = _get_auth(mock_db)
        result = await auth.login("user@example.com", "wrongpass")

    assert result is None


async def test_login_unknown_email(mock_db):
    """Unknown email returns None."""
    mock_db.execute.return_value = scalar_result(None)

    auth = _get_auth(mock_db)
    result = await auth.login("ghost@example.com", "anypass")

    assert result is None


# ── verify_access_token ───────────────────────────────────────────────────────

async def test_verify_access_token_valid(mock_db):
    """Valid token resolves to the corresponding User."""
    user = make_user()
    mock_db.execute.return_value = scalar_result(user)

    auth = _get_auth(mock_db)
    # First generate a real token via _create_tokens
    token_resp = auth._create_tokens(user)

    result = await auth.verify_access_token(token_resp.access_token)
    assert result is user


async def test_verify_access_token_invalid(mock_db):
    """Malformed / tampered token returns None."""
    auth = _get_auth(mock_db)
    result = await auth.verify_access_token("not.a.valid.jwt")
    assert result is None


async def test_verify_access_token_user_not_found(mock_db):
    """Token valid but user deleted → None."""
    user = make_user()
    auth = _get_auth(mock_db)
    token = auth._create_tokens(user).access_token

    mock_db.execute.return_value = scalar_result(None)  # user gone
    result = await auth.verify_access_token(token)
    assert result is None


# ── refresh_tokens ────────────────────────────────────────────────────────────

async def test_refresh_tokens_valid(mock_db):
    """Valid refresh token returns a new token pair."""
    user = make_user()
    auth = _get_auth(mock_db)
    refresh_token = auth._create_tokens(user).refresh_token

    mock_db.execute.return_value = scalar_result(user)
    result = await auth.refresh_tokens(refresh_token)

    assert result is not None
    assert result.access_token != refresh_token


async def test_refresh_tokens_rejects_access_token(mock_db):
    """Passing an access token to refresh endpoint returns None."""
    user = make_user()
    auth = _get_auth(mock_db)
    access_token = auth._create_tokens(user).access_token

    result = await auth.refresh_tokens(access_token)
    assert result is None
