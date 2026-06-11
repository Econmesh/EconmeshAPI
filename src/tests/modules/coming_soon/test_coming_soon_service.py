"""Unit tests for coming-soon email signups."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.modules.coming_soon.model import ComingSoonSubscriberDocument
from src.modules.coming_soon.schema import ComingSoonSubscribeRequest
from src.modules.coming_soon.service import ComingSoonService
from src.shared.utils.ids import new_uuid

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_subscribe_creates_new_record() -> None:
    repo = AsyncMock()
    repo.get_by_email = AsyncMock(return_value=None)
    repo.create = AsyncMock(side_effect=lambda doc: doc)
    service = ComingSoonService(repo)

    response = await service.subscribe(ComingSoonSubscribeRequest(email="alice@example.com"))

    assert response.message == "Thanks! We'll notify you when we launch."
    repo.create.assert_awaited_once()
    created: ComingSoonSubscriberDocument = repo.create.await_args.args[0]
    assert created.email == "alice@example.com"


@pytest.mark.asyncio
async def test_subscribe_is_idempotent_for_existing_email() -> None:
    existing = ComingSoonSubscriberDocument(id=new_uuid(), email="alice@example.com")
    repo = AsyncMock()
    repo.get_by_email = AsyncMock(return_value=existing)
    service = ComingSoonService(repo)

    response = await service.subscribe(ComingSoonSubscribeRequest(email="alice@example.com"))

    assert response.message == "Thanks! We'll notify you when we launch."
    repo.create.assert_not_awaited()
