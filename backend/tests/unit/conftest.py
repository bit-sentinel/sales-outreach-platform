"""Unit-test fixtures – provide an AsyncMock database session."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession


def scalar_result(value):
    """Build a mock result object returned by session.execute()."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    r.scalar.return_value = value if isinstance(value, (int, float)) else 0
    r.scalars.return_value.all.return_value = [value] if value is not None else []
    return r


def scalars_result(items: list):
    """Build a mock result that returns a list from .scalars().all()."""
    r = MagicMock()
    r.scalar.return_value = len(items)
    r.scalars.return_value.all.return_value = items
    r.scalar_one_or_none.return_value = items[0] if items else None
    return r


@pytest.fixture
def mock_db():
    """Async SQLAlchemy session mock."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute.return_value = scalar_result(None)
    return db
