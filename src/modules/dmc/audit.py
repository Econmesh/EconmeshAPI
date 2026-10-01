"""Append-only audit records for DMC actions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from src.modules.dmc.model import AuditAction, AuditEventDocument
from src.modules.dmc.repository import AuditEventsRepository


def audit_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): audit_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [audit_value(item) for item in value]
    return value


class AuditLog:
    def __init__(self, repository: AuditEventsRepository) -> None:
        self._repository = repository

    async def record(
        self,
        action: AuditAction | str,
        *,
        resource_type: str,
        resource_id: UUID | str | None = None,
        actor_user_id: UUID | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> AuditEventDocument:
        action_value = action.value if isinstance(action, AuditAction) else action
        doc = AuditEventDocument(
            actor_user_id=actor_user_id,
            action=action_value,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            before=audit_value(before) if before is not None else None,
            after=audit_value(after) if after is not None else None,
        )
        return await self._repository.create(doc)


__all__ = ["AuditLog", "audit_value"]
