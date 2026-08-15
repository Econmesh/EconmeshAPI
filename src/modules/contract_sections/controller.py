"""HTTP controller for contract section templates."""

from __future__ import annotations

from uuid import UUID

from src.modules.contract_sections.model import ContractType, SectionAppliesTo
from src.modules.contract_sections.schema import (
    ContractPreviewResponse,
    ContractSectionCreate,
    ContractSectionListResponse,
    ContractSectionReorder,
    ContractSectionResponse,
    ContractSectionUpdate,
    MinutaStructureResponse,
)
from src.modules.contract_sections.service import ContractSectionsService
from src.modules.opportunities.model import OpportunityType


class AdminContractSectionsController:
    def __init__(self, service: ContractSectionsService) -> None:
        self._service = service

    async def create(
        self,
        payload: ContractSectionCreate,
        *,
        created_by: UUID,
    ) -> ContractSectionResponse:
        return await self._service.create(payload, created_by=created_by)

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        contract_type: SectionAppliesTo | None = None,
        opportunity_type: OpportunityType | None = None,
        active_only: bool = False,
    ) -> ContractSectionListResponse:
        return await self._service.list(
            page=page,
            page_size=page_size,
            contract_type=contract_type,
            opportunity_type=opportunity_type,
            active_only=active_only,
        )

    async def get_structure(
        self,
        *,
        contract_type: SectionAppliesTo | None = None,
        opportunity_type: OpportunityType | None = None,
    ) -> MinutaStructureResponse:
        return await self._service.get_minuta_structure(
            contract_type=contract_type,
            opportunity_type=opportunity_type,
        )

    async def get_preview(
        self, *, opportunity_type: OpportunityType
    ) -> ContractPreviewResponse:
        return await self._service.get_contract_preview(
            opportunity_type=opportunity_type
        )

    async def reorder(
        self, payload: ContractSectionReorder
    ) -> ContractSectionListResponse:
        return await self._service.reorder(payload)

    async def get(self, section_id: UUID) -> ContractSectionResponse:
        return await self._service.get(section_id)

    async def update(
        self, section_id: UUID, payload: ContractSectionUpdate
    ) -> ContractSectionResponse:
        return await self._service.update(section_id, payload)

    async def delete(self, section_id: UUID) -> None:
        await self._service.delete(section_id)


class ContractSectionTemplatesController:
    """Authenticated (non-admin) listing of active templates."""

    def __init__(self, service: ContractSectionsService) -> None:
        self._service = service

    async def list_active(
        self, *, contract_type: ContractType
    ) -> ContractSectionListResponse:
        return await self._service.list_active_templates(contract_type=contract_type)


__all__ = [
    "AdminContractSectionsController",
    "ContractSectionTemplatesController",
]
