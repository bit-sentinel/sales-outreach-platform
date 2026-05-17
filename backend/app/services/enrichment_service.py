"""
Enrichment service – triggers AI enrichment pipeline for leads.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead import AIInsight, EnrichmentData, EnrichmentJob, LeadScore, ResearchData


class EnrichmentService:
    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    async def enrich_leads(
        self, lead_ids: list[uuid.UUID], enrichment_types: list[str]
    ) -> list[uuid.UUID]:
        """Create enrichment jobs and dispatch to Celery pipeline worker."""
        from app.config import get_settings
        settings = get_settings()
        use_v3 = settings.pipeline_version == "v3"
        use_v2 = settings.use_signal_pipeline

        all_job_ids: list[uuid.UUID] = []

        for lead_id in lead_ids:
            job_map: dict[str, str] = {}

            if use_v3:
                job = EnrichmentJob(
                    tenant_id=self.tenant_id,
                    lead_id=lead_id,
                    job_type="event_intelligence",
                    status="pending",
                )
                self.db.add(job)
                await self.db.flush()
                all_job_ids.append(job.id)
                await self.db.commit()
                from app.tasks.v3.stage_tasks import orchestrate_event_intelligence
                orchestrate_event_intelligence.delay(str(lead_id), job_id=str(job.id))
            elif use_v2:
                job = EnrichmentJob(
                    tenant_id=self.tenant_id,
                    lead_id=lead_id,
                    job_type="signal_pipeline",
                    status="pending",
                )
                self.db.add(job)
                await self.db.flush()
                job_map["signal_pipeline"] = str(job.id)
                all_job_ids.append(job.id)
                await self.db.commit()
                from app.tasks.signal_tasks import run_signal_pipeline
                run_signal_pipeline.delay(str(lead_id), str(self.tenant_id), job_map)
            else:
                for etype in enrichment_types:
                    job = EnrichmentJob(
                        tenant_id=self.tenant_id,
                        lead_id=lead_id,
                        job_type=etype,
                        status="pending",
                    )
                    self.db.add(job)
                    await self.db.flush()
                    job_map[etype] = str(job.id)
                    all_job_ids.append(job.id)
                await self.db.commit()
                from app.tasks.enrichment_tasks import run_enrichment_pipeline
                run_enrichment_pipeline.delay(str(lead_id), str(self.tenant_id), job_map)

        return all_job_ids

    async def get_job(self, job_id: uuid.UUID) -> EnrichmentJob | None:
        result = await self.db.execute(
            select(EnrichmentJob).where(
                EnrichmentJob.id == job_id,
                EnrichmentJob.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_lead_insights(self, lead_id: uuid.UUID) -> list[dict]:
        result = await self.db.execute(
            select(AIInsight).where(
                AIInsight.lead_id == lead_id,
                AIInsight.tenant_id == self.tenant_id,
            ).order_by(AIInsight.created_at.desc())
        )
        insights = result.scalars().all()
        return [
            {
                "id": str(i.id),
                "type": i.insight_type,
                "content": i.content,
                "source_data": i.source_data,
                "confidence": i.confidence,
                "model": i.model_used,
                "created_at": i.created_at.isoformat(),
            }
            for i in insights
        ]

    async def get_lead_research(self, lead_id: uuid.UUID) -> list[dict]:
        result = await self.db.execute(
            select(ResearchData).where(
                ResearchData.lead_id == lead_id,
                ResearchData.tenant_id == self.tenant_id,
            ).order_by(ResearchData.relevance_score.desc().nullslast())
        )
        research = result.scalars().all()
        return [
            {
                "id": str(r.id),
                "source": r.source,
                "url": r.url,
                "title": r.title,
                "content": r.content,
                "relevance_score": r.relevance_score,
            }
            for r in research
        ]

    async def get_enrichment_data(self, lead_id: uuid.UUID) -> list[dict]:
        result = await self.db.execute(
            select(EnrichmentData).where(
                EnrichmentData.lead_id == lead_id,
                EnrichmentData.tenant_id == self.tenant_id,
            ).order_by(EnrichmentData.created_at.desc())
        )
        rows = result.scalars().all()
        return [
            {
                "id": str(r.id),
                "data_type": r.data_type,
                "provider": r.provider,
                "data": r.data,
                "confidence": r.confidence,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    async def get_latest_score(self, lead_id: uuid.UUID) -> dict | None:
        result = await self.db.execute(
            select(LeadScore)
            .where(
                LeadScore.lead_id == lead_id,
                LeadScore.tenant_id == self.tenant_id,
            )
            .order_by(LeadScore.created_at.desc())
            .limit(1)
        )
        score = result.scalar_one_or_none()
        if not score:
            return None
        return {
            "overall_score": score.overall_score,
            "tier": score.tier,
            "signal_scores": score.signal_scores,
            "signal_breakdown": score.signal_breakdown,
            "explanation": score.explanation,
            "model": score.model_used,
            "pipeline_version": score.pipeline_version,
            "created_at": score.created_at.isoformat(),
        }
