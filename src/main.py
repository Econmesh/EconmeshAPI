"""FastAPI application factory and entry-point.

This module wires every cross-cutting concern (settings, logging, mongo, redis,
firebase, middleware, exception handlers, routers) into a single FastAPI app.

Run locally::

    poetry run uvicorn src.main:app --reload

Run in production (gunicorn + uvicorn workers)::

    poetry run gunicorn src.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import ORJSONResponse

from src.core.config import Settings, get_settings
from src.core.database import mongo
from src.core.exceptions import register_exception_handlers
from src.core.firebase import firebase
from src.core.logging import get_logger, setup_logging
from src.infrastructure.redis.client import redis_manager
from src.modules.admin import router as admin_router
from src.modules.auth import router as auth_router
from src.modules.blockchain import router as blockchain_router
from src.modules.coming_soon import router as coming_soon_router
from src.modules.circularity import router as circularity_router
from src.modules.companies import router as companies_router
from src.modules.files import router as files_router
from src.modules.opportunities import router as opportunities_router
from src.modules.notifications import router as notifications_router
from src.modules.support import router as support_router
from src.modules.users import router as users_router
from src.shared.middleware import (
    AccessLogMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    TimeoutMiddleware,
)
from src.shared.schemas.responses import HealthResponse


# ---------------------------------------------------------------------------
# Lifespan — connect/disconnect external resources around the running app.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(settings)
    log = get_logger(__name__)

    log.info(
        "app_starting",
        env=str(settings.ENV),
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
    )

    await mongo.connect()
    await redis_manager.connect()
    firebase.init()

    log.info("mail_configured", enabled=settings.MAIL_ENABLED, host=settings.SMTP_HOST or None)
    log.info("app_ready")
    try:
        yield
    finally:
        log.info("app_shutting_down")
        firebase.shutdown()
        await redis_manager.close()
        await mongo.close()
        log.info("app_stopped")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a configured FastAPI instance.

    Kept as a factory so tests can build isolated apps with overridden settings.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Econmesh enterprise API — circular economy, ESG, blockchain.",
        default_response_class=ORJSONResponse,
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        openapi_url=settings.openapi_url,
        lifespan=lifespan,
    )

    _configure_middleware(app, settings)
    register_exception_handlers(app)
    _register_routers(app, settings)
    _register_root_endpoints(app, settings)

    return app


# ---------------------------------------------------------------------------
# Middleware wiring — Starlette executes middleware in REVERSE registration
# order, so the LAST one added runs FIRST on the way in. We add from
# innermost-to-outermost so the outer chain is:
#
#     RequestID → AccessLog → SecurityHeaders → CORS → TrustedHost → Timeout
# ---------------------------------------------------------------------------
def _configure_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        TimeoutMiddleware,
        timeout_seconds=settings.REQUEST_TIMEOUT_SECONDS,
    )

    if settings.TRUSTED_HOSTS and settings.TRUSTED_HOSTS != ["*"]:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.TRUSTED_HOSTS,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Trace-ID"],
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIDMiddleware)


# ---------------------------------------------------------------------------
# Routers — every domain module is mounted under /api/v1.
# ---------------------------------------------------------------------------
def _register_routers(app: FastAPI, settings: Settings) -> None:
    api_v1 = APIRouter(prefix=settings.API_V1_PREFIX)
    api_v1.include_router(auth_router)
    api_v1.include_router(admin_router)
    api_v1.include_router(coming_soon_router)
    api_v1.include_router(users_router)
    api_v1.include_router(companies_router)
    api_v1.include_router(opportunities_router)
    api_v1.include_router(notifications_router)
    api_v1.include_router(support_router)
    api_v1.include_router(circularity_router)
    api_v1.include_router(files_router)
    api_v1.include_router(blockchain_router)
    app.include_router(api_v1)


# ---------------------------------------------------------------------------
# Root-level endpoints (health probes, not versioned)
# ---------------------------------------------------------------------------
def _register_root_endpoints(app: FastAPI, settings: Settings) -> None:
    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["health"],
        status_code=status.HTTP_200_OK,
        summary="Liveness probe — process is up.",
    )
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get(
        "/health/ready",
        response_model=HealthResponse,
        tags=["health"],
        summary="Readiness probe — external deps reachable.",
    )
    async def readiness() -> HealthResponse:
        checks: dict[str, str] = {}
        mongo_ok = await mongo.ping()
        redis_ok = await redis_manager.ping()
        checks["mongo"] = "ok" if mongo_ok else "down"
        checks["redis"] = "ok" if redis_ok else "down"

        overall = "ok" if mongo_ok and redis_ok else "degraded"
        return HealthResponse(status=overall, checks=checks)  # type: ignore[arg-type]

    @app.get("/", tags=["root"], include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": settings.docs_url or "disabled",
        }


# Module-level app used by uvicorn/gunicorn (``src.main:app``).
app = create_app()
