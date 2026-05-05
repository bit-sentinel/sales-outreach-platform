"""Lead management endpoints – CRUD, import, bulk operations, search."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.api.deps import get_current_user, get_tenant_id, PaginationDep
from app.schemas.common import APIResponse, PaginatedData
from app.schemas.lead import (
    LeadCreate,
    LeadDetailResponse,
    LeadResponse,
    LeadUpdate,
    ImportBatchResponse,
)
from app.services.lead_service import LeadService
from app.api.audit import log_action

router = APIRouter()


@router.get("", response_model=APIResponse[PaginatedData[LeadResponse]])
async def list_leads(
    pagination: PaginationDep = Depends(),
    status_filter: str | None = Query(None, alias="status"),
    source: str | None = None,
    search: str | None = None,
    tags: list[str] | None = Query(None),
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = LeadService(db, tenant_id)
    result = await svc.list_leads(
        page=pagination.page,
        page_size=pagination.page_size,
        status=status_filter,
        source=source,
        search=search,
        tags=tags,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return APIResponse(data=result)


@router.post("", response_model=APIResponse[LeadResponse], status_code=201)
async def create_lead(
    body: LeadCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = LeadService(db, tenant_id)
    lead = await svc.create_lead(body)
    await db.refresh(lead, ["company", "contact"])
    return APIResponse(data=LeadResponse.model_validate(lead))


@router.get("/{lead_id}", response_model=APIResponse[LeadDetailResponse])
async def get_lead(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = LeadService(db, tenant_id)
    lead = await svc.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return APIResponse(data=lead)


@router.get("/{lead_id}/activity")
async def get_lead_activity(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Return a merged, chronological activity timeline for a lead."""
    from datetime import datetime as dt
    from sqlalchemy import select, desc
    from app.models.campaign import Message, Campaign, CampaignLead
    from app.models.lead import EnrichmentJob

    events: list[dict] = []

    # ── Email messages ──────────────────────────────────────────────────────
    msgs = (await db.execute(
        select(Message, Campaign.name)
        .outerjoin(Campaign, Campaign.id == Message.campaign_id)
        .where(Message.lead_id == lead_id, Message.tenant_id == tenant_id)
        .order_by(desc(Message.created_at))
        .limit(100)
    )).all()

    for msg, campaign_name in msgs:
        events.append({
            "id": str(msg.id),
            "type": "email",
            "ts": (msg.sent_at or msg.created_at).isoformat(),
            "status": msg.status,
            "subject": msg.subject,
            "campaign_name": campaign_name,
            "sequence_step": msg.sequence_step,
            "ai_generated": msg.ai_generated,
            "error": msg.error_message,
        })

    # ── Enrichment jobs ─────────────────────────────────────────────────────
    all_jobs = (await db.execute(
        select(EnrichmentJob)
        .where(EnrichmentJob.lead_id == lead_id, EnrichmentJob.tenant_id == tenant_id)
        .order_by(desc(EnrichmentJob.created_at))
        .limit(200)
    )).scalars().all()

    # Find the timestamp of the most recent completed/failed job for this lead.
    # Any pending job created before that timestamp is orphaned (its batch was superseded).
    latest_completed_at = None
    for j in all_jobs:
        if j.status in ("completed", "failed") and j.created_at:
            if latest_completed_at is None or j.created_at > latest_completed_at:
                latest_completed_at = j.created_at

    # Deduplicate: skip pending if a newer completed/failed run exists for same type,
    # OR if any completed job was created after this pending job (orphaned from old batch).
    seen: dict[str, str] = {}   # job_type -> best status so far
    jobs = []
    for job in all_jobs:  # already newest-first
        # Drop orphaned pending jobs superseded by a later completed batch
        if (job.status == "pending" and latest_completed_at and
                job.created_at and job.created_at < latest_completed_at):
            continue
        prev = seen.get(job.job_type)
        if prev is None:
            seen[job.job_type] = job.status
            jobs.append(job)
        elif job.status == "pending" and prev in ("completed", "failed", "processing"):
            continue
        else:
            jobs.append(job)

    JOB_LABEL = {"web_research": "Web Research", "company": "Company Intel", "scoring": "AI Scoring", "contact": "Contact Data"}
    for job in jobs:
        events.append({
            "id": str(job.id),
            "type": "enrichment",
            "ts": (job.completed_at or job.created_at).isoformat(),
            "status": job.status,
            "job_type": job.job_type,
            "job_label": JOB_LABEL.get(job.job_type, job.job_type),
            "duration_ms": job.duration_ms,
            "tokens_used": job.tokens_used,
            "error": job.error,
        })

    # ── Campaign membership ─────────────────────────────────────────────────
    cl_rows = (await db.execute(
        select(CampaignLead, Campaign.name)
        .join(Campaign, Campaign.id == CampaignLead.campaign_id)
        .where(CampaignLead.lead_id == lead_id, CampaignLead.tenant_id == tenant_id)
        .order_by(desc(CampaignLead.created_at))
    )).all()

    for cl, campaign_name in cl_rows:
        events.append({
            "id": str(cl.id),
            "type": "campaign",
            "ts": cl.created_at.isoformat(),
            "status": cl.status,
            "campaign_name": campaign_name,
            "current_step": cl.current_step,
        })

    # Sort all events newest-first
    events.sort(key=lambda e: e["ts"], reverse=True)
    return APIResponse(data=events)


@router.patch("/{lead_id}", response_model=APIResponse[LeadResponse])
async def update_lead(
    lead_id: uuid.UUID,
    body: LeadUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = LeadService(db, tenant_id)
    lead = await svc.update_lead(lead_id, body)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return APIResponse(data=LeadResponse.model_validate(lead))


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = LeadService(db, tenant_id)
    deleted = await svc.delete_lead(lead_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Lead not found")


@router.post("/import", response_model=APIResponse[ImportBatchResponse], status_code=202)
async def import_leads(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.endswith((".csv", ".xlsx")):
        raise HTTPException(status_code=400, detail="Only CSV and XLSX files are supported")
    svc = LeadService(db, tenant_id)
    batch = await svc.start_import(file, user_id=current_user.id)
    await log_action(db, tenant_id=tenant_id, user_id=current_user.id,
                     action="leads.import", resource_type="import_batch",
                     resource_id=str(batch.id),
                     details={"file_name": file.filename,
                              "rows_imported": getattr(batch, 'total_rows', None)})
    return APIResponse(data=ImportBatchResponse.model_validate(batch))


@router.post("/bulk/tag")
async def bulk_tag_leads(
    lead_ids: list[uuid.UUID],
    tags: list[str],
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = LeadService(db, tenant_id)
    count = await svc.bulk_add_tags(lead_ids, tags)
    return APIResponse(data={"updated": count})


@router.post("/bulk/assign")
async def bulk_assign_leads(
    lead_ids: list[uuid.UUID],
    assigned_to: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = LeadService(db, tenant_id)
    count = await svc.bulk_assign(lead_ids, assigned_to)
    return APIResponse(data={"updated": count})
