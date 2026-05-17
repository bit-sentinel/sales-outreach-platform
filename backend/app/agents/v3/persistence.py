"""
Persist v3 agent output to the event-intelligence schema.

  persist_evidence        -> signal_evidence (immutable provenance ledger)
  persist_typed_signals   -> cvent_evidence / event_history / hiring_signals /
                             buying_intent_signals / org_graphs (domain detail)
  upsert_company_profile  -> company_event_profiles (canonical rollup)

Returns content_hash -> evidence UUID maps so the scoring engine can attach
evidence_ids to lead_score_breakdown rows.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.agents.v3.contracts import AgentResult, SignalType

logger = logging.getLogger(__name__)


async def persist_evidence(
    session, tenant_id: UUID, company_id: UUID, results: list[AgentResult],
) -> dict[str, UUID]:
    """Bulk-insert immutable evidence rows. Returns {content_hash: evidence_id}."""
    from app.models.event_intelligence import SignalEvidence

    hash_to_id: dict[str, UUID] = {}
    rows: list[SignalEvidence] = []
    for result in results:
        if not result.is_usable():
            continue
        for ev in result.evidence:
            ev_id = uuid.uuid4()
            hash_to_id[ev.content_hash] = ev_id
            rows.append(SignalEvidence(
                id=ev_id,
                tenant_id=tenant_id,
                company_id=company_id,
                signal_type=ev.signal_type.value,
                claim=ev.claim,
                source_type=ev.source_type.value,
                source_provider=ev.source_provider,
                source_url=ev.source_url,
                raw_snippet=ev.raw_snippet,
                raw_data=ev.raw_data,
                confidence=ev.confidence,
                observed_at=ev.observed_at,
                content_hash=ev.content_hash,
                agent=ev.agent,
            ))
    if rows:
        session.add_all(rows)
        await session.flush()
    return hash_to_id


async def persist_typed_signals(
    session, tenant_id: UUID, company_id: UUID,
    results: dict[SignalType, AgentResult], evidence_ids: list[UUID],
) -> None:
    """Write domain-detail rows from agent payloads. Best-effort per table."""
    from app.models.event_intelligence import (
        CventEvidence, EventHistory, HiringSignal, OrgGraph,
    )
    from sqlalchemy import update as sa_update

    # ── Cvent ──────────────────────────────────────────────────────────────
    cvent = results.get(SignalType.CVENT)
    if cvent and cvent.is_usable():
        p = cvent.payload
        await session.execute(
            sa_update(CventEvidence)
            .where(CventEvidence.company_id == company_id, CventEvidence.is_current.is_(True))
            .values(is_current=False)
        )
        session.add(CventEvidence(
            tenant_id=tenant_id, company_id=company_id,
            detected=bool(p.get("detected")),
            detection_method=p.get("detection_method"),
            products=p.get("products") or [],
            cvent_subdomain=p.get("cvent_subdomain"),
            registration_urls=p.get("registration_urls") or [],
            confidence=cvent.confidence, is_current=True,
            source_url=(cvent.evidence[0].source_url if cvent.evidence else None),
            evidence_ids=evidence_ids, detail=p,
        ))

    # ── Event history ──────────────────────────────────────────────────────
    volume = results.get(SignalType.EVENT_VOLUME)
    if volume and volume.is_usable():
        for ev in (volume.payload.get("upcoming_events") or [])[:10]:
            session.add(EventHistory(
                tenant_id=tenant_id, company_id=company_id,
                event_name=ev.get("title") or ev.get("name"),
                event_type=ev.get("event_type"),
                attendee_estimate=ev.get("attendee_estimate"),
                platform=ev.get("platform"),
                is_upcoming=bool(ev.get("is_upcoming", True)),
                source_url=ev.get("url"),
                evidence_ids=evidence_ids, detail=ev,
            ))

    # ── Hiring ─────────────────────────────────────────────────────────────
    hiring = results.get(SignalType.HIRING)
    if hiring and hiring.is_usable():
        for role in (hiring.payload.get("roles") or [])[:15]:
            session.add(HiringSignal(
                tenant_id=tenant_id, company_id=company_id,
                role_title=role.get("title"),
                role_category=role.get("category"),
                seniority=role.get("seniority"),
                job_url=role.get("url"),
                location=role.get("location"),
                status="open",
                is_event_related=bool(role.get("is_event_related", True)),
                role_keywords=role.get("keywords") or [],
                evidence_ids=evidence_ids, detail=role,
            ))

    # ── Org graph (upsert 1:1) ─────────────────────────────────────────────
    org = results.get(SignalType.ORG_GRAPH)
    if org and org.is_usable():
        from sqlalchemy import select
        p = org.payload
        existing = (await session.execute(
            select(OrgGraph).where(OrgGraph.company_id == company_id)
        )).scalar_one_or_none()
        fields = dict(
            parent_company=p.get("parent_company"),
            headcount_total=p.get("headcount_total"),
            headcount_band=p.get("headcount_band"),
            location_count=p.get("location_count"),
            locations=p.get("locations") or [],
            departments=p.get("departments") or {},
            has_events_org=p.get("has_events_org"),
            has_marketing_org=p.get("has_marketing_org"),
            key_people=p.get("key_people") or [],
            structure_raw=p, evidence_ids=evidence_ids,
        )
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
        else:
            session.add(OrgGraph(tenant_id=tenant_id, company_id=company_id, **fields))


async def upsert_company_profile(
    session, tenant_id: UUID, company_id: UUID, rollup: dict[str, Any],
) -> None:
    """Upsert the canonical company_event_profiles rollup (1 row per company)."""
    from sqlalchemy import select
    from app.models.event_intelligence import CompanyEventProfile

    existing = (await session.execute(
        select(CompanyEventProfile).where(CompanyEventProfile.company_id == company_id)
    )).scalar_one_or_none()

    fields = dict(
        cvent_status=rollup.get("cvent_status", "unknown"),
        cvent_confidence=rollup.get("cvent_confidence"),
        event_volume_tier=rollup.get("event_volume_tier", "unknown"),
        estimated_events_per_year=rollup.get("estimated_events_per_year"),
        attendee_scale=rollup.get("attendee_scale"),
        event_complexity_score=rollup.get("event_complexity_score"),
        event_team_size=rollup.get("event_team_size"),
        event_team_under_resourced=rollup.get("event_team_under_resourced"),
        estimated_budget_band=rollup.get("estimated_budget_band"),
        budget_confidence=rollup.get("budget_confidence"),
        outsourcing_propensity=rollup.get("outsourcing_propensity"),
        outsourcing_tier=rollup.get("outsourcing_tier", "unknown"),
        overall_fit_score=rollup.get("overall_fit_score"),
        icp_fit=rollup.get("icp_fit"),
        data_completeness=rollup.get("data_completeness", 0.0),
        enrichment_version="v3",
        last_enriched_at=datetime.now(timezone.utc),
        next_refresh_due=rollup.get("next_refresh_due"),
        summary=rollup.get("summary"),
        raw_rollup=rollup,
    )
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
    else:
        session.add(CompanyEventProfile(
            tenant_id=tenant_id, company_id=company_id, **fields,
        ))
