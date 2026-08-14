"""Structured logging configuration backed by structlog.

Logs are emitted as JSON in production and human-friendly in development.
A small set of context vars (``request_id``, ``user_id``, ``trace_id``)
is propagated automatically through middleware so every log line is
correlatable to the originating HTTP request.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from src.core.config import Settings, get_settings

# ----------------------------------------------------------------------------
# Per-request context (populated by middleware).
# ----------------------------------------------------------------------------
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)


# ----------------------------------------------------------------------------
# Sensitive fields are scrubbed from any log record before rendering.
# ----------------------------------------------------------------------------
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "id_token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "apikey",
        "asaas_api_key",
        "creditcard",
        "credit_card",
        "card_number",
        "cvv",
        "private_key",
        "cookie",
        "set-cookie",
    }
)
_REDACTED = "[REDACTED]"


def _scrub_sensitive(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    """Recursively redact sensitive values from any log payload."""

    def _walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: (_REDACTED if k.lower() in _SENSITIVE_KEYS else _walk(v))
                for k, v in value.items()
            }
        if isinstance(value, list | tuple):
            return type(value)(_walk(v) for v in value)
        return value

    return _walk(event_dict)  # type: ignore[no-any-return]


def _inject_request_context(
    _logger: Any, _name: str, event_dict: EventDict
) -> EventDict:
    """Attach request-scoped identifiers (request_id, trace_id, user_id) if present."""
    if (rid := request_id_ctx.get()) is not None:
        event_dict.setdefault("request_id", rid)
    if (tid := trace_id_ctx.get()) is not None:
        event_dict.setdefault("trace_id", tid)
    if (uid := user_id_ctx.get()) is not None:
        event_dict.setdefault("user_id", uid)
    return event_dict


def setup_logging(settings: Settings | None = None) -> None:
    """Configure structlog + stdlib logging.

    Safe to call multiple times (e.g. test setup); the underlying stdlib root
    handler is replaced on each call.
    """
    settings = settings or get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        _inject_request_context,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        _scrub_sensitive,
    ]

    if settings.LOG_JSON:
        renderer: Processor = structlog.processors.JSONRenderer()
        shared_processors.append(structlog.processors.dict_tracebacks)
        shared_processors.append(structlog.processors.EventRenamer("message"))
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
        shared_processors.append(structlog.processors.format_exc_info)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(message)s") if settings.LOG_JSON else logging.Formatter()
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    for noisy in ("uvicorn.access", "uvicorn.error", "pymongo", "asyncio"):
        logging.getLogger(noisy).setLevel(
            logging.WARNING if not settings.DEBUG else log_level
        )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog-bound logger; prefer this over ``logging.getLogger``."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]


__all__ = [
    "get_logger",
    "request_id_ctx",
    "setup_logging",
    "trace_id_ctx",
    "user_id_ctx",
]
