"""Dependency wiring for contract sections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.modules.contract_proposals.repository import ContractProposalsRepository
from src.modules.contract_sections.controller import (
    AdminContractSectionsController,
    ContractSectionTemplatesController,
)
from src.modules.contract_sections.repository import ContractSectionsRepository
from src.modules.contract_sections.service import ContractSectionsService

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase


def build_contract_sections_service(db: AsyncDatabase) -> ContractSectionsService:
    return ContractSectionsService(
        ContractSectionsRepository(db),
        proposals_repo=ContractProposalsRepository(db),
    )


def build_admin_contract_sections_controller(
    db: AsyncDatabase,
) -> AdminContractSectionsController:
    return AdminContractSectionsController(build_contract_sections_service(db))


def build_contract_section_templates_controller(
    db: AsyncDatabase,
) -> ContractSectionTemplatesController:
    return ContractSectionTemplatesController(build_contract_sections_service(db))


__all__ = [
    "build_admin_contract_sections_controller",
    "build_contract_section_templates_controller",
    "build_contract_sections_service",
]
