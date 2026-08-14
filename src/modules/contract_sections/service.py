"""Business rules for contract section templates."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.core.exceptions import NotFoundError, ValidationAppError
from src.modules.contract_proposals.core_sections import CORE_SECTION_DEFINITIONS
from src.modules.contract_proposals.section_sync import (
    remove_template_section,
    reorder_proposal_sections,
    upsert_template_section,
)
from src.modules.contract_sections.model import (
    ContractSectionTemplateDocument,
    ContractType,
    SectionAppliesTo,
)
from src.modules.contract_sections.repository import ContractSectionsRepository
from src.modules.contract_sections.schema import (
    ContractSectionCreate,
    ContractSectionListResponse,
    ContractSectionReorder,
    ContractSectionResponse,
    ContractSectionUpdate,
    MinutaStructureResponse,
    SystemSectionInfo,
)

if TYPE_CHECKING:
    from src.modules.contract_proposals.repository import ContractProposalsRepository


def _to_response(doc: ContractSectionTemplateDocument) -> ContractSectionResponse:
    return ContractSectionResponse(
        id=doc.id,
        title=doc.title,
        content_html=doc.content_html,
        contract_type=doc.contract_type,
        sort_order=doc.sort_order,
        created_by=doc.created_by,
        is_active=doc.is_active,
        is_company_editable=doc.is_company_editable,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


class ContractSectionsService:
    def __init__(
        self,
        repository: ContractSectionsRepository,
        proposals_repo: ContractProposalsRepository | None = None,
    ) -> None:
        self._repo = repository
        self._proposals = proposals_repo

    async def _sync_template_to_negotiating(
        self, template: ContractSectionTemplateDocument
    ) -> None:
        if self._proposals is None:
            return
        proposals = await self._proposals.list_negotiating(contract_types=None)
        # Cache templates per contract type for correct admin ordering
        templates_by_type: dict[ContractType, list[ContractSectionTemplateDocument]] = {}
        for proposal in proposals:
            if not template.is_active:
                if remove_template_section(proposal, template.id):
                    await self._proposals.replace(proposal)
                continue
            if proposal.contract_type not in templates_by_type:
                templates_by_type[proposal.contract_type] = (
                    await self._repo.list_active_by_type(proposal.contract_type)
                )
            if upsert_template_section(
                proposal,
                template,
                all_templates=templates_by_type[proposal.contract_type],
            ):
                await self._proposals.replace(proposal)

    async def _remove_template_from_negotiating(self, template_id: UUID) -> None:
        if self._proposals is None:
            return
        proposals = await self._proposals.list_negotiating(contract_types=None)
        for proposal in proposals:
            if remove_template_section(proposal, template_id):
                await self._proposals.replace(proposal)

    async def _resync_negotiating_orders(self) -> None:
        if self._proposals is None:
            return
        proposals = await self._proposals.list_negotiating(contract_types=None)
        templates_by_type: dict[ContractType, list[ContractSectionTemplateDocument]] = {}
        for proposal in proposals:
            if proposal.contract_type not in templates_by_type:
                templates_by_type[proposal.contract_type] = (
                    await self._repo.list_active_by_type(proposal.contract_type)
                )
            if reorder_proposal_sections(
                proposal, templates_by_type[proposal.contract_type]
            ):
                await self._proposals.replace(proposal)

    async def get_minuta_structure(
        self, *, contract_type: SectionAppliesTo | None = None
    ) -> MinutaStructureResponse:
        admin_sections = await self._repo.list_sections(
            skip=0,
            limit=500,
            contract_type=contract_type,
            active_only=False,
        )
        return MinutaStructureResponse(
            system_sections=[
                SystemSectionInfo(
                    key=item["key"],
                    title=item["title"],
                    description=item["description"],
                    sort_order=item["sort_order"],
                )
                for item in CORE_SECTION_DEFINITIONS
            ],
            admin_sections=[_to_response(doc) for doc in admin_sections],
        )

    async def reorder(
        self, payload: ContractSectionReorder
    ) -> ContractSectionListResponse:
        if not payload.ordered_ids:
            raise ValidationAppError("Informe ao menos uma seção para reordenar.")

        seen: set[UUID] = set()
        for index, section_id in enumerate(payload.ordered_ids):
            if section_id in seen:
                raise ValidationAppError("IDs duplicados na ordenação.")
            seen.add(section_id)
            existing = await self._repo.get_by_id(section_id)
            if existing is None:
                raise NotFoundError(f"Contract section not found: {section_id}")
            if existing.sort_order != index:
                await self._repo.update(section_id, {"sort_order": index})

        await self._resync_negotiating_orders()

        items = await self._repo.list_sections(skip=0, limit=500, active_only=False)
        return ContractSectionListResponse(
            items=[_to_response(doc) for doc in items],
            total=len(items),
            page=1,
            page_size=len(items) or 1,
        )

    async def create(
        self, payload: ContractSectionCreate, *, created_by: UUID
    ) -> ContractSectionResponse:
        doc = ContractSectionTemplateDocument(
            title=payload.title,
            content_html=payload.content_html,
            contract_type=payload.contract_type,
            sort_order=payload.sort_order,
            created_by=created_by,
            is_active=payload.is_active,
            is_company_editable=payload.is_company_editable,
        )
        created = await self._repo.create(doc)
        await self._sync_template_to_negotiating(created)
        return _to_response(created)

    async def get(self, section_id: UUID) -> ContractSectionResponse:
        doc = await self._repo.get_by_id(section_id)
        if doc is None:
            raise NotFoundError("Contract section not found.")
        return _to_response(doc)

    async def list(
        self,
        *,
        page: int,
        page_size: int,
        contract_type: SectionAppliesTo | None = None,
        active_only: bool = False,
    ) -> ContractSectionListResponse:
        skip = (page - 1) * page_size
        items = await self._repo.list_sections(
            skip=skip,
            limit=page_size,
            contract_type=contract_type,
            active_only=active_only,
        )
        total = await self._repo.count_sections(
            contract_type=contract_type,
            active_only=active_only,
        )
        return ContractSectionListResponse(
            items=[_to_response(doc) for doc in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def list_active_templates(
        self, *, contract_type: ContractType
    ) -> ContractSectionListResponse:
        items = await self._repo.list_active_by_type(contract_type)
        return ContractSectionListResponse(
            items=[_to_response(doc) for doc in items],
            total=len(items),
            page=1,
            page_size=len(items) or 1,
        )

    async def update(
        self, section_id: UUID, payload: ContractSectionUpdate
    ) -> ContractSectionResponse:
        existing = await self._repo.get_by_id(section_id)
        if existing is None:
            raise NotFoundError("Contract section not found.")
        patch = payload.model_dump(exclude_unset=True)
        updated = await self._repo.update(section_id, patch)
        if updated is None:
            raise NotFoundError("Contract section not found.")
        await self._sync_template_to_negotiating(updated)
        return _to_response(updated)

    async def delete(self, section_id: UUID) -> None:
        existing = await self._repo.get_by_id(section_id)
        if existing is None or not existing.is_active:
            raise NotFoundError("Contract section not found.")
        await self._repo.soft_delete(section_id)
        await self._remove_template_from_negotiating(section_id)


__all__ = ["ContractSectionsService"]
