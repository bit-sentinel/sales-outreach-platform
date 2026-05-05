"""Simple token-bucket rate limiter using Redis."""

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-user rate limiting (keyed on Authorization token, not IP).
    Behind a reverse proxy all requests share the same IP, so IP-keying
    would incorrectly throttle every authenticated user together.
    """

    DEFAULT_LIMIT = 600  # requests per minute per user/token

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self._buckets: dict[str, list[float]] = {}

    SKIP_PATHS = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # Key on the auth token if present, otherwise fall back to IP
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            key = auth[7:40]  # first 33 chars of token is enough to distinguish users
        else:
            key = request.client.host if request.client else "unknown"

        now = time.time()
        window = 60  # 1 minute

        bucket = self._buckets.get(key, [])
        bucket = [t for t in bucket if now - t < window]

        if len(bucket) >= self.DEFAULT_LIMIT:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": "Rate limit exceeded",
                    "detail": f"Max {self.DEFAULT_LIMIT} requests per minute",
                },
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(self.DEFAULT_LIMIT),
                    "X-RateLimit-Remaining": "0",
                },
            )

        bucket.append(now)
        self._buckets[key] = bucket

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.DEFAULT_LIMIT)
        response.headers["X-RateLimit-Remaining"] = str(self.DEFAULT_LIMIT - len(bucket))
        return response
