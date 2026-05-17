"""
Base signal dataclass and abstract agent interface.

Each signal agent is responsible for exactly ONE signal type.
It collects evidence from one or more data sources, applies rule-based
scoring logic, and returns a SignalResult.  LLMs are only called when
unstructured text must be understood; rule engines handle the rest.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Signal weights ─────────────────────────────────────────────────────────
# Must sum to 1.0.  These are the ONLY scoring weights in the pipeline.
SIGNAL_WEIGHTS: dict[str, float] = {
    "cvent_events":   0.25,   # confirmed upcoming Cvent events (build pressure)
    "event_volume":   0.20,   # annual event program scale / complexity
    "org_fit":        0.20,   # contact seniority + company size band
    "hiring_signal":  0.15,   # active event-ops hiring
    "news_signal":    0.10,   # recent event-relevant news
    "industry_fit":   0.10,   # static industry fit lookup
}

# ── Signal-level cache TTLs (hours) ──────────────────────────────────────
SIGNAL_TTL_HOURS: dict[str, int] = {
    "cvent_events":   168,   # 7 days  – Cvent pages change slowly
    "event_volume":   336,   # 14 days – event calendar is stable
    "org_fit":        720,   # 30 days – company structure is stable
    "hiring_signal":   72,   # 3 days  – job postings change quickly
    "news_signal":     24,   # 1 day   – news is time-sensitive
    "industry_fit":  2160,   # 90 days – static lookup
}


@dataclass
class SignalResult:
    """Immutable result produced by one signal agent."""

    signal_type: str          # must be a key in SIGNAL_WEIGHTS
    value: float              # 0.0 – 1.0 normalised strength
    evidence: dict[str, Any]  # structured evidence (URLs, snippets, counts, dates)
    provider: str             # comma-separated list of data sources used
    confidence: float = 1.0  # how reliable is this result
    # Filled in automatically from SIGNAL_WEIGHTS / SIGNAL_TTL_HOURS
    weight: float = field(init=False)
    ttl_hours: int = field(init=False)

    def __post_init__(self) -> None:
        self.weight = SIGNAL_WEIGHTS.get(self.signal_type, 0.0)
        self.ttl_hours = SIGNAL_TTL_HOURS.get(self.signal_type, 24)
        self.value = max(0.0, min(1.0, float(self.value)))

    def weighted_contribution(self) -> float:
        return self.value * self.weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "value": self.value,
            "weight": self.weight,
            "weighted_contribution": self.weighted_contribution(),
            "evidence": self.evidence,
            "provider": self.provider,
            "confidence": self.confidence,
        }


def make_cache_key(signal_type: str, domain: str | None, company_name: str) -> str:
    """Deterministic cache key: SHA-256 of (signal_type + canonical identifier)."""
    identifier = (domain or company_name).lower().strip().replace("https://", "").replace("http://", "").strip("/")
    digest = hashlib.sha256(f"{signal_type}:{identifier}".encode()).hexdigest()[:20]
    return f"signal:{signal_type}:{digest}"


class BaseSignalAgent:
    """
    Abstract base for all signal agents.

    Subclasses implement `collect()`.  The base class provides:
    - Access to settings
    - A fast LLM (Claude Haiku) for lightweight extraction tasks
    - Logging helpers
    """

    signal_type: str = ""  # must be overridden

    def __init__(self) -> None:
        self.settings = get_settings()
        self._llm = None  # lazy-initialised

    def get_haiku(self, temperature: float = 0.1):
        """Return Claude Haiku – cheap LLM for structured extraction."""
        if self._llm is None:
            from langchain_anthropic import ChatAnthropic
            self._llm = ChatAnthropic(
                model=self.settings.anthropic_fast_model,
                temperature=temperature,
                api_key=self.settings.anthropic_api_key,
                max_retries=2,
            )
        return self._llm

    async def collect(self, **kwargs: Any) -> SignalResult:
        raise NotImplementedError

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, value))

    def _log(self, msg: str, *args: Any) -> None:
        logger.debug("[%s] " + msg, self.signal_type, *args)
