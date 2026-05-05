"""
Company service – CRUD operations.
"""

import uuid
from math import ceil

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import Company
from app.schemas.lead import CompanyCreate, CompanyResponse, CompanyUpdate
from app.schemas.common import PaginatedData


class CompanyService:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def list_companies(
        self,
        page: int = 1,
        page_size: int = 25,
        search: str | None = None,
        industry: str | None = None,
    ) -> PaginatedData[CompanyResponse]:
        query = select(Company).where(Company.tenant_id == self.tenant_id)

        if industry:
            query = query.where(Company.industry == industry)
        if search:
            query = query.where(Company.name.ilike(f"%{search}%"))

        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        query = query.order_by(Company.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        companies = result.scalars().all()

        return PaginatedData(
            items=[CompanyResponse.model_validate(c) for c in companies],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=ceil(total / page_size) if total > 0 else 0,
            has_next=page * page_size < total,
            has_prev=page > 1,
        )

    async def create_company(self, data: CompanyCreate) -> Company:
        company = Company(
            tenant_id=self.tenant_id,
            **data.model_dump(),
        )
        self.db.add(company)
        await self.db.flush()
        return company

    async def get_company(self, company_id: uuid.UUID) -> Company | None:
        result = await self.db.execute(
            select(Company).where(
                Company.id == company_id, Company.tenant_id == self.tenant_id
            )
        )
        return result.scalar_one_or_none()

    async def update_company(
        self, company_id: uuid.UUID, data: CompanyUpdate
    ) -> Company | None:
        company = await self.get_company(company_id)
        if not company:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(company, key, value)
        await self.db.flush()
        return company

    async def delete_company(self, company_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            delete(Company).where(
                Company.id == company_id, Company.tenant_id == self.tenant_id
            )
        )
        return result.rowcount > 0
