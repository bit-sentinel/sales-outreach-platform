"""
signal_tasks.py — Celery tasks for the v2 signal-centric enrichment pipeline.

Runs 6 specialised signal agents in parallel (cache-first), then scores
deterministically with the Python scoring engine, and generates a Haiku
explanation.  PersonalizationAgent compatibility is maintained by persisting
AIInsight and ResearchData rows in the same format as v1.

Backward compatibility:
  - v1 run_enrichment_pipeline task is UNCHANGED in enrichment_tasks.py
  - v2 run_signal_pipeline is dispatched instead when settings.use_signal_pipeline=True
  - Both produce a LeadScore row; v2 sets pipeline_version="v2"
"""

from app.celery_app import celery_app


def _make_session_factory():
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


# Re-use the identity profile helper from v1
def _apply_identity_profile(company, contact, identity_profile: dict) -> None:
    from app.tasks.enrichment_tasks import _apply_identity_profile as _v1
    _v1(company, contact, identity_profile)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, queue="enrichment")
def run_signal_pipeline(self, lead_id: str, tenant_id: str, job_ids: dict):
    """
    v2 signal-centric pipeline:
      1. Apollo identity lookup
      2. 6 signal agents in parallel (cache-first)
      3. Pure-Python scoring engine
      4. Haiku explanation
      5. Persist LeadScore(pipeline_version="v2") + AIInsight rows
    """
    import asyncio
    try:
        asyncio.run(_run_signal_pipeline_async(lead_id, tenant_id, job_ids))
    except Exception as exc:
        raise self.retry(exc=exc)


async def _run_signal_pipeline_async(lead_id: str, tenant_id: str, job_ids: dict):
    import asyncio
    import uuid
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.config import get_settings
    from app.models.lead import (
        AIInsight, Company, Contact, EnrichmentData,
        EnrichmentJob, Lead, LeadScore, LeadSignal, ResearchData, SignalCache,
    )
    from app.agents.signals.base_signal import make_cache_key
    from app.agents.signals.cvent_signal import CventSignalAgent
    from app.agents.signals.event_volume_signal import EventVolumeSignalAgent
    from app.agents.signals.hiring_signal import HiringSignalAgent
    from app.agents.signals.org_fit_signal import OrgFitSignalAgent
    from app.agents.signals.news_signal import NewsSignalAgent
    from app.agents.signals.industry_fit_signal import IndustryFitSignalAgent
    from app.agents.scoring_engine import compute_score
    from app.agents.explainer_agent import ExplainerAgent
    from app.tools.signal_cache import SignalCacheService

    settings = get_settings()
    async_session_factory = _make_session_factory()

    lead_uuid = uuid.UUID(lead_id)
    tenant_uuid = uuid.UUID(tenant_id)

    # ── Redis client (optional) ─────────────────────────────────────────────
    redis_client = None
    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(str(settings.redis_url), decode_responses=True)
    except Exception:
        pass

    async with async_session_factory() as db:
        # ── Load jobs ───────────────────────────────────────────────────────
        job_map: dict[str, EnrichmentJob] = {}
        for jtype, jid in (job_ids or {}).items():
            res = await db.execute(
                select(EnrichmentJob).where(EnrichmentJob.id == uuid.UUID(jid))
            )
            job = res.scalar_one_or_none()
            if job:
                job_map[jtype] = job

        # ── Load lead ───────────────────────────────────────────────────────
        res = await db.execute(select(Lead).where(Lead.id == lead_uuid))
        lead = res.scalar_one_or_none()
        if not lead:
            return

        lead.enrichment_status = "enriching"
        await db.commit()

        # ── Load company + contact ──────────────────────────────────────────
        company = None
        contact = None
        if lead.company_id:
            res = await db.execute(select(Company).where(Company.id == lead.company_id))
            company = res.scalar_one_or_none()
        if lead.contact_id:
            res = await db.execute(select(Contact).where(Contact.id == lead.contact_id))
            contact = res.scalar_one_or_none()

        company_name = company.name if company else None
        domain = company.domain if company else None
        contact_full_name = (
            f"{contact.first_name} {contact.last_name}".strip() if contact else None
        )

        # ── Contact identity lookup: Apollo → PDL fallback ─────────────────
        identity_profile: dict = {}
        identity_provider: str = ""
        if contact and contact.email:
            from app.tools.apollo import enrich_person_by_email as apollo_enrich
            from app.tools.pdl import enrich_person_by_email as pdl_enrich
            try:
                if settings.apollo_api_key:
                    identity_profile = await apollo_enrich(contact.email, settings.apollo_api_key)
                    if identity_profile:
                        identity_provider = "apollo"
                if not identity_profile and settings.pdl_api_key:
                    identity_profile = await pdl_enrich(contact.email, settings.pdl_api_key)
                    if identity_profile:
                        identity_provider = "pdl"
                if identity_profile:
                    _apply_identity_profile(company, contact, identity_profile)
                    db.add(EnrichmentData(
                        tenant_id=tenant_uuid,
                        lead_id=lead_uuid,
                        data_type="identity_profile",
                        provider=identity_provider,
                        data=identity_profile,
                        confidence=1.0,
                    ))
                    await db.commit()
                    domain = company.domain if company else None
                    contact_full_name = (
                        f"{contact.first_name} {contact.last_name}".strip() if contact else None
                    )
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Contact identity lookup failed: %s", exc)

        # ── Cache service ───────────────────────────────────────────────────
        cache = SignalCacheService(redis_client=redis_client, db=db)

        # ── Check cache for each signal type ────────────────────────────────
        signal_types = [
            "cvent_events", "event_volume", "hiring_signal",
            "org_fit", "news_signal", "industry_fit",
        ]
        cache_results = await asyncio.gather(*[
            cache.get(stype, domain=domain, company_name=company_name or "")
            for stype in signal_types
        ])
        cached: dict = {
            stype: r for stype, r in zip(signal_types, cache_results) if r is not None
        }
        uncached = [stype for stype in signal_types if stype not in cached]

        # ── Run uncached signal agents in parallel ───────────────────────────
        agent_kwargs = {
            "company_name":     company_name or "",
            "domain":           domain,
            "company":          company,
            "contact":          contact,
            "identity_profile": identity_profile,
        }

        async def _run_cvent() -> None:
            if "cvent_events" not in uncached:
                return
            result = await CventSignalAgent().collect(**agent_kwargs)
            cached["cvent_events"] = result
            await cache.set(result, domain=domain, company_name=company_name or "")

        async def _run_event_volume() -> None:
            if "event_volume" not in uncached:
                return
            # Seed from Cvent agent evidence if available
            cvent_ev = cached.get("cvent_events", {})
            cvent_evidence = cvent_ev.evidence if hasattr(cvent_ev, "evidence") else {}
            result = await EventVolumeSignalAgent().collect(
                **agent_kwargs, cvent_evidence=cvent_evidence
            )
            cached["event_volume"] = result
            await cache.set(result, domain=domain, company_name=company_name or "")

        async def _run_hiring() -> None:
            if "hiring_signal" not in uncached:
                return
            result = await HiringSignalAgent().collect(**agent_kwargs)
            cached["hiring_signal"] = result
            await cache.set(result, domain=domain, company_name=company_name or "")

        async def _run_org_fit() -> None:
            if "org_fit" not in uncached:
                return
            result = await OrgFitSignalAgent().collect(**agent_kwargs)
            cached["org_fit"] = result
            # org_fit is NOT cached at company level — it's contact-specific
            # (seniority/dept differ per contact).  Cache with contact email as discriminator.
            contact_discriminator = (contact.email if contact else None) or company_name or ""
            org_key = make_cache_key("org_fit", domain, contact_discriminator)
            # Write directly to Redis (short TTL already built into OrgFitSignal: 720h)
            if redis_client:
                import json
                try:
                    await redis_client.setex(
                        org_key, 3600 * result.ttl_hours,
                        json.dumps(result.to_dict(), default=str),
                    )
                except Exception:
                    pass

        async def _run_news() -> None:
            if "news_signal" not in uncached:
                return
            result = await NewsSignalAgent().collect(**agent_kwargs)
            cached["news_signal"] = result
            await cache.set(result, domain=domain, company_name=company_name or "")

        async def _run_industry_fit() -> None:
            if "industry_fit" not in uncached:
                return
            result = await IndustryFitSignalAgent().collect(**agent_kwargs)
            cached["industry_fit"] = result
            await cache.set(result, domain=domain, company_name=company_name or "")

        # Cvent must run first so event_volume can seed from it
        await _run_cvent()
        await asyncio.gather(
            _run_event_volume(),  # depends on cvent
            _run_hiring(),
            _run_org_fit(),
            _run_news(),
            _run_industry_fit(),
        )

        signals = list(cached.values())

        # ── Persist LeadSignal rows ─────────────────────────────────────────
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        for sig in signals:
            db.add(LeadSignal(
                tenant_id=tenant_uuid,
                lead_id=lead_uuid,
                signal_type=sig.signal_type,
                value=sig.value,
                weight=sig.weight,
                evidence=sig.evidence,
                provider=sig.provider,
                confidence=sig.confidence,
                cached_until=now + timedelta(hours=sig.ttl_hours),
            ))
        await db.commit()

        # ── Scoring engine ──────────────────────────────────────────────────
        score_result = compute_score(signals)

        # ── Explanation (Haiku) ─────────────────────────────────────────────
        explanation_data: dict = {}
        try:
            explainer = ExplainerAgent()
            explanation_data = await explainer.run(
                score_result=score_result,
                company_name=company_name,
                contact_name=contact_full_name,
                contact_title=contact.title if contact else None,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("ExplainerAgent failed: %s", exc)

        # ── Persist LeadScore (v2) ──────────────────────────────────────────
        db.add(LeadScore(
            tenant_id=tenant_uuid,
            lead_id=lead_uuid,
            overall_score=score_result["overall_score"],
            tier=score_result["tier"],
            signal_scores=score_result["signal_scores"],
            signal_breakdown=score_result["signal_breakdown"],
            explanation=explanation_data.get("explanation", ""),
            model_used="claude-3-5-haiku-20241022",
            pipeline_version="v2",
            scored_at=now,
        ))

        # ── Persist AIInsight rows (PersonalizationAgent compatibility) ──────
        db.add(AIInsight(
            tenant_id=tenant_uuid,
            lead_id=lead_uuid,
            insight_type="lead_score",
            content=explanation_data.get("explanation", ""),
            confidence=score_result["overall_score"] / 100,
            source_data={
                **score_result,
                "recommended_action": explanation_data.get("recommended_action"),
                "top_hooks":          explanation_data.get("top_hooks", []),
                "outreach_angle":     explanation_data.get("outreach_angle"),
            },
            model_used="claude-3-5-haiku-20241022",
        ))

        # Persist cvent event pages as ResearchData (PersonalizationAgent compatibility)
        cvent_result = cached.get("cvent_events")
        if cvent_result:
            for page in (cvent_result.evidence.get("event_pages") or [])[:5]:
                db.add(ResearchData(
                    tenant_id=tenant_uuid,
                    lead_id=lead_uuid,
                    source="cvent_event_page",
                    url=page.get("url"),
                    title=page.get("title") or "Cvent event page",
                    content=page.get("snippet") or "",
                    relevance_score=cvent_result.value,
                    metadata_=page,
                ))

        # ── Mark jobs complete ──────────────────────────────────────────────
        for job in job_map.values():
            job.status = "completed"
            job.output_data = score_result
            job.completed_at = now

        lead.enrichment_status = "enriched"
        lead.status = "scored"
        await db.commit()

    if redis_client:
        try:
            await redis_client.aclose()
        except Exception:
            pass
