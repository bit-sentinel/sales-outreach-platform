"""
Enrichment service – triggers AI enrichment pipeline for leads.
"""

import hashlib
import uuid
from datetime import datetime, timezone

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

    # ── v3 signal_cache helpers ────────────────────────────────────────────

    @staticmethod
    def _v3_cache_key(signal_type: str, scope: str, identifier: str) -> str:
        """Reproduce AgentResultCache.cache_key() from app/agents/v3/cache.py."""
        norm = (identifier or "").lower().strip()
        norm = norm.replace("https://", "").replace("http://", "").strip("/")
        digest = hashlib.sha256(f"{signal_type}|{scope}|{norm}".encode()).hexdigest()[:24]
        return f"v3res:{digest}"

    async def _get_v3_result(self, signal_type: str, scope: str, identifier: str) -> dict | None:
        """Look up a cached v3 AgentResult from signal_cache."""
        from app.models.lead import SignalCache
        key = self._v3_cache_key(signal_type, scope, identifier)
        row = (await self.db.execute(
            select(SignalCache).where(
                SignalCache.cache_key == key,
                SignalCache.expires_at > datetime.now(timezone.utc),
            )
        )).scalar_one_or_none()
        return row.evidence if row else None

    async def _get_lead_identifiers(self, lead_id: uuid.UUID) -> dict | None:
        """Return company domain/name and contact email for computing v3 cache keys."""
        from app.models.lead import Lead, Contact
        from app.models.lead import Company
        row = (await self.db.execute(
            select(
                Lead.company_id,
                Company.domain,
                Company.name.label("company_name"),
                Contact.email,
            )
            .join(Company, Company.id == Lead.company_id, isouter=True)
            .join(Contact, Contact.id == Lead.contact_id, isouter=True)
            .where(Lead.id == lead_id)
        )).one_or_none()
        if not row:
            return None
        return {
            "company_id": row.company_id,
            "domain": row.domain or row.company_name or "",
            "email": row.email or "",
        }

    async def _load_v3_signals(self, lead_id: uuid.UUID) -> dict[str, dict]:
        """Load all v3 signal cache results for a lead. Returns {signal_type: result_dict}."""
        ids = await self._get_lead_identifiers(lead_id)
        if not ids:
            return {}

        company_id = ids["domain"]
        email = ids["email"]

        # Scope per agent class (mirrors each agent's cache_scope declaration)
        company_signals = [
            "org_graph", "cvent", "event_volume", "hiring",
            "budget", "outsourcing", "targeted_research",
        ]
        contact_signals = ["identity", "event_team", "outreach"]

        results: dict[str, dict] = {}
        for sig in company_signals:
            data = await self._get_v3_result(sig, "company", company_id)
            if data:
                results[sig] = data
        if email:
            for sig in contact_signals:
                data = await self._get_v3_result(sig, "contact", email)
                if data:
                    results[sig] = data
        return results

    # ── Existing v2 read methods (unchanged, but now v3-aware) ────────────

    async def get_lead_insights(self, lead_id: uuid.UUID) -> list[dict]:
        result = await self.db.execute(
            select(AIInsight).where(
                AIInsight.lead_id == lead_id,
                AIInsight.tenant_id == self.tenant_id,
            ).order_by(AIInsight.created_at.desc())
        )
        insights = result.scalars().all()
        if insights:
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
        # Fall back to v3 signal_cache data
        return await self._synthesize_v3_insights(lead_id)

    async def _synthesize_v3_insights(self, lead_id: uuid.UUID) -> list[dict]:
        """Build a fake research_summary AIInsight from v3 signal_cache data."""
        signals = await self._load_v3_signals(lead_id)
        if not signals:
            return []

        cvent = signals.get("cvent", {})
        volume = signals.get("event_volume", {})
        hiring = signals.get("hiring", {})
        targeted = signals.get("targeted_research", {})
        budget = signals.get("budget", {})

        cvent_payload = cvent.get("payload", {})
        volume_payload = volume.get("payload", {})
        hiring_payload = hiring.get("payload", {})
        budget_payload = budget.get("payload", {})

        # Build technology_stack from cvent detection
        tech_stack: list[str] = []
        if cvent_payload.get("detected"):
            tech_stack.append("Cvent")

        # Build events_attended from cvent + evidence items
        events_attended: list[dict] = []
        for ev in (cvent_payload.get("_raw", {}).get("events", []) or [])[:8]:
            events_attended.append({
                "event": ev.get("title") or ev.get("name", "Unknown event"),
                "date_label": ev.get("date_label") or ev.get("date"),
                "type": "upcoming" if ev.get("is_upcoming") else "past",
                "role": "host",
                "confirmed": cvent_payload.get("detected", False),
                "url": ev.get("url"),
            })

        # Industry signals from hiring
        industry_signals: list[str] = []
        for role in (hiring_payload.get("roles") or [])[:5]:
            title = role.get("title")
            if title:
                industry_signals.append(f"Open role: {title}")

        # Pull findings from targeted_research as additional signals
        for finding in (targeted.get("payload", {}).get("findings") or []):
            if finding.get("results", 0) > 0:
                industry_signals.append(
                    f"Research gap resolved: {finding.get('signal')} ({finding.get('reason', '')})"
                )

        company_summary = (
            volume_payload.get("company_summary")
            or f"Event programme: ~{volume_payload.get('estimated_events_per_year', '?')} events/year"
            f", complexity: {volume_payload.get('complexity_tier', 'unknown')}"
            f". Budget band: {budget_payload.get('estimated_budget_band', 'unknown')}."
        )

        source_data = {
            "company_summary": company_summary,
            "technology_stack": {"confirmed": tech_stack, "inferred": [],
                                  "tech_stack_confidence": "high" if tech_stack else "low"},
            "events_attended": events_attended,
            "industry_signals": industry_signals,
            "relevance_score": 0.85 if cvent_payload.get("detected") else 0.5,
            "key_people": [],
            "recent_news": [],
            "data_gaps": [],
        }

        return [{
            "id": str(uuid.uuid4()),
            "type": "research_summary",
            "content": company_summary,
            "source_data": source_data,
            "confidence": cvent.get("confidence", 0.7),
            "model": "v3_event_intelligence",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }]

    async def get_lead_research(self, lead_id: uuid.UUID) -> list[dict]:
        result = await self.db.execute(
            select(ResearchData).where(
                ResearchData.lead_id == lead_id,
                ResearchData.tenant_id == self.tenant_id,
            ).order_by(ResearchData.relevance_score.desc().nullslast())
        )
        research = result.scalars().all()
        if research:
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
        # Fall back to v3 evidence
        return await self._synthesize_v3_research(lead_id)

    async def _synthesize_v3_research(self, lead_id: uuid.UUID) -> list[dict]:
        """Return evidence items from v3 signal_cache as ResearchItem list."""
        signals = await self._load_v3_signals(lead_id)
        items: list[dict] = []
        for sig_type, data in signals.items():
            for ev in (data.get("evidence") or [])[:4]:
                claim = ev.get("claim", "")
                url = ev.get("source_url")
                if not claim:
                    continue
                items.append({
                    "id": str(uuid.uuid4()),
                    "source": ev.get("source_provider") or sig_type,
                    "url": url,
                    "title": claim[:120],
                    "content": ev.get("raw_snippet") or claim,
                    "relevance_score": ev.get("confidence", 0.5),
                })
        return items

    async def get_enrichment_data(self, lead_id: uuid.UUID) -> list[dict]:
        result = await self.db.execute(
            select(EnrichmentData).where(
                EnrichmentData.lead_id == lead_id,
                EnrichmentData.tenant_id == self.tenant_id,
            ).order_by(EnrichmentData.created_at.desc())
        )
        rows = result.scalars().all()
        if rows:
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
        # Fall back to v3 synthesized company profile
        return await self._synthesize_v3_enrichment_data(lead_id)

    async def _synthesize_v3_enrichment_data(self, lead_id: uuid.UUID) -> list[dict]:
        """Return company event profile from v3 signal_cache as EnrichmentDataItem."""
        signals = await self._load_v3_signals(lead_id)
        if not signals:
            return []

        ids = await self._get_lead_identifiers(lead_id)
        cvent = signals.get("cvent", {})
        volume = signals.get("event_volume", {})
        budget = signals.get("budget", {})
        outsourcing = signals.get("outsourcing", {})
        event_team = signals.get("event_team", {})
        identity = signals.get("identity", {})

        cvent_p = cvent.get("payload", {})
        volume_p = volume.get("payload", {})
        budget_p = budget.get("payload", {})
        out_p = outsourcing.get("payload", {})
        team_p = event_team.get("payload", {})
        id_p = identity.get("payload", {})

        events_per_year = volume_p.get("estimated_events_per_year")
        cvent_status = ("confirmed" if (cvent.get("value", 0) or 0) >= 0.5
                        else "likely" if (cvent.get("value", 0) or 0) > 0 else "unknown")
        volume_tier = (
            "high" if (events_per_year or 0) >= 12
            else "medium" if (events_per_year or 0) >= 4
            else "low" if events_per_year else "unknown"
        )

        company_profile = {
            "cvent_status": cvent_status,
            "cvent_confidence": cvent.get("confidence"),
            "event_volume_tier": volume_tier,
            "estimated_events_per_year": events_per_year,
            "complexity_tier": volume_p.get("complexity_tier"),
            "estimated_budget_band": budget_p.get("estimated_budget_band"),
            "budget_confidence": budget.get("confidence"),
            "outsourcing_tier": out_p.get("outsourcing_tier", "unknown"),
            "outsourcing_propensity": outsourcing.get("value"),
            "event_team_size": team_p.get("event_team_size"),
            "event_team_under_resourced": team_p.get("under_resourced"),
            "registration_urls": cvent_p.get("registration_urls") or [],
            "pipeline_version": "v3",
        }

        contact_profile = {}
        if id_p:
            contact_profile = {
                "title_inferred": id_p.get("contact_title"),
                "seniority_estimate": id_p.get("seniority"),
                "department_estimate": id_p.get("department"),
                "decision_maker_status": id_p.get("decision_maker"),
            }

        return [{
            "id": str(uuid.uuid4()),
            "data_type": "company_event_profile",
            "provider": "v3_event_intelligence",
            "data": {"company": company_profile, "contact": contact_profile},
            "confidence": max(
                cvent.get("confidence", 0) or 0,
                volume.get("confidence", 0) or 0,
            ),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }]

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

    async def get_lead_outreach(self, lead_id: uuid.UUID) -> dict | None:
        """Return v3 outreach intelligence for a lead (contact-scoped from signal_cache)."""
        ids = await self._get_lead_identifiers(lead_id)
        if not ids or not ids.get("email"):
            return None
        data = await self._get_v3_result("outreach", "contact", ids["email"])
        if not data:
            return None
        payload = data.get("payload", {})
        if not payload:
            return None
        return {
            "recommended_contact_role": payload.get("recommended_contact_role", ""),
            "subject_line": payload.get("subject_line", ""),
            "email_body": payload.get("email_body", ""),
            "angles": payload.get("angles", []),
            "event_references": payload.get("event_references", []),
            "timing_recommendation": payload.get("timing_recommendation", ""),
            "timing_rationale": payload.get("timing_rationale", ""),
            "service_recommendations": payload.get("service_recommendations", []),
            "generation_basis": payload.get("generation_basis", {}),
            "confidence": data.get("confidence", 0.7),
            "generated_at": data.get("completed_at"),
        }
