"""v3 agent error taxonomy. Drives retry vs. fail-fast classification."""
from __future__ import annotations


class AgentError(Exception):
    """Base for all v3 agent/tool errors."""


class RetryableError(AgentError):
    """Transient — safe to retry (network, 429, 5xx, timeout)."""


class FatalError(AgentError):
    """Permanent — retrying will not help (401/403, malformed request)."""


class BudgetExceededError(FatalError):
    """LLM/API spend circuit breaker tripped — abort cleanly, do not retry."""


class UpstreamMissingError(FatalError):
    """A required upstream agent result is absent — agent cannot run."""


def classify_http(status: int, provider: str, body: str = "") -> None:
    """Raise the correct error class for a non-2xx HTTP status, or return None."""
    if status < 400:
        return
    if status in (408, 425, 429) or status >= 500:
        raise RetryableError(f"{provider} HTTP {status}: {body[:200]}")
    raise FatalError(f"{provider} HTTP {status}: {body[:200]}")
