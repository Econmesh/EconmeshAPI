"""MongoDB connection lifecycle.

Uses the native PyMongo Async API (``pymongo.AsyncMongoClient``).
Motor reached end of life on 14-May-2026 — the async PyMongo client is
the official replacement and is GA since PyMongo 4.9.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from pymongo import AsyncMongoClient
from pymongo.server_api import ServerApi

from src.core.config import Settings, get_settings
from src.core.exceptions import ExternalServiceError
from src.core.logging import get_logger

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase

logger = get_logger(__name__)

_DEBUG_LOG_PATH = Path(__file__).resolve().parents[2] / "debug-88686b.log"


def _agent_debug_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict,
    run_id: str = "pre-fix",
) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "88686b",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        pass
    # endregion


def _configure_srv_dns_resolver() -> list[str]:
    """Prefer system DNS but add public resolvers for unreliable home routers."""
    import dns.asyncresolver
    import dns.resolver

    public_dns = ("8.8.8.8", "1.1.1.1")
    sync_resolver = dns.resolver.Resolver(configure=True)
    nameservers = [str(ns) for ns in sync_resolver.nameservers]
    for ns in public_dns:
        if ns not in nameservers:
            nameservers.append(ns)

    sync_resolver.nameservers = nameservers
    dns.resolver.default_resolver = sync_resolver

    async_resolver = dns.asyncresolver.Resolver(configure=False)
    async_resolver.nameservers = nameservers
    dns.asyncresolver.default_resolver = async_resolver
    return nameservers


class MongoClientManager:
    """Owns the async MongoDB client and exposes safe accessors.

    Lifecycle is driven by the FastAPI ``lifespan`` context. Outside of tests,
    a single instance is shared process-wide via the module-level ``mongo``.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: AsyncMongoClient | None = None
        self._db: AsyncDatabase | None = None

    # -------------------------------------------------------------- lifecycle
    async def connect(self) -> None:
        if self._client is not None:
            return

        uri = self._settings.MONGO_URI
        parsed = urlparse(uri)
        uri_host = uri.split("@")[-1].split("/")[0]
        is_srv = uri.startswith("mongodb+srv://")

        logger.info(
            "mongo_connecting",
            uri_host=uri_host,
            db=self._settings.MONGO_DB,
        )

        dns_probe: dict[str, object] = {"skipped": True}
        if is_srv:
            configured_nameservers = _configure_srv_dns_resolver()
            _agent_debug_log(
                hypothesis_id="E",
                location="database.py:connect:dns_configured",
                message="srv dns resolver configured",
                data={"nameservers": configured_nameservers},
                run_id="post-fix",
            )
            try:
                import dns.resolver

                resolver = dns.resolver.Resolver(configure=False)
                resolver.nameservers = configured_nameservers
                dns_probe = {
                    "nameservers": [str(ns) for ns in resolver.nameservers],
                    "timeout": resolver.timeout,
                    "lifetime": resolver.lifetime,
                }
                srv_fqdn = f"_mongodb._tcp.{parsed.hostname}"
                t0 = time.perf_counter()
                answers = resolver.resolve(srv_fqdn, "SRV")
                dns_probe["srv_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                dns_probe["srv_count"] = len(answers)
                dns_probe["srv_ok"] = True
            except Exception as exc:  # noqa: BLE001
                dns_probe["srv_ok"] = False
                dns_probe["srv_error"] = type(exc).__name__
                dns_probe["srv_error_msg"] = str(exc)[:300]

        _agent_debug_log(
            hypothesis_id="A",
            location="database.py:connect:uri",
            message="mongo uri and env",
            data={
                "env": str(self._settings.ENV),
                "is_srv": is_srv,
                "uri_scheme": parsed.scheme,
                "uri_host": parsed.hostname,
                "mongo_db": self._settings.MONGO_DB,
                "server_selection_timeout_ms": self._settings.MONGO_SERVER_SELECTION_TIMEOUT_MS,
            },
        )
        _agent_debug_log(
            hypothesis_id="B",
            location="database.py:connect:dns_probe",
            message="pre-connect dns probe",
            data=dns_probe,
        )

        self._client = AsyncMongoClient(
            self._settings.MONGO_URI,
            uuidRepresentation="standard",
            tz_aware=True,
            minPoolSize=self._settings.MONGO_MIN_POOL_SIZE,
            maxPoolSize=self._settings.MONGO_MAX_POOL_SIZE,
            serverSelectionTimeoutMS=self._settings.MONGO_SERVER_SELECTION_TIMEOUT_MS,
            server_api=ServerApi("1"),
            appname=self._settings.APP_NAME,
        )

        try:
            ping_t0 = time.perf_counter()
            await self._client.admin.command("ping")
            _agent_debug_log(
                hypothesis_id="D",
                location="database.py:connect:ping",
                message="mongo ping succeeded",
                data={"ping_ms": round((time.perf_counter() - ping_t0) * 1000, 1)},
            )
        except Exception as exc:  # noqa: BLE001 — re-raised as domain error
            _agent_debug_log(
                hypothesis_id="C",
                location="database.py:connect:ping_failed",
                message="mongo ping failed",
                data={
                    "exc_type": type(exc).__name__,
                    "exc_msg": str(exc)[:500],
                    "is_srv": is_srv,
                },
            )
            logger.error("mongo_connection_failed", error=str(exc))
            await self._client.close()
            self._client = None
            raise ExternalServiceError(
                "Failed to connect to MongoDB.",
                code="mongo_unavailable",
            ) from exc

        self._db = self._client[self._settings.MONGO_DB]
        logger.info("mongo_connected", db=self._settings.MONGO_DB)

    async def close(self) -> None:
        if self._client is None:
            return
        logger.info("mongo_closing")
        await self._client.close()
        self._client = None
        self._db = None

    # ---------------------------------------------------------------- access
    @property
    def client(self) -> AsyncMongoClient:
        if self._client is None:
            raise RuntimeError("MongoDB client not initialised; call connect() first.")
        return self._client

    @property
    def db(self) -> AsyncDatabase:
        if self._db is None:
            raise RuntimeError("MongoDB database not initialised; call connect() first.")
        return self._db

    def get_collection(self, name: str) -> AsyncCollection:
        return self.db[name]

    async def ping(self) -> bool:
        if self._client is None:
            return False
        try:
            await self._client.admin.command("ping")
        except Exception:  # noqa: BLE001
            return False
        return True


mongo = MongoClientManager()
"""Process-wide singleton — connect/close in the FastAPI lifespan."""


__all__ = ["MongoClientManager", "mongo"]
