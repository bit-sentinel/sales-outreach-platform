"""Company management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.api.deps import get_tenant_id, PaginationDep
from app.schemas.common import APIResponse, PaginatedData
from app.schemas.lead import CompanyCreate, CompanyResponse, CompanyUpdate, ContactCreate, ContactResponse
from app.services.company_service import CompanyService

router = APIRouter()


@router.get("", response_model=APIResponse[PaginatedData[CompanyResponse]])
async def list_companies(
    pagination: PaginationDep = Depends(),
    search: str | None = None,
    industry: str | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CompanyService(db, tenant_id)
    result = await svc.list_companies(
        page=pagination.page, page_size=pagination.page_size,
        search=search, industry=industry,
    )
    return APIResponse(data=result)


@router.post("", response_model=APIResponse[CompanyResponse], status_code=201)
async def create_company(
    body: CompanyCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CompanyService(db, tenant_id)
    company = await svc.create_company(body)
    return APIResponse(data=CompanyResponse.model_validate(company))


@router.get("/{company_id}", response_model=APIResponse[CompanyResponse])
async def get_company(
    company_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CompanyService(db, tenant_id)
    company = await svc.get_company(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return APIResponse(data=CompanyResponse.model_validate(company))


@router.patch("/{company_id}", response_model=APIResponse[CompanyResponse])
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CompanyService(db, tenant_id)
    company = await svc.update_company(company_id, body)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return APIResponse(data=CompanyResponse.model_validate(company))


@router.delete("/{company_id}", status_code=204)
async def delete_company(
    company_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = CompanyService(db, tenant_id)
    deleted = await svc.delete_company(company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Company not found")


@router.get("/{company_id}/contacts", response_model=APIResponse[list[ContactResponse]])
async def list_company_contacts(
    company_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """List all contacts for a company."""
    from sqlalchemy import select
    from app.models.lead import Contact

    result = await db.execute(
        select(Contact).where(
            Contact.company_id == company_id,
            Contact.tenant_id == tenant_id,
        ).order_by(Contact.created_at)
    )
    contacts = result.scalars().all()
    return APIResponse(data=[ContactResponse.model_validate(c) for c in contacts])


@router.post("/{company_id}/contacts", response_model=APIResponse[ContactResponse], status_code=201)
async def create_company_contact(
    company_id: uuid.UUID,
    body: ContactCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a contact under a specific company."""
    from sqlalchemy import select
    from app.models.lead import Contact, Company

    company = await db.get(Company, company_id)
    if not company or company.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Company not found")

    contact = Contact(
        tenant_id=tenant_id,
        company_id=company_id,
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        title=body.title,
        department=body.department,
        phone=body.phone,
        linkedin_url=body.linkedin_url,
        location=body.location,
        timezone=body.timezone,
        tags=body.tags,
        custom_fields=body.custom_fields,
    )
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return APIResponse(data=ContactResponse.model_validate(contact))
