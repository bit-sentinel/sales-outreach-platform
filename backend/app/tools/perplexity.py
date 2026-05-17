"""Perplexity helpers for deep company and event research."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PERPLEXITY_CHAT_URL = "https://api.perplexity.ai/chat/completions"


async def research_deep(
    query: str,
    api_key: str,
    *,
    model: str = "sonar-pro",
) -> dict[str, Any]:
    """Run a cited research query through Perplexity."""
    if not api_key or not query:
        return {}

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You research B2B event teams that already use Cvent. Focus on upcoming "
                    "events, event program scale, hiring or growth signals, and cold-email "
                    "personalization hooks. Keep findings factual and cite sources."
                ),
            },
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(PERPLEXITY_CHAT_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("Perplexity research failed for %r: %s", query, exc)
        return {}

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return {
        "answer": message.get("content", ""),
        "citations": data.get("citations") or [],
        "model": data.get("model") or model,
        "raw": data,
    }