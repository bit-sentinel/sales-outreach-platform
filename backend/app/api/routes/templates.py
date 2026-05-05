"""Email template CRUD endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.api.deps import get_current_user, get_tenant_id, PaginationDep
from app.schemas.common import APIResponse, PaginatedData
from app.schemas.campaign import TemplateCreate, TemplateResponse

router = APIRouter()


@router.get("", response_model=APIResponse[PaginatedData[TemplateResponse]])
async def list_templates(
    pagination: PaginationDep = Depends(),
    category: str | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    return APIResponse(data=PaginatedData(
        items=[], total=0, page=pagination.page,
        page_size=pagination.page_size, total_pages=0,
        has_next=False, has_prev=False,
    ))


@router.post("", response_model=APIResponse[TemplateResponse], status_code=201)
async def create_template(
    body: TemplateCreate,
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{template_id}", response_model=APIResponse[TemplateResponse])
async def get_template(
    template_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.patch("/{template_id}", response_model=APIResponse[TemplateResponse])
async def update_template(
    template_id: uuid.UUID,
    body: TemplateCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=501, detail="Not implemented")


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=501, detail="Not implemented")
