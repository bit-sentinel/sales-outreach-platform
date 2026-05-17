"""
v3 pipeline — Celery stage tasks.

Each stage task: builds context, runs its agents concurrently, persists
evidence + typed signals, then explicitly dispatches the next stage.
Gates run between Stage 2->3 and Stage 5->6.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.agents.v3.cache import AgentResultCache, CallCache
from app.agents.v3.contracts import (
    AgentContext, AgentResult, CompanyContext, ContactContext, PipelineStage,
    SignalType,
)
import app.agents.v3.agents  # noqa: F401 — registers all agents
from app.agents.v3.persistence import (
    persist_evidence, persist_typed_signals, upsert_company_profile,
)
from app.agents.v3.registry import agents_for_stage
from app.agents.v3.scoring import (
    EvidenceAggregator, ScoringEngine, gate1_event_fit, gate2_score,
)
from app.celery_app import celery_app
from app.config import get_settings

logger = logging.getLogger(__name__)

_STAGE_ORDER = [
    PipelineStage.IDENTITY, PipelineStage.EVENT_FIT, PipelineStage.PRESSURE,
    PipelineStage.SYNTHESIS, PipelineStage.SCORE, PipelineStage.INTELLIGENCE,
]


# ── infrastructure ─────────────────────────────────────────────────────────
def _session_factory():
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    s = get_settings()
    engine = create_async_engine(str(s.database_url), pool_size=5,
                                 max_overflow=5, pool_pre_ping=True)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _redis():
    try:
        import redis.asyncio as aioredis
        return aioredis.from_url(str(get_settings().redis_url), decode_responses=True)
    except Exception:
        return None


def _sync_redis():
    import redis
    return redis.from_url(str(get_settings().redis_url), decode_responses=True)


def _load_upstream(run_id: UUID) -> dict[SignalType, AgentResult]:
    try:
        client = _sync_redis()
        raw = client.get(f"v3run:{run_id}:results")
        client.close()
        if not raw:
            return {}
        return {SignalType(k): AgentResult.model_validate(v)
                for k, v in json.loads(raw).items()}
    except Exception:
        return {}


def _save_upstream(run_id: UUID, results: dict[SignalType, AgentResult]) -> None:
    try:
        client = _sync_redis()
        client.setex(f"v3run:{run_id}:results", 7200,
                     json.dumps({k.value: v.model_dump(mode="json")
                                 for k, v in results.items()}))
        client.close()
    except Exception as exc:
        logger.warning("[v3] could not save run state: %s", exc)


def _save_job_id(run_id: UUID, job_id: str) -> None:
    try:
        client = _sync_redis()
        client.setex(f"v3run:{run_id}:job_id", 7200, job_id)
        client.close()
    except Exception:
        pass


def _mark_job_done(run_id: UUID, status: str, error: str | None = None) -> None:
    """Update the EnrichmentJob row that tracks this v3 run."""
    try:
        import asyncio
        from datetime import datetime, timezone
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy import select
        from app.models.lead import EnrichmentJob

        client = _sync_redis()
        job_id_str = client.get(f"v3run:{run_id}:job_id")
        client.close()
        if not job_id_str:
            return

        job_uuid = UUID(job_id_str)
        s = get_settings()
        engine = create_async_engine(str(s.database_url))
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _update():
            async with factory() as session:
                job = (await session.execute(
                    select(EnrichmentJob).where(EnrichmentJob.id == job_uuid)
                )).scalar_one_or_none()
                if job:
                    job.status = status
                    job.completed_at = datetime.now(timezone.utc)
                    if error:
                        job.error = error[:500]
                    await session.commit()
            await engine.dispose()

        asyncio.run(_update())
    except Exception as exc:
        logger.warning("[v3] could not mark job done: %s", exc)


# ── context ────────────────────────────────────────────────────────────────
async def _build_context(session, run_id: UUID, lead_id: UUID) -> AgentContext:
    from sqlalchemy import desc, select
    from app.models.lead import Lead, Company, Contact, LeadScore
    from app.models.event_intelligence import CompanyEventProfile

    lead = (await session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
    company = (await session.execute(
        select(Company).where(Company.id == lead.company_id))).scalar_one_or_none()
    contact = (await session.execute(
        select(Contact).where(Contact.id == lead.contact_id))).scalar_one_or_none()
    if company is None:
        raise RuntimeError(f"lead {lead_id} has no company")

    # Stage-6 inputs — present once Stage 5 has run; harmless (None) earlier.
    extra: dict = {}
    score = (await session.execute(
        select(LeadScore).where(LeadScore.lead_id == lead_id)
        .order_by(desc(LeadScore.created_at)).limit(1))).scalar_one_or_none()
    if score is not None:
        extra["lead_score"] = {
            "overall_score": score.overall_score, "tier": score.tier,
            "confidence": score.confidence, "completeness": score.completeness,
            "signal_scores": score.signal_scores or {},
            "signal_breakdown": score.signal_breakdown or {},
            "explanation": score.explanation,
        }
    profile = (await session.execute(
        select(CompanyEventProfile)
        .where(CompanyEventProfile.company_id == company.id))).scalar_one_or_none()
    if profile is not None:
        extra["company_profile"] = {
            "cvent_status": profile.cvent_status,
            "event_volume_tier": profile.event_volume_tier,
            "estimated_events_per_year": profile.estimated_events_per_year,
            "estimated_budget_band": profile.estimated_budget_band,
            "outsourcing_tier": profile.outsourcing_tier,
            "overall_fit_score": profile.overall_fit_score,
            "summary": profile.summary,
        }

    return AgentContext(
        extra=extra,
        run_id=run_id, lead_id=lead_id,
        company=CompanyContext(
            company_id=company.id, tenant_id=lead.tenant_id, name=company.name,
            domain=company.domain, industry=company.industry,
            employee_count=company.employee_count, location=company.location,
        ),
        contact=ContactContext(
            contact_id=contact.id, first_name=contact.first_name,
            last_name=contact.last_name,
            full_name=f"{contact.first_name} {contact.last_name}".strip(),
            email=contact.email, title=contact.title, department=contact.department,
            linkedin_url=contact.linkedin_url,
        ) if contact else None,
        upstream=_load_upstream(run_id),
    )


# ── stage execution ────────────────────────────────────────────────────────
async def _run_collection_stage(stage: PipelineStage, run_id: UUID, lead_id: UUID) -> None:
    session_factory = _session_factory()
    redis_client = _redis()
    result_cache = AgentResultCache(redis_client=redis_client, session_factory=session_factory)
    call_cache = CallCache(redis_client=redis_client)

    async with session_factory() as session:
        ctx = await _build_context(session, run_id, lead_id)

    agents = [cls(result_cache, call_cache) for cls in agents_for_stage(stage.value)]
    if not agents:
        logger.info("[v3] stage %s — no agents", stage.value)
        return

    results: list[AgentResult] = await asyncio.gather(*(a.run(ctx) for a in agents))
    by_signal = {r.signal_type: r for r in results}

    # persist evidence + typed domain rows
    async with session_factory() as session:
        ev_map = await persist_evidence(
            session, ctx.company.tenant_id, ctx.company.company_id, results)
        await persist_typed_signals(
            session, ctx.company.tenant_id, ctx.company.company_id,
            by_signal, list(ev_map.values()))
        await session.commit()

    merged = dict(ctx.upstream)
    merged.update(by_signal)
    _save_upstream(run_id, merged)
    logger.info("[v3] stage %s — %s", stage.value,
                {r.signal_type.value: r.status.value for r in results})


async def _run_score_stage(run_id: UUID, lead_id: UUID) -> bool:
    """Stage 5 — aggregate, score, persist lead_scores + breakdown. Returns gate2."""
    from sqlalchemy import select
    from app.models.lead import Lead, LeadScore
    from app.models.event_intelligence import LeadScoreBreakdown, SignalEvidence

    session_factory = _session_factory()
    results = _load_upstream(run_id)

    agg = EvidenceAggregator().aggregate(results)
    score = ScoringEngine().score(results, agg["completeness"])

    async with session_factory() as session:
        lead = (await session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
        tenant_id = lead.tenant_id

        ls = LeadScore(
            tenant_id=tenant_id, lead_id=lead_id,
            overall_score=score.overall_score, tier=score.tier,
            signal_scores=score.signal_scores,
            signal_breakdown={b.signal_type.value: {
                "value": b.raw_value, "weight": b.weight,
                "contribution": b.contribution, "confidence": b.confidence,
            } for b in score.breakdown},
            explanation="; ".join(b.rationale for b in score.breakdown[:3]),
            model_used="v3_scoring_engine", pipeline_version="v3",
            scored_at=datetime.now(timezone.utc),
            confidence=score.confidence, completeness=score.completeness,
            gate_passed=score.gate_passed,
        )
        session.add(ls)
        await session.flush()

        # resolve evidence content-hashes -> evidence UUIDs for traceability
        all_hashes = [h for b in score.breakdown for h in b.evidence_hashes]
        hash_to_id: dict[str, UUID] = {}
        if all_hashes:
            rows = (await session.execute(
                select(SignalEvidence.id, SignalEvidence.content_hash)
                .where(SignalEvidence.company_id == lead.company_id,
                       SignalEvidence.content_hash.in_(all_hashes))
            )).all()
            hash_to_id = {ch: rid for rid, ch in rows}

        for b in score.breakdown:
            session.add(LeadScoreBreakdown(
                tenant_id=tenant_id, score_id=ls.id, lead_id=lead_id,
                signal_type=b.signal_type.value, raw_value=b.raw_value,
                weight=b.weight, contribution=b.contribution, confidence=b.confidence,
                evidence_ids=[hash_to_id[h] for h in b.evidence_hashes if h in hash_to_id],
                rationale=b.rationale,
            ))

        lead.status = "scored"
        lead.enrichment_status = "enriched"
        await upsert_company_profile(session, tenant_id, lead.company_id,
                                     _build_profile_rollup(results, score, ls.explanation))
        await session.commit()

    logger.info("[v3] scored lead %s -> %.1f (%s)", lead_id, score.overall_score, score.tier)
    return gate2_score(score)


def _build_profile_rollup(results, score, explanation: str) -> dict:
    """Compose the CompanyEventProfile rollup from scored signal payloads."""
    cvent = results.get(SignalType.CVENT)
    volume = results.get(SignalType.EVENT_VOLUME)
    budget = results.get(SignalType.BUDGET)
    outsourcing = results.get(SignalType.OUTSOURCING)

    cvent_v = cvent.value if cvent and cvent.is_usable() else 0.0
    cvent_status = ("confirmed" if cvent_v >= 0.5
                    else "likely" if cvent_v > 0.0 else "none")
    vol_payload = volume.payload if volume and volume.is_usable() else {}
    events = vol_payload.get("estimated_events_per_year")
    volume_tier = ("high" if (events or 0) >= 12
                   else "medium" if (events or 0) >= 4
                   else "low" if events else "unknown")
    return {
        "cvent_status": cvent_status,
        "cvent_confidence": cvent.confidence if cvent else None,
        "event_volume_tier": volume_tier,
        "estimated_events_per_year": events,
        "estimated_budget_band": (budget.payload.get("estimated_budget_band")
                                  if budget and budget.is_usable() else None),
        "budget_confidence": budget.confidence if budget else None,
        "outsourcing_propensity": outsourcing.value if outsourcing else None,
        "outsourcing_tier": (outsourcing.payload.get("outsourcing_tier")
                             if outsourcing and outsourcing.is_usable() else "unknown"),
        "overall_fit_score": score.overall_score,
        "data_completeness": score.completeness,
        "summary": explanation,
    }


async def _finalize_disqualified(run_id: UUID, lead_id: UUID, reason: str) -> None:
    from sqlalchemy import select
    from app.models.lead import Lead, LeadScore

    session_factory = _session_factory()
    async with session_factory() as session:
        lead = (await session.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
        session.add(LeadScore(
            tenant_id=lead.tenant_id, lead_id=lead_id, overall_score=0.0, tier="cold",
            signal_scores={}, explanation=f"Disqualified at Gate 1: {reason}",
            model_used="v3_gate", pipeline_version="v3",
            scored_at=datetime.now(timezone.utc),
            disqualified_reason=reason, gate_passed="disqualified",
        ))
        lead.status = "disqualified"
        lead.enrichment_status = "enriched"
        await session.commit()
    logger.info("[v3] lead %s disqualified at Gate 1: %s", lead_id, reason)
    _mark_job_done(run_id, "completed")


# ── dispatch ───────────────────────────────────────────────────────────────
def _dispatch_next(current: PipelineStage, run_id: str, lead_id: str) -> None:
    idx = _STAGE_ORDER.index(current)
    if idx + 1 >= len(_STAGE_ORDER):
        return
    _STAGE_TASKS[_STAGE_ORDER[idx + 1]].delay(run_id, lead_id)


def _make_stage_task(stage: PipelineStage):
    @celery_app.task(bind=True, name=f"app.tasks.v3.{stage.value}",
                     queue="enrichment", max_retries=2, default_retry_delay=30,
                     acks_late=True)
    def _task(self, run_id: str, lead_id: str):
        rid, lid = UUID(run_id), UUID(lead_id)
        try:
            if stage is PipelineStage.SCORE:
                gate2 = asyncio.run(_run_score_stage(rid, lid))
                if gate2:
                    _dispatch_next(stage, run_id, lead_id)
                else:
                    logger.info("[v3] Gate 2 not passed — stopping before Stage 6")
                    _mark_job_done(rid, "completed")
                return

            asyncio.run(_run_collection_stage(stage, rid, lid))

            if stage is PipelineStage.EVENT_FIT:
                passed, reason = gate1_event_fit(_load_upstream(rid))
                if not passed:
                    asyncio.run(_finalize_disqualified(rid, lid, reason or "gate1"))
                    return

            if stage is PipelineStage.INTELLIGENCE:
                _mark_job_done(rid, "completed")
                return

            _dispatch_next(stage, run_id, lead_id)
        except Exception as exc:
            logger.error("[v3] stage %s infra error: %s", stage.value, exc)
            if self.request.retries >= self.max_retries:
                _mark_job_done(rid, "failed", error=str(exc))
            raise self.retry(exc=exc)

    return _task


stage1_identity     = _make_stage_task(PipelineStage.IDENTITY)
stage2_event_fit    = _make_stage_task(PipelineStage.EVENT_FIT)
stage3_pressure     = _make_stage_task(PipelineStage.PRESSURE)
stage4_synthesis    = _make_stage_task(PipelineStage.SYNTHESIS)
stage5_score        = _make_stage_task(PipelineStage.SCORE)
stage6_intelligence = _make_stage_task(PipelineStage.INTELLIGENCE)

_STAGE_TASKS = {
    PipelineStage.IDENTITY: stage1_identity,
    PipelineStage.EVENT_FIT: stage2_event_fit,
    PipelineStage.PRESSURE: stage3_pressure,
    PipelineStage.SYNTHESIS: stage4_synthesis,
    PipelineStage.SCORE: stage5_score,
    PipelineStage.INTELLIGENCE: stage6_intelligence,
}


@celery_app.task(name="app.tasks.v3.orchestrate", queue="enrichment")
def orchestrate_event_intelligence(lead_id: str, run_id: str | None = None,
                                   job_id: str | None = None) -> str:
    """Entry point — creates a run, stores the job_id, kicks off Stage 1."""
    rid = run_id or str(uuid4())
    if job_id:
        _save_job_id(UUID(rid), job_id)
    stage1_identity.delay(rid, lead_id)
    return rid
