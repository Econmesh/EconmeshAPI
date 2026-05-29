"""Seed minimal development data. Safe to re-run.

Run via:

    poetry run python -m src.scripts.seed_dev
"""

from __future__ import annotations

import asyncio

from src.core.database import mongo
from src.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def _main() -> None:
    setup_logging()
    await mongo.connect()
    try:
        logger.info("seeding_dev_data")
        # TODO: insert sample companies, demo profiles, sample circularity flows.
        logger.info("seed_done")
    finally:
        await mongo.close()


if __name__ == "__main__":
    asyncio.run(_main())
