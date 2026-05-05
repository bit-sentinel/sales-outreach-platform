"""AI chat assistant – streams Claude responses with read-only diagnostic tools."""

import json
import logging
import re
from typing import Any, AsyncIterator

import anthropic
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.deps import get_current_user, get_tenant_id
from app.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the OutreachAI assistant — an expert embedded inside an AI-powered B2B sales outreach platform.

The platform manages:
- **Leads** — imported contacts with AI enrichment, 10-signal scoring, and research data (events, news, LinkedIn signals)
- **Campaigns** — multi-step email sequences with AI-generated personalized emails, follow-up scheduling, and reply-gated conditions
- **Reply Inbox** — inbound replies with AI intent classification (interested / meeting_request / question / objection / not_now / unsubscribe / out_of_office / bounce / irrelevant), sentiment, and suggested responses
- **Analytics** — open rates, reply rates, lead conversion funnel

You have access to read-only diagnostic tools. Use them proactively when the user asks about system issues, errors, campaign problems, or platform behaviour. Don't wait to be asked — if a question implies checking logs, DB state, or queue depths, call the appropriate tool first.

You help the user with:
1. **Drafting reply emails** — given a lead's reply, craft the ideal response (concise, warm, action-oriented)
2. **Analyzing replies** — interpret intent/sentiment and recommend the right next step
3. **Campaign strategy** — advise on sequencing, timing, subject lines, and value props
4. **Lead prioritisation** — help decide which leads to pursue based on score/signals
5. **Debugging platform issues** — celery tasks, email delivery, IMAP polling, DB state
6. **General sales advice** — objection handling, follow-up cadence, tone calibration

Formatting rules:
- Be concise and direct — sales teams are busy
- Use bullet points for lists, bold for key terms
- When drafting an email, wrap it in a clear block so it's easy to copy
- Never pad responses with unnecessary preamble
"""

TOOLS: list[dict] = [
    {
        "name": "docker_ps",
        "description": "List all Docker containers with their names and health status.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "docker_logs",
        "description": (
            "Fetch recent logs from a Docker container. "
            "Available containers: outreachai-api, outreachai-frontend, "
            "outreachai-celery-worker, outreachai-celery-beat, "
            "outreachai-postgres, outreachai-redis, outreachai-caddy."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "container": {
                    "type": "string",
                    "description": "Container name e.g. outreachai-api",
                },
                "tail": {
                    "type": "integer",
                    "description": "Number of log lines to fetch (default 100, max 500)",
                    "default": 100,
                },
                "since": {
                    "type": "string",
                    "description": "Show logs since this duration e.g. '30m', '1h'",
                },
            },
            "required": ["container"],
        },
    },
    {
        "name": "db_query",
        "description": (
            "Run a read-only SELECT query against the production database. "
            "Returns up to 100 rows. Only SELECT statements are permitted."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A SQL SELECT query.",
                }
            },
            "required": ["sql"],
        },
    },
    {
        "name": "redis_info",
        "description": (
            "Inspect Redis / Celery state. "
            "Use section='queues' to see Celery queue depths, "
            "'memory' for memory usage, 'stats' for command stats."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": ["queues", "memory", "stats", "server", "all"],
                    "description": "What to inspect (default: queues)",
                }
            },
            "required": [],
        },
    },
    {
        "name": "system_health",
        "description": "Get application system health: database, Redis, and all Celery workers.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

MAX_CONTEXT_MESSAGES = 20
MAX_TOOL_ROUNDS = 12

_SAFE_SQL = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


# ── Tool handlers ──────────────────────────────────────────────────────────────

async def _tool_docker_ps() -> str:
    try:
        import docker as docker_sdk
        client = docker_sdk.from_env()
        containers = client.containers.list(all=True)
        lines = [f"{'NAME':<40} STATUS"]
        for c in containers:
            lines.append(f"{c.name:<40} {c.status}")
        client.close()
        return "\n".join(lines)
    except Exception as e:
        return f"docker ps error: {e}"


async def _tool_docker_logs(container: str, tail: int = 100, since: str | None = None) -> str:
    try:
        import docker as docker_sdk
        tail = min(int(tail), 500)
        client = docker_sdk.from_env()
        c = client.containers.get(container)
        kwargs: dict[str, Any] = {"tail": tail, "timestamps": True}
        if since:
            kwargs["since"] = since
        raw = c.logs(**kwargs)
        client.close()
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        return text[-10_000:]  # cap at 10 k chars
    except Exception as e:
        return f"docker logs error: {e}"


async def _tool_db_query(sql: str) -> str:
    if not _SAFE_SQL.match(sql.strip()):
        return "Error: only SELECT queries are allowed."
    # Append LIMIT if not present to prevent runaway queries
    if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        sql = sql.rstrip(";") + " LIMIT 100"
    try:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy import text
        settings = get_settings()
        url = settings.readonly_database_url or str(settings.database_url)
        engine = create_async_engine(url, pool_size=2, max_overflow=2, pool_pre_ping=True)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            result = await db.execute(text(sql))
            rows = result.fetchall()
            cols = list(result.keys())
        await engine.dispose()
        if not rows:
            return "Query returned 0 rows."
        lines = ["\t".join(str(c) for c in cols)]
        for row in rows:
            lines.append("\t".join("" if v is None else str(v) for v in row))
        return "\n".join(lines)
    except Exception as e:
        return f"DB query error: {e}"


async def _tool_redis_info(section: str = "queues") -> str:
    try:
        import redis.asyncio as aioredis
        settings = get_settings()

        if section == "queues":
            broker_url = settings.celery_broker_url or "redis://redis:6379/1"
            broker = aioredis.from_url(broker_url, decode_responses=True)
            queues = ["default", "enrichment", "ai", "email", "campaign"]
            lines = []
            for q in queues:
                depth = await broker.llen(q)
                lines.append(f"{q}: {depth} pending tasks")
            await broker.aclose()
            return "\n".join(lines)

        r = aioredis.from_url(str(settings.redis_url), decode_responses=True)
        info = await r.info(section if section != "all" else None)
        await r.aclose()
        return "\n".join(f"{k}: {v}" for k, v in info.items())
    except Exception as e:
        return f"Redis info error: {e}"


async def _tool_system_health() -> str:
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://127.0.0.1:8000/api/v1/system/health", timeout=10)
            data = resp.json()
        return json.dumps(data.get("data", data), indent=2)
    except Exception as e:
        return f"System health error: {e}"


async def _execute_tool(name: str, tool_input: dict) -> str:
    logger.info("chat tool call: %s %s", name, tool_input)
    if name == "docker_ps":
        return await _tool_docker_ps()
    if name == "docker_logs":
        return await _tool_docker_logs(**tool_input)
    if name == "db_query":
        return await _tool_db_query(tool_input.get("sql", ""))
    if name == "redis_info":
        return await _tool_redis_info(tool_input.get("section", "queues"))
    if name == "system_health":
        return await _tool_system_health()
    return f"Unknown tool: {name}"


# ── Models ────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    _tenant_id: str = Depends(get_tenant_id),
    _user=Depends(get_current_user),
):
    settings = get_settings()
    messages = body.messages[-MAX_CONTEXT_MESSAGES:]

    async def event_stream() -> AsyncIterator[str]:
        try:
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            msgs: list[dict] = [{"role": m.role, "content": m.content} for m in messages]

            for _round in range(MAX_TOOL_ROUNDS):
                tool_calls: list[dict] = []
                stop_reason = "end_turn"

                async with client.messages.stream(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    messages=msgs,
                    tools=TOOLS,
                ) as stream:
                    async for event in stream:
                        if getattr(event, "type", None) == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            if delta and getattr(delta, "type", None) == "text_delta":
                                yield f"data: {json.dumps({'text': delta.text})}\n\n"

                    final = await stream.get_final_message()
                    stop_reason = final.stop_reason or "end_turn"
                    for block in final.content:
                        if block.type == "tool_use":
                            tool_calls.append({"id": block.id, "name": block.name, "input": block.input})

                if stop_reason != "tool_use" or not tool_calls:
                    break

                # Add assistant turn (with tool_use blocks) to history.
                # Manually serialize to exclude SDK-internal fields (e.g. parsed_output)
                # that the API rejects when sent back.
                def _block_to_dict(b) -> dict:
                    if b.type == "text":
                        return {"type": "text", "text": b.text}
                    if b.type == "tool_use":
                        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                    return {"type": b.type}

                msgs.append({"role": "assistant", "content": [_block_to_dict(b) for b in final.content]})

                # Execute each tool, stream activity events to frontend
                tool_results = []
                for tc in tool_calls:
                    yield f"data: {json.dumps({'type': 'tool_start', 'name': tc['name'], 'input': tc['input']})}\n\n"
                    result = await _execute_tool(tc["name"], tc["input"])
                    yield f"data: {json.dumps({'type': 'tool_done', 'name': tc['name']})}\n\n"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": result,
                    })

                msgs.append({"role": "user", "content": tool_results})

            yield "data: [DONE]\n\n"

        except Exception as exc:
            logger.error("chat_stream error: %s", exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
