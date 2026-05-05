# Root conftest — set env vars BEFORE any app module is imported.
import os

# Minimal env so pydantic-settings/app.db won't choke at import time.
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-32chars!")
os.environ.setdefault(
    "DATABASE_URL",
    os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://outreach:outreach@localhost:5432/outreachai_test",
    ),
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/15")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
