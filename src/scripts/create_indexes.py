"""Idempotently create MongoDB indexes for every module.

Run via:

    poetry run python -m src.scripts.create_indexes
"""

from __future__ import annotations

import asyncio

from src.core.database import mongo
from src.core.logging import get_logger, setup_logging
from src.modules.auth.repository import AuthRepository, EmailVerificationRepository
from src.modules.companies.repository import CompaniesRepository
from src.modules.users.repository import UsersRepository

logger = get_logger(__name__)


async def _main() -> None:
    setup_logging()
    await mongo.connect()
    try:
        logger.info("creating_indexes")
        await AuthRepository(mongo.db).ensure_indexes()
        await EmailVerificationRepository(mongo.db).ensure_indexes()
        await CompaniesRepository(mongo.db).ensure_indexes()
        await UsersRepository(mongo.db).ensure_indexes()
        logger.info("indexes_done")
    finally:
        await mongo.close()


if __name__ == "__main__":
    asyncio.run(_main())
