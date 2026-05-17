"""
Enrichment Celery tasks – web research, company enrichment, scoring.
"""

from app.celery_app import celery_app


def _make_session_factory():
    """Create a fresh engine + session factory for this OS process / event loop."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import get_settings
    settings = get_settings()
    engine = create_async_engine(
        str(settings.database_url),
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _apply_identity_profile(company, contact, identity_profile: dict) -> None:
    """Back-fill company/contact records from a resolved Apollo identity profile."""
    if not identity_profile:
        return

    organization = identity_profile.get("organization") or {}
    if contact:
        first_name = identity_profile.get("first_name")
        last_name = identity_profile.get("last_name")
        if first_name and not contact.first_name:
            contact.first_name = first_name
        if last_name and not contact.last_name:
            contact.last_name = last_name
        if identity_profile.get("title") and not contact.title:
            contact.title = identity_profile["title"]
        if identity_profile.get("department") and not contact.department:
            value = identity_profile["department"]
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value if item)
            contact.department = str(value)
        if identity_profile.get("phone") and not contact.phone:
            contact.phone = identity_profile["phone"]
        if identity_profile.get("linkedin_url") and not contact.linkedin_url:
            contact.linkedin_url = identity_profile["linkedin_url"]

    if company:
        domain = organization.get("domain") or organization.get("website_url")
        if domain and not company.domain:
            company.domain = str(domain).replace("https://", "").replace("http://", "").strip("/")
        if organization.get("linkedin_url") and not company.linkedin_url:
            company.linkedin_url = organization["linkedin_url"]
        if organization.get("website_url") and not company.website_url:
            company.website_url = organization["website_url"]
        if organization.get("employee_count") and not company.employee_count:
            try:
                company.employee_count = int(organization["employee_count"])
            except (TypeError, ValueError):
                pass
        industry = organization.get("industry")
        if industry and not company.industry:
            if isinstance(industry, list):
                industry = ", ".join(str(item) for item in industry if item)
            company.industry = str(industry)
        description = organization.get("short_description")
        if description and not company.description:
            company.description = description


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, queue="enrichment")
def run_enrichment_pipeline(self, lead_id: str, tenant_id: str, job_ids: list):
    """
    Run the full enrichment pipeline for one lead: web_research → company → scoring.
    job_ids is a dict mapping job_type -> job_id (as strings).
    """
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_pipeline_async(lead_id, tenant_id, job_ids))
    except Exception as exc:
        raise self.retry(exc=exc)
    finally:
        loop.close()


async def _run_pipeline_async(lead_id: str, tenant_id: str, job_ids: dict):
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy import select

    async_session_factory = _make_session_factory()
    from app.models.lead import (
        AIInsight, Company, Contact, EnrichmentData,
        EnrichmentJob, Lead, LeadScore, ResearchData,
    )

    lead_uuid = uuid.UUID(lead_id)
    tenant_uuid = uuid.UUID(tenant_id)

    async with async_session_factory() as db:
        # ── Load jobs map ───────────────────────────────────────────
        job_map: dict[str, EnrichmentJob] = {}
        for jtype, jid in job_ids.items():
            res = await db.execute(
                select(EnrichmentJob).where(EnrichmentJob.id == uuid.UUID(jid))
            )
            job = res.scalar_one_or_none()
            if job:
                job_map[jtype] = job

        # ── Load lead ───────────────────────────────────────────────
        res = await db.execute(select(Lead).where(Lead.id == lead_uuid))
        lead = res.scalar_one_or_none()
        if not lead:
            return

        lead.enrichment_status = "enriching"
        await db.commit()

        # ── Load company + contact ──────────────────────────────────
        company = None
        contact = None
        if lead.company_id:
            res = await db.execute(select(Company).where(Company.id == lead.company_id))
            company = res.scalar_one_or_none()
        if lead.contact_id:
            res = await db.execute(select(Contact).where(Contact.id == lead.contact_id))
            contact = res.scalar_one_or_none()

        contact_full_name = (
            f"{contact.first_name} {contact.last_name}".strip() if contact else None
        )

        identity_profile: dict = {}
        if contact and contact.email:
            from app.config import get_settings
            from app.tools.apollo import enrich_person_by_email

            settings = get_settings()
            if settings.apollo_api_key:
                identity_profile = await enrich_person_by_email(contact.email, settings.apollo_api_key)
                if identity_profile:
                    _apply_identity_profile(company, contact, identity_profile)
                    db.add(EnrichmentData(
                        tenant_id=tenant_uuid,
                        lead_id=lead_uuid,
                        data_type="identity_profile",
                        provider="apollo",
                        data=identity_profile,
                        confidence=1.0,
                    ))
                    await db.commit()

                    if company and company.domain:
                        company.domain = company.domain.replace("https://", "").replace("http://", "").strip("/")
                    contact_full_name = (
                        f"{contact.first_name} {contact.last_name}".strip() if contact else None
                    )

        # ── Step 1: Web Research ────────────────────────────────────
        research_output: dict = {}
        if "web_research" in job_map:
            job = job_map["web_research"]
            job.status = "running"
            await db.commit()
            try:
                from app.agents.research_agent import ResearchAgent
                agent = ResearchAgent()
                research_output = await agent.run(
                    lead_id=lead_id,
                    tenant_id=tenant_id,
                    company_name=company.name if company else None,
                    domain=company.domain if company else None,
                    contact_name=contact_full_name,
                    linkedin_url=contact.linkedin_url if contact else None,
                )
                # Persist ResearchData record
                if research_output and not research_output.get("parse_error"):
                    db.add(ResearchData(
                        tenant_id=tenant_uuid,
                        lead_id=lead_uuid,
                        source="ai_synthesis",
                        title=f"Research – {company.name if company else 'Lead'}",
                        content=research_output.get("company_summary", ""),
                        relevance_score=research_output.get("relevance_score"),
                        metadata_=research_output,
                    ))
                    for page in research_output.get("cvent_event_pages", [])[:3]:
                        db.add(ResearchData(
                            tenant_id=tenant_uuid,
                            lead_id=lead_uuid,
                            source="cvent_event_page",
                            url=page.get("url"),
                            title=page.get("title") or page.get("name") or "Cvent event page",
                            content=page.get("note") or page.get("snippet") or "",
                            relevance_score=research_output.get("relevance_score"),
                            metadata_=page,
                        ))
                    db.add(AIInsight(
                        tenant_id=tenant_uuid,
                        lead_id=lead_uuid,
                        insight_type="research_summary",
                        content=research_output.get("company_summary", ""),
                        confidence=research_output.get("relevance_score"),
                        source_data=research_output,
                        model_used="claude",
                    ))
                job.status = "completed"
                job.output_data = research_output
                job.completed_at = datetime.now(timezone.utc)
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
            await db.commit()

        # ── Step 2: Company Enrichment ──────────────────────────────
        enrichment_output: dict = {}
        if "company" in job_map:
            job = job_map["company"]
            job.status = "running"
            await db.commit()
            try:
                from app.agents.enrichment_agent import EnrichmentAgent
                agent = EnrichmentAgent()
                raw_data = {
                    "company_name": company.name if company else None,
                    "domain": company.domain if company else None,
                    "contact_name": contact_full_name,
                    "contact_email": contact.email if contact else None,
                    "contact_title": contact.title if contact else None,
                    "linkedin_url": contact.linkedin_url if contact else None,
                    "identity_profile": identity_profile or None,
                }
                enrichment_output = await agent.run(
                    lead_id=lead_id,
                    tenant_id=tenant_id,
                    raw_data=raw_data,
                    research_data=research_output or None,
                )
                if enrichment_output and not enrichment_output.get("parse_error"):
                    db.add(EnrichmentData(
                        tenant_id=tenant_uuid,
                        lead_id=lead_uuid,
                        data_type="company_contact",
                        provider="anthropic",
                        data=enrichment_output,
                        confidence=enrichment_output.get("confidence"),
                    ))
                    company_info = enrichment_output.get("company", {})
                    db.add(AIInsight(
                        tenant_id=tenant_uuid,
                        lead_id=lead_uuid,
                        insight_type="company_enrichment",
                        content=company_info.get("description", str(company_info)[:500]),
                        confidence=enrichment_output.get("confidence"),
                        source_data=enrichment_output,
                        model_used="claude",
                    ))
                    # Back-fill company record with enriched data
                    if company and company_info:
                        industry = company_info.get("industry")
                        if industry and not company.industry:
                            company.industry = industry if isinstance(industry, str) else str(industry)
                        description = company_info.get("description")
                        if description and not company.description:
                            company.description = description if isinstance(description, str) else str(description)
                        employee_count = company_info.get("employee_count") or company_info.get("employee_count_estimate")
                        if employee_count and not company.employee_count:
                            try:
                                company.employee_count = int(employee_count)
                            except (TypeError, ValueError):
                                pass
                        location = company_info.get("headquarters") or company_info.get("location")
                        if location and not company.location:
                            company.location = str(location)
                        linkedin_url = company_info.get("linkedin_url")
                        if linkedin_url and not company.linkedin_url:
                            company.linkedin_url = str(linkedin_url)
                    # Back-fill contact title/department
                    contact_info = enrichment_output.get("contact", {})
                    if contact and contact_info:
                        dept = contact_info.get("department")
                        if dept and not contact.department:
                            contact.department = dept if isinstance(dept, str) else dept.get("estimate") or str(dept)
                        seniority = contact_info.get("seniority")
                        if seniority and not contact.title:
                            contact.title = seniority if isinstance(seniority, str) else seniority.get("level") or str(seniority)
                        if contact_info.get("linkedin_url") and not contact.linkedin_url:
                            contact.linkedin_url = str(contact_info.get("linkedin_url"))
                        if contact_info.get("phone") and not contact.phone:
                            contact.phone = str(contact_info.get("phone"))
                        if contact_info.get("location") and not contact.location:
                            contact.location = str(contact_info.get("location"))
                job.status = "completed"
                job.output_data = enrichment_output
                job.completed_at = datetime.now(timezone.utc)
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
            await db.commit()

        # ── Step 3: Scoring ─────────────────────────────────────────
        if "scoring" in job_map:
            job = job_map["scoring"]
            job.status = "running"
            await db.commit()
            try:
                from app.agents.scoring_agent import ScoringAgent
                agent = ScoringAgent()
                lead_data = {
                    "company_name": company.name if company else None,
                    "domain": company.domain if company else None,
                    "contact_name": contact_full_name,
                    "contact_email": contact.email if contact else None,
                    "contact_title": contact.title if contact else None,
                    "contact_department": contact.department if contact else None,
                    "employee_count": company.employee_count if company else None,
                    "source": lead.source,
                    "identity_profile": identity_profile or None,
                }
                scoring_output = await agent.run(
                    lead_id=lead_id,
                    tenant_id=tenant_id,
                    lead_data=lead_data,
                    enrichment_data=enrichment_output or None,
                    research_data=research_output or None,
                )
                if scoring_output and not scoring_output.get("parse_error"):
                    signals_list = scoring_output.get("signals", [])
                    signal_scores = (
                        {s.get("signal_name", ""): s.get("score", s.get("value", 0))
                         for s in signals_list if s.get("signal_name")}
                        if signals_list else {}
                    )
                    db.add(LeadScore(
                        tenant_id=tenant_uuid,
                        lead_id=lead_uuid,
                        overall_score=float(scoring_output.get("overall_score", 0)),
                        tier=scoring_output.get("tier", "cold"),
                        signal_scores=signal_scores,
                        explanation=scoring_output.get("explanation"),
                        model_used="claude",
                    ))
                    db.add(AIInsight(
                        tenant_id=tenant_uuid,
                        lead_id=lead_uuid,
                        insight_type="lead_score",
                        content=scoring_output.get("explanation", ""),
                        confidence=float(scoring_output.get("overall_score", 0)) / 100,
                        source_data=scoring_output,
                        model_used="claude",
                    ))
                    lead.status = "scored"
                job.status = "completed"
                job.output_data = scoring_output
                job.completed_at = datetime.now(timezone.utc)
            except Exception as e:
                job.status = "failed"
                job.error = str(e)
            await db.commit()

        # ── Final: mark lead enriched ───────────────────────────────
        lead.enrichment_status = "enriched"
        await db.commit()


# Keep legacy single-job task for backwards compatibility
@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def run_enrichment(self, job_id: str):
    """Legacy single-job runner (kept for compatibility)."""
    import asyncio
    asyncio.run(_run_single_job_async(job_id))


async def _run_single_job_async(job_id: str):
    import uuid
    from datetime import datetime, timezone
    from sqlalchemy import select
    from app.db import async_session_factory
    from app.models.lead import EnrichmentJob

    async with async_session_factory() as db:
        res = await db.execute(
            select(EnrichmentJob).where(EnrichmentJob.id == uuid.UUID(job_id))
        )
        job = res.scalar_one_or_none()
        if not job:
            return
        job.status = "failed"
        job.error = "Use run_enrichment_pipeline instead of run_enrichment"
        await db.commit()
