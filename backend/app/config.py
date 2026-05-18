"""
OutreachAI – Application Configuration.

All settings are loaded from environment variables / .env files via pydantic-settings.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────
    app_name: str = "OutreachAI"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    secret_key: str = Field(..., min_length=32)
    allowed_origins: list[str] = ["http://localhost:3000"]

    # ── Database ─────────────────────────────────────────
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://outreach:outreach@localhost:5432/outreachai"
    )
    readonly_database_url: str = ""  # chatbot_readonly user; falls back to database_url
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_echo: bool = False

    # ── Redis ────────────────────────────────────────────
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_cache_ttl: int = 3600

    # ── JWT / Auth ───────────────────────────────────────
    jwt_algorithm: str = "RS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    jwt_private_key_path: str = "keys/jwt-private.pem"
    jwt_public_key_path: str = "keys/jwt-public.pem"

    # ── AI / LLM ─────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_fast_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    anthropic_fast_model: str = "claude-haiku-4-5-20251001"
    llm_max_retries: int = 3
    llm_request_timeout: int = 60
    llm_monthly_budget_usd: float = 500.0

    # ── Web Research ─────────────────────────────────────
    apollo_api_key: str = ""
    pdl_api_key: str = ""
    perplexity_api_key: str = ""
    serpapi_api_key: str = ""
    firecrawl_api_key: str = ""
    tavily_api_key: str = ""

    # ── Email ────────────────────────────────────────────
    sendgrid_api_key: str = ""
    ses_region: str = "us-east-1"
    email_tracking_domain: str = "track.outreach.ai"
    email_default_from_name: str = "LaunchHouse Events"
    email_default_from: str = "outreach@launchhouse.events"
    sendgrid_from_email: str = ""  # Overrides email_default_from when set
    # If set, ALL outbound emails are redirected here (for testing)
    test_email_override: str = ""
    # Sender identity (used when no SenderAccount row exists)
    sender_first_name: str = "Snehdeep"
    sender_calendar_link: str = "#"
    company_site_url: str = "https://launchhouse.events/"

    # ── Testing / Dev helpers ─────────────────────────────
    # When set to "minutes" (or "seconds", "hours"), campaign step delay_days
    # values are treated as that unit instead of days. UI still shows "days".
    step_delay_unit: str = "days"  # days | hours | minutes | seconds
    # IMAP credentials for background reply polling (check_replies beat task)
    gmail_imap_user: str = ""
    gmail_app_password: str = ""
    # SendGrid Inbound Parse webhook secret (appended as ?secret= in webhook URL)
    sendgrid_webhook_secret: str = ""

    # ── Signal pipeline (v2) ─────────────────────────────
    # Set to True to route new leads through run_signal_pipeline instead of run_enrichment_pipeline.
    # v1 (run_enrichment_pipeline) remains unchanged and is still used when this flag is False.
    use_signal_pipeline: bool = False

    # ── Pipeline version selector ────────────────────────
    # "v1" = legacy LLM scorer, "v2" = signal pipeline, "v3" = event intelligence engine.
    # When "v3", EnrichmentService dispatches orchestrate_event_intelligence.
    pipeline_version: str = "v3"

    # ── Cvent customer assumption ─────────────────────────
    # When True, all leads are treated as confirmed Cvent customers regardless of
    # whether the web-search detection finds a Cvent page.  Effects:
    #   • Gate 1: CVENT check is bypassed (leads are never cut on cvent alone)
    #   • Scoring: CVENT signal gets a baseline urgency of 0.40 when detection returns
    #     0, representing "confirmed customer, upcoming event timing not found"
    assume_cvent_customer: bool = False

    # ── Celery ───────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── S3 / Storage ─────────────────────────────────────
    s3_bucket: str = "outreachai-uploads"
    s3_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # ── Sentry ───────────────────────────────────────────
    sentry_dsn: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
