"""Pure queue selection for automatic DMC assignment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.shared.constants.roles import Role


@dataclass(frozen=True, slots=True)
class QueueCandidate:
    user_id: UUID
    queue_position: int
    available: bool
    is_active: bool
    role: Role
    created_at: datetime


def next_in_queue(candidates: list[QueueCandidate]) -> QueueCandidate | None:
    """Return the eligible agent at the head of the queue.

    Inactive or unavailable agents keep their position and are skipped.
    """
    eligible = [
        candidate
        for candidate in candidates
        if candidate.available
        and candidate.is_active
        and candidate.role == Role.DMC_AGENT
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda candidate: (candidate.queue_position, candidate.created_at))


__all__ = ["QueueCandidate", "next_in_queue"]
