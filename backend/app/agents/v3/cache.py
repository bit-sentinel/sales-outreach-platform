"""
v3 caching.

  AgentResultCache  — semantic, signal-level. Caches a whole AgentResult,
                      keyed by (signal_type, company-or-contact identifier).
                      Redis L1 + Postgres signal_cache L2.

  CallCache         — raw, call-level. Memoizes raw external-API responses so
                      duplicate calls (retries, sibling leads, sibling agents
                      for the same company) never re-hit the provider.
                      Process-local L0 + Redis L1.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from app.agents.v3.contracts import AgentResult, CacheScope, SignalType

logger = logging.getLogger(__name__)


def _norm(identifier: str) -> str:
    return (
        (identifier or "").lower().strip()
        .replace("https://", "").replace("http://", "").strip("/")
    )


def _hashed(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]
    return f"{prefix}:{digest}"


# ── Result cache ───────────────────────────────────────────────────────────
class AgentResultCache:
    """Redis L1 + Postgres signal_cache L2 for full AgentResult objects."""

    def __init__(self, redis_client=None, session_factory=None) -> None:
        self._redis = redis_client
        self._session_factory = session_factory

    @staticmethod
    def cache_key(signal: SignalType, scope: CacheScope, identifier: str) -> str:
        return _hashed("v3res", signal.value, scope.value, _norm(identifier))

    async def get(self, signal: SignalType, scope: CacheScope, identifier: str) -> AgentResult | None:
        key = self.cache_key(signal, scope, identifier)

        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    return self._deserialize(json.loads(raw))
            except Exception as exc:
                logger.warning("[v3cache] redis GET failed: %s", exc)

        if self._session_factory:
            ctx = self._session_factory()
            session = await ctx.__aenter__()
            try:
                from sqlalchemy import select
                from app.models.lead import SignalCache
                row = (await session.execute(
                    select(SignalCache).where(
                        SignalCache.cache_key == key,
                        SignalCache.expires_at > datetime.now(timezone.utc),
                    )
                )).scalar_one_or_none()
                if row and isinstance(row.evidence, dict):
                    result = self._deserialize(row.evidence)
                    await self._warm_redis(key, row.evidence, row.expires_at)
                    return result
            except Exception as exc:
                logger.warning("[v3cache] db GET failed: %s", exc)
            finally:
                await ctx.__aexit__(None, None, None)
        return None

    async def set(
        self, signal: SignalType, scope: CacheScope, identifier: str,
        result: AgentResult, ttl_hours: int,
    ) -> None:
        key = self.cache_key(signal, scope, identifier)
        ttl_s = ttl_hours * 3600
        snapshot = result.model_dump(mode="json")
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_s)
        payload = json.dumps(snapshot, default=str)

        if self._redis:
            try:
                await self._redis.setex(key, ttl_s, payload)
            except Exception as exc:
                logger.warning("[v3cache] redis SET failed: %s", exc)

        if self._session_factory:
            ctx = self._session_factory()
            session = await ctx.__aenter__()
            try:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                from app.models.lead import SignalCache
                stmt = pg_insert(SignalCache).values(
                    cache_key=key, signal_type=signal.value,
                    value=result.value, evidence=snapshot,
                    provider=",".join(result.providers) or None,
                    confidence=result.confidence, expires_at=expires_at,
                ).on_conflict_do_update(
                    index_elements=["cache_key"],
                    set_={"value": result.value, "evidence": snapshot,
                          "confidence": result.confidence, "expires_at": expires_at,
                          "updated_at": datetime.now(timezone.utc)},
                )
                await session.execute(stmt)
                await session.commit()
            except Exception as exc:
                logger.warning("[v3cache] db SET failed: %s", exc)
            finally:
                await ctx.__aexit__(None, None, None)

    async def _warm_redis(self, key: str, snapshot: dict, expires_at: datetime) -> None:
        if not self._redis:
            return
        remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds())
        if remaining > 0:
            try:
                await self._redis.setex(key, remaining, json.dumps(snapshot, default=str))
            except Exception:
                pass

    @staticmethod
    def _deserialize(snapshot: dict) -> AgentResult:
        result = AgentResult.model_validate(snapshot)
        result.cache_hit = True
        if result.completed_at:
            result.cache_age_s = int(
                (datetime.now(timezone.utc) - result.completed_at).total_seconds()
            )
        return result


# ── Call cache (raw API dedup) ─────────────────────────────────────────────
class CallCache:
    """
    Deduplicates raw external-API calls.

    L0 process-local dict  — kills retry + same-run duplicate calls.
    L1 Redis               — kills cross-run / cross-agent duplicates within TTL.

    `factory` SHOULD return a JSON-serializable value (the raw provider payload).
    Non-serializable returns are still deduped within the run via L0.
    """

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client
        self._local: dict[str, Any] = {}

    async def call(
        self, *, provider: str, dedup_key: str,
        factory: Callable[[], Awaitable[Any]], ttl_s: int = 3600,
    ) -> Any:
        h = _hashed("v3call", provider, dedup_key)

        if h in self._local:
            return self._local[h]

        if self._redis:
            try:
                raw = await self._redis.get(h)
                if raw is not None:
                    value = json.loads(raw)
                    self._local[h] = value
                    return value
            except Exception as exc:
                logger.debug("[v3callcache] redis miss/err: %s", exc)

        value = await factory()
        self._local[h] = value
        if self._redis:
            try:
                await self._redis.setex(h, ttl_s, json.dumps(value, default=str))
            except Exception as exc:
                logger.debug("[v3callcache] redis SET skipped: %s", exc)
        return value
