"""
SignalCacheService — Redis-first + DB fallback cache for company-level signal data.

Key structure:  "signal:{signal_type}:{sha256(domain_or_company)[:20]}"

Strategy:
  1. Read → try Redis first, fall back to DB, warm Redis on DB hit
  2. Write → write Redis + DB in parallel
  3. Keys are company-level (no tenant_id) — signals are facts about companies,
     not tenants.  Multiple leads / tenants for the same company share cached signals.

Usage:
    cache = SignalCacheService(redis_client=redis, db=session)
    result = await cache.get("cvent_events", domain="acme.com", company_name="Acme Corp")
    if result is None:
        result = await CventSignalAgent().collect(...)
        await cache.set(result)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.agents.signals.base_signal import SignalResult, make_cache_key

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SignalCacheService:
    def __init__(
        self,
        redis_client: "aioredis.Redis | None" = None,
        db: "AsyncSession | None" = None,
    ) -> None:
        self._redis = redis_client
        self._db = db

    # ── Public API ──────────────────────────────────────────────────────────

    async def get(
        self,
        signal_type: str,
        domain: str | None = None,
        company_name: str = "",
    ) -> SignalResult | None:
        key = make_cache_key(signal_type, domain, company_name)

        # 1. Redis
        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    data = json.loads(raw)
                    return self._deserialize(data)
            except Exception as exc:
                logger.warning("[signal_cache] Redis GET failed: %s", exc)

        # 2. DB fallback
        if self._db:
            try:
                from sqlalchemy import select, text
                from app.models.lead import SignalCache
                now = datetime.now(timezone.utc)
                result = await self._db.execute(
                    select(SignalCache).where(
                        SignalCache.cache_key == key,
                        SignalCache.expires_at > now,
                    )
                )
                row: SignalCache | None = result.scalar_one_or_none()
                if row:
                    sig = SignalResult(
                        signal_type=row.signal_type,
                        value=row.value,
                        evidence=row.evidence or {},
                        provider=row.provider or "cache",
                        confidence=row.confidence,
                    )
                    # Warm Redis so next hit is fast
                    await self._warm_redis(key, sig, row.expires_at)
                    return sig
            except Exception as exc:
                logger.warning("[signal_cache] DB GET failed: %s", exc)

        return None

    async def set(
        self,
        result: SignalResult,
        domain: str | None = None,
        company_name: str = "",
    ) -> None:
        key = make_cache_key(result.signal_type, domain, company_name)
        ttl_seconds = result.ttl_hours * 3600

        data = {
            "signal_type": result.signal_type,
            "value":        result.value,
            "evidence":     result.evidence,
            "provider":     result.provider,
            "confidence":   result.confidence,
            "weight":       result.weight,
            "ttl_hours":    result.ttl_hours,
        }
        payload = json.dumps(data, default=str)

        # Redis write
        if self._redis:
            try:
                await self._redis.setex(key, ttl_seconds, payload)
            except Exception as exc:
                logger.warning("[signal_cache] Redis SET failed: %s", exc)

        # DB write (upsert)
        if self._db:
            try:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                from app.models.lead import SignalCache
                now = datetime.now(timezone.utc)
                from datetime import timedelta
                expires_at = now + timedelta(seconds=ttl_seconds)

                stmt = pg_insert(SignalCache).values(
                    cache_key=key,
                    signal_type=result.signal_type,
                    value=result.value,
                    evidence=result.evidence,
                    provider=result.provider,
                    confidence=result.confidence,
                    expires_at=expires_at,
                ).on_conflict_do_update(
                    index_elements=["cache_key"],
                    set_={
                        "value":       result.value,
                        "evidence":    result.evidence,
                        "provider":    result.provider,
                        "confidence":  result.confidence,
                        "expires_at":  expires_at,
                        "updated_at":  now,
                    },
                )
                await self._db.execute(stmt)
                await self._db.commit()
            except Exception as exc:
                logger.warning("[signal_cache] DB SET failed: %s", exc)

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _warm_redis(
        self,
        key: str,
        result: SignalResult,
        expires_at: datetime,
    ) -> None:
        if not self._redis:
            return
        now = datetime.now(timezone.utc)
        remaining_seconds = int((expires_at - now).total_seconds())
        if remaining_seconds <= 0:
            return
        data = {
            "signal_type": result.signal_type,
            "value":        result.value,
            "evidence":     result.evidence,
            "provider":     result.provider,
            "confidence":   result.confidence,
            "weight":       result.weight,
            "ttl_hours":    result.ttl_hours,
        }
        try:
            await self._redis.setex(key, remaining_seconds, json.dumps(data, default=str))
        except Exception as exc:
            logger.debug("[signal_cache] Redis warm failed: %s", exc)

    @staticmethod
    def _deserialize(data: dict) -> SignalResult:
        return SignalResult(
            signal_type=data["signal_type"],
            value=data["value"],
            evidence=data.get("evidence") or {},
            provider=data.get("provider", "cache"),
            confidence=data.get("confidence", 1.0),
        )
