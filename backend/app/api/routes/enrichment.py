"""Enrichment endpoints – trigger, status, results."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.api.deps import get_current_user, get_tenant_id
from app.schemas.common import APIResponse
from app.schemas.lead import EnrichmentJobResponse, EnrichmentRequest
from app.services.enrichment_service import EnrichmentService
from app.api.audit import log_action

router = APIRouter()


@router.get("/jobs", response_model=APIResponse[list[EnrichmentJobResponse]])
async def list_enrichment_jobs(
    limit: int = Query(50, ge=1, le=200),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Return recent enrichment jobs with lead name for the current tenant."""
    from app.models.lead import EnrichmentJob, Lead, Contact

    rows = (await db.execute(
        select(EnrichmentJob)
        .where(EnrichmentJob.tenant_id == tenant_id)
        .order_by(desc(EnrichmentJob.created_at))
        .limit(limit)
    )).scalars().all()

    if not rows:
        return APIResponse(data=[])

    # Drop orphaned pending jobs: for each lead, if any completed/failed job was
    # created after a pending job, that pending job is from a superseded batch.
    from collections import defaultdict
    latest_completed: dict = {}
    for r in rows:
        if r.status in ("completed", "failed") and r.created_at:
            prev = latest_completed.get(r.lead_id)
            if prev is None or r.created_at > prev:
                latest_completed[r.lead_id] = r.created_at

    rows = [
        r for r in rows
        if not (
            r.status == "pending"
            and r.created_at
            and r.lead_id in latest_completed
            and r.created_at < latest_completed[r.lead_id]
        )
    ]

    # Resolve lead names in one query
    lead_ids = list({r.lead_id for r in rows})
    lead_contacts = (await db.execute(
        select(Lead.id, Contact.first_name, Contact.last_name)
        .join(Contact, Contact.id == Lead.contact_id, isouter=True)
        .where(Lead.id.in_(lead_ids))
    )).all()
    name_map = {
        row[0]: f"{row[1] or ''} {row[2] or ''}".strip() or "Unknown"
        for row in lead_contacts
    }

    items = []
    for r in rows:
        item = EnrichmentJobResponse.model_validate(r)
        item.lead_name = name_map.get(r.lead_id)
        items.append(item)

    return APIResponse(data=items)


@router.post("/enrich", status_code=202)
async def trigger_enrichment(
    body: EnrichmentRequest,
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Trigger async enrichment for a batch of leads."""
    svc = EnrichmentService(db, tenant_id)
    job_ids = await svc.enrich_leads(body.lead_ids, body.enrichment_types)
    await log_action(db, tenant_id=tenant_id, user_id=current_user.id,
                     action="leads.enrich", resource_type="enrichment_job",
                     details={"lead_count": len(body.lead_ids),
                              "types": body.enrichment_types})
    return APIResponse(data={"jobs_created": len(job_ids), "job_ids": job_ids})


@router.post("/enrich-all", status_code=202)
async def trigger_enrich_all(
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Trigger enrichment for every lead in the tenant."""
    from app.models.lead import Lead
    lead_ids = (await db.execute(
        select(Lead.id).where(Lead.tenant_id == tenant_id)
    )).scalars().all()
    if not lead_ids:
        return APIResponse(data={"jobs_created": 0, "job_ids": []})
    svc = EnrichmentService(db, tenant_id)
    job_ids = await svc.enrich_leads(list(lead_ids), ["web_research", "company", "scoring"])
    await log_action(db, tenant_id=tenant_id, user_id=current_user.id,
                     action="leads.enrich", resource_type="enrichment_job",
                     details={"lead_count": len(lead_ids), "types": ["web_research", "company", "scoring"]})
    return APIResponse(data={"jobs_created": len(job_ids), "lead_count": len(lead_ids), "job_ids": job_ids})


@router.post("/rescore-all", status_code=202)
async def trigger_rescore_all(
    current_user=Depends(get_current_user),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Re-score all enriched leads using cached signals (no enrichment agents run)."""
    from app.models.lead import Lead
    from app.tasks.v3.stage_tasks import rescore_lead_v3

    lead_ids = (await db.execute(
        select(Lead.id)
        .where(Lead.tenant_id == tenant_id, Lead.enrichment_status == "enriched")
    )).scalars().all()

    if not lead_ids:
        return APIResponse(data={"queued": 0, "lead_ids": []})

    for lid in lead_ids:
        rescore_lead_v3.delay(str(lid))

    await log_action(db, tenant_id=tenant_id, user_id=current_user.id,
                     action="leads.rescore_all", resource_type="lead",
                     details={"lead_count": len(lead_ids)})

    return APIResponse(data={"queued": len(lead_ids), "lead_ids": [str(i) for i in lead_ids]})


@router.get("/jobs/{job_id}", response_model=APIResponse[EnrichmentJobResponse])
async def get_enrichment_job(
    job_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    svc = EnrichmentService(db, tenant_id)
    job = await svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Enrichment job not found")
    return APIResponse(data=EnrichmentJobResponse.model_validate(job))


@router.get("/lead/{lead_id}/insights")
async def get_lead_insights(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Get all AI insights for a lead."""
    svc = EnrichmentService(db, tenant_id)
    insights = await svc.get_lead_insights(lead_id)
    return APIResponse(data=insights)


@router.get("/lead/{lead_id}/research")
async def get_lead_research(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Get all web research data for a lead."""
    svc = EnrichmentService(db, tenant_id)
    research = await svc.get_lead_research(lead_id)
    return APIResponse(data=research)


@router.get("/lead/{lead_id}/score")
async def get_lead_score(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest AI-generated lead score."""
    svc = EnrichmentService(db, tenant_id)
    score = await svc.get_latest_score(lead_id)
    if not score:
        raise HTTPException(status_code=404, detail="No score found for this lead")
    return APIResponse(data=score)


@router.get("/lead/{lead_id}/data")
async def get_lead_enrichment_data(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Get structured enrichment data for a lead (company/contact intel)."""
    svc = EnrichmentService(db, tenant_id)
    data = await svc.get_enrichment_data(lead_id)
    return APIResponse(data=data)


@router.get("/lead/{lead_id}/outreach")
async def get_lead_outreach(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Get v3 outreach intelligence package for a lead."""
    svc = EnrichmentService(db, tenant_id)
    outreach = await svc.get_lead_outreach(lead_id)
    if not outreach:
        raise HTTPException(status_code=404, detail="No outreach intelligence found for this lead")
    return APIResponse(data=outreach)
