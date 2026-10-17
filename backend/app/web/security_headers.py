"""Security response headers (T48, spec/14): CSP, HSTS, nosniff, framing, referrer, permissions."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from backend.app.config import settings

# Templates still use inline <script>/<style> and onclick handlers, so script-src/style-src
# carry 'unsafe-inline'. Everything else is locked to the same origin.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "connect-src 'self'; "
    "worker-src 'self'; "
    "manifest-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

STATIC_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), geolocation=(), payment=(), microphone=(self)",
}

HSTS_VALUE = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every response without overriding ones a route set itself."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for name, value in STATIC_HEADERS.items():
            response.headers.setdefault(name, value)
        if settings.ENVIRONMENT == "production":
            response.headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
        return response
