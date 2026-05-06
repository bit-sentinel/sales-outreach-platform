"""API router registry – aggregates all endpoint routers."""

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.leads import router as leads_router
from app.api.routes.companies import router as companies_router
from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.messages import router as messages_router
from app.api.routes.replies import router as replies_router
from app.api.routes.templates import router as templates_router
from app.api.routes.enrichment import router as enrichment_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.admin import router as admin_router
from app.api.routes.chat import router as chat_router
from app.api.routes.system import router as system_router
from app.api.routes.webhooks import router as webhooks_router

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(leads_router, prefix="/leads", tags=["Leads"])
router.include_router(companies_router, prefix="/companies", tags=["Companies"])
router.include_router(campaigns_router, prefix="/campaigns", tags=["Campaigns"])
router.include_router(messages_router, prefix="/messages", tags=["Messages"])
router.include_router(replies_router, prefix="/replies", tags=["Replies"])
router.include_router(templates_router, prefix="/templates", tags=["Templates"])
router.include_router(enrichment_router, prefix="/enrichment", tags=["Enrichment"])
router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
router.include_router(admin_router, prefix="/admin", tags=["Admin"])
router.include_router(system_router, prefix="/system", tags=["System"])
router.include_router(chat_router, prefix="/chat", tags=["Chat"])
router.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])
