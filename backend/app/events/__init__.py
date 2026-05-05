"""
Redis Streams-based event bus for inter-service communication.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

from app.config import get_settings


class EventBus:
    """Publish/subscribe events via Redis Streams."""

    STREAMS = {
        "lead_events": "lead-events-stream",
        "enrichment_events": "enrichment-events-stream",
        "campaign_events": "campaign-events-stream",
        "email_events": "email-events-stream",
        "reply_events": "reply-events-stream",
        "ai_events": "ai-events-stream",
        "system_events": "system-events-stream",
    }

    def __init__(self):
        settings = get_settings()
        self._redis = redis.from_url(str(settings.redis_url), decode_responses=True)

    async def publish(
        self,
        stream: str,
        event_type: str,
        data: dict[str, Any],
        tenant_id: str | None = None,
    ) -> str:
        """Publish an event to a Redis Stream."""
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id or "",
            "data": json.dumps(data),
        }
        stream_key = self.STREAMS.get(stream, stream)
        message_id = await self._redis.xadd(stream_key, event)
        return message_id

    async def subscribe(
        self,
        stream: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[dict]:
        """Read events from a consumer group."""
        stream_key = self.STREAMS.get(stream, stream)

        # Ensure consumer group exists
        try:
            await self._redis.xgroup_create(
                stream_key, consumer_group, id="0", mkstream=True
            )
        except redis.ResponseError:
            pass  # Group already exists

        messages = await self._redis.xreadgroup(
            consumer_group,
            consumer_name,
            {stream_key: ">"},
            count=count,
            block=block_ms,
        )

        events = []
        for _stream_name, stream_messages in messages:
            for msg_id, fields in stream_messages:
                event = {
                    "message_id": msg_id,
                    "event_id": fields.get("event_id", ""),
                    "event_type": fields.get("event_type", ""),
                    "timestamp": fields.get("timestamp", ""),
                    "tenant_id": fields.get("tenant_id", ""),
                    "data": json.loads(fields.get("data", "{}")),
                }
                events.append(event)

        return events

    async def ack(
        self, stream: str, consumer_group: str, message_id: str
    ) -> None:
        """Acknowledge a processed message."""
        stream_key = self.STREAMS.get(stream, stream)
        await self._redis.xack(stream_key, consumer_group, message_id)

    async def close(self) -> None:
        await self._redis.close()


# Singleton
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
