"""Background worker for scheduled blog publishing."""

from __future__ import annotations

import asyncio

from src.core.database import mongo
from src.core.logging import get_logger, setup_logging
from src.modules.blog.deps import build_blog_service

logger = get_logger(__name__)

_POLL_INTERVAL_SECONDS = 60


async def _process_due_posts() -> None:
    service = build_blog_service(mongo.db)
    try:
        count = await service.publish_due_scheduled()
        if count:
            logger.info("published_scheduled_blog_posts", count=count)
    except Exception:  # noqa: BLE001
        logger.exception("scheduled_blog_publish_failed")


async def main() -> None:
    setup_logging()
    await mongo.connect()
    logger.info("blog_worker_started", interval=_POLL_INTERVAL_SECONDS)
    try:
        while True:
            await _process_due_posts()
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    finally:
        await mongo.close()
        logger.info("blog_worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
