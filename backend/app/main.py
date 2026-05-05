"""
OutreachAI – FastAPI Application Factory.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from app.config import get_settings
from app.db.session import engine
from app.middleware.tenant import TenantMiddleware
from app.middleware.logging import LoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.api import router as api_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    settings = get_settings()
    logger.info("starting_outreachai", environment=settings.environment)

    # Initialize Sentry in production
    if settings.sentry_dsn and settings.is_production:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

    yield

    # Graceful shutdown
    await engine.dispose()
    logger.info("shutdown_outreachai")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Custom middleware (order matters: last added = first executed) ──
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(TenantMiddleware)
    app.add_middleware(LoggingMiddleware)

    # ── Prometheus metrics endpoint ──────────────────────
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # ── API routes ───────────────────────────────────────
    app.include_router(api_router, prefix="/api/v1")

    # ── Health check ─────────────────────────────────────
    @app.get("/health")
    async def health():
        return {"status": "healthy", "version": "0.1.0"}

    return app


app = create_app()
