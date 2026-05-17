"""FastAPI dependencies – auth, DB session, tenant context, pagination."""

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.auth_service import AuthService


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
):
    """Extract and validate JWT from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    token = authorization.removeprefix("Bearer ")
    auth_service = AuthService(db)
    user = await auth_service.verify_access_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return user


async def get_tenant_id(
    current_user=Depends(get_current_user),
) -> uuid.UUID:
    """Extract tenant_id from the authenticated user."""
    return current_user.tenant_id


def require_role(*roles: str):
    """Dependency factory: require user to have one of the given roles."""
    async def _check_role(current_user=Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(roles)}",
            )
        return current_user
    return _check_role


class PaginationDep:
    """Parse and validate pagination query params."""

    def __init__(self, page: int = 1, page_size: int = 25):
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 1
        if page_size > 1000:
            page_size = 1000
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size
