"""Attach security-related response headers (OWASP Secure Headers baseline)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_DEFAULT_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
}

_STRICT_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
_DOCS_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "font-src 'self' data: https://cdn.jsdelivr.net; "
    "connect-src 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add OWASP-recommended security headers to every response.

    HSTS is conditional on HTTPS-aware deployments and is added only when
    the request was already TLS (avoids breaking local dev over HTTP).
    """

    def __init__(self, app: object, *, hsts: bool = True) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._hsts = hsts

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for header, value in _DEFAULT_HEADERS.items():
            response.headers.setdefault(header, value)
        response.headers.setdefault(
            "Content-Security-Policy", self._csp_for_path(request.url.path)
        )

        if self._hsts and request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    @staticmethod
    def _csp_for_path(path: str) -> str:
        if path.startswith("/docs") or path.startswith("/redoc"):
            return _DOCS_CSP
        return _STRICT_CSP


__all__ = ["SecurityHeadersMiddleware"]
