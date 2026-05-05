"""Message and email event endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.api.deps import get_tenant_id, PaginationDep
from app.schemas.common import APIResponse, PaginatedData
from app.schemas.campaign import MessageResponse

router = APIRouter()


@router.get("", response_model=APIResponse[PaginatedData[MessageResponse]])
async def list_messages(
    pagination: PaginationDep = Depends(),
    campaign_id: uuid.UUID | None = None,
    lead_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    # Service call placeholder
    return APIResponse(data=PaginatedData(
        items=[], total=0, page=pagination.page,
        page_size=pagination.page_size, total_pages=0,
        has_next=False, has_prev=False,
    ))


@router.get("/{message_id}", response_model=APIResponse[MessageResponse])
async def get_message(
    message_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=501, detail="Not implemented")
