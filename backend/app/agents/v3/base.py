"""
BaseIntelligenceAgent — the abstract interface + execution template.

Subclasses implement ONLY `_collect()`. The base provides, uniformly:
  • cache lookup / write          (AgentResultCache)
  • raw API-call deduplication    (CallCache, via self.call())
  • retry with backoff            (tenacity, retryable errors only)
  • per-attempt timeout
  • graceful degradation          (failure -> FAILED result, never raises)
  • timing / cost capture
  • evidence stamping
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, ClassVar

from tenacity import (
    AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential,
)

from app.agents.v3.cache import AgentResultCache, CallCache
from app.agents.v3.contracts import (
    AgentContext, AgentResult, AgentStatus, CacheScope, SignalType, utcnow,
)
from app.agents.v3.errors import FatalError, RetryableError
from app.config import get_settings

logger = logging.getLogger(__name__)


class BaseIntelligenceAgent(ABC):
    # ── declared by every subclass ─────────────────────────────────────────
    signal_type: ClassVar[SignalType]
    stage: ClassVar[str]                       # PipelineStage value
    cache_scope: ClassVar[CacheScope] = CacheScope.COMPANY
    cache_ttl_hours: ClassVar[int] = 168
    max_attempts: ClassVar[int] = 3
    timeout_s: ClassVar[float] = 45.0
    depends_on: ClassVar[tuple[SignalType, ...]] = ()

    def __init__(
        self,
        result_cache: AgentResultCache,
        call_cache: CallCache,
        settings: Any = None,
    ) -> None:
        self.result_cache = result_cache
        self.call_cache = call_cache
        self.settings = settings or get_settings()

    @property
    def name(self) -> str:
        return self.__class__.__name__

    # ── public template method — DO NOT override ───────────────────────────
    async def run(self, ctx: AgentContext) -> AgentResult:
        started = utcnow()

        if not ctx.force_refresh:
            cached = await self.result_cache.get(
                self.signal_type, self.cache_scope, self._discriminator(ctx)
            )
            if cached is not None:
                cached.status = AgentStatus.CACHED
                return cached

        skip_reason = self._precondition(ctx)
        if skip_reason is not None:
            return self._terminal(AgentStatus.SKIPPED, started, error=skip_reason)

        attempts = 0
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((RetryableError, asyncio.TimeoutError)),
                stop=stop_after_attempt(self.max_attempts),
                wait=wait_exponential(multiplier=1, min=2, max=20),
                reraise=True,
            ):
                with attempt:
                    attempts = attempt.retry_state.attempt_number
                    result = await asyncio.wait_for(
                        self._collect(ctx), timeout=self.timeout_s
                    )
        except FatalError as exc:
            logger.warning("[%s] fatal: %s", self.name, exc)
            return self._terminal(AgentStatus.FAILED, started, error=str(exc),
                                  attempts=attempts)
        except Exception as exc:
            logger.warning("[%s] failed after %d attempts: %s", self.name, attempts, exc)
            return self._terminal(AgentStatus.FAILED, started, error=str(exc),
                                  attempts=attempts)

        result.signal_type = self.signal_type
        result.attempts = attempts
        result.started_at = started
        result.completed_at = utcnow()
        result.duration_ms = int((result.completed_at - started).total_seconds() * 1000)
        result.evidence = [
            e.model_copy(update={"agent": self.name}) for e in result.evidence
        ]
        if result.status not in (AgentStatus.OK, AgentStatus.PARTIAL):
            result.status = AgentStatus.OK

        if result.is_usable():
            await self.result_cache.set(
                self.signal_type, self.cache_scope, self._discriminator(ctx),
                result, self.cache_ttl_hours,
            )
        return result

    # ── helper: deduplicated external call ─────────────────────────────────
    async def call(
        self, *, provider: str, dedup_key: str,
        factory: Callable[[], Awaitable[Any]], ttl_s: int = 3600,
    ) -> Any:
        return await self.call_cache.call(
            provider=provider, dedup_key=dedup_key, factory=factory, ttl_s=ttl_s,
        )

    # ── abstract: the only thing subclasses implement ──────────────────────
    @abstractmethod
    async def _collect(self, ctx: AgentContext) -> AgentResult:
        """
        Collect data and return an AgentResult.

        MUST set: value, confidence, payload, evidence, providers.
        MAY raise RetryableError / FatalError; anything else is treated fatal.
        """
        raise NotImplementedError

    # ── overridable hooks ──────────────────────────────────────────────────
    def _precondition(self, ctx: AgentContext) -> str | None:
        for dep in self.depends_on:
            r = ctx.upstream.get(dep)
            if not (r and r.is_usable()):
                return f"missing upstream: {dep.value}"
        return None

    def _discriminator(self, ctx: AgentContext) -> str:
        if self.cache_scope is CacheScope.CONTACT and ctx.contact and ctx.contact.email:
            return ctx.contact.email
        return ctx.company.domain or ctx.company.name

    # ── internals ──────────────────────────────────────────────────────────
    def _terminal(
        self, status: AgentStatus, started, *, error: str | None = None,
        attempts: int = 0,
    ) -> AgentResult:
        end = utcnow()
        return AgentResult(
            signal_type=self.signal_type, status=status, value=0.0, confidence=0.0,
            error=error, attempts=attempts, started_at=started, completed_at=end,
            duration_ms=int((end - started).total_seconds() * 1000),
        )
