"""Tenant isolation middleware – extracts tenant_id from JWT and attaches to request state."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Extracts tenant context from the JWT token (decoded by auth dependency)
    and makes it available on request.state for downstream services.
    This is a lightweight pass-through; the actual tenant_id enforcement
    happens in service-layer queries via the get_tenant_id dependency.
    """

    SKIP_PATHS = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # tenant_id will be set by the auth dependency via get_tenant_id
        request.state.tenant_id = None
        return await call_next(request)
