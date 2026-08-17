"""Business rules for contract section templates."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.core.exceptions import NotFoundError, ValidationAppError
from src.modules.contract_proposals.core_sections import (
    CORE_SECTION_DEFINITIONS,
    FORO_SECTION_DEFINITION,
    is_foro_title,
)
from src.modules.contract_proposals.opportunity_contract import minuta_title_for
from src.modules.contract_proposals.pdf_service import build_core_sections_html, build_foro_html
from src.modules.contract_proposals.section_sync import (
    proposal_opportunity_type,
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
    ContractPreviewResponse,
    ContractPreviewSection,
    ContractSectionCreate,
    ContractSectionListResponse,
    ContractSectionReorder,
    ContractSectionResponse,
    ContractSectionUpdate,
    MinutaStructureResponse,
    SystemSectionInfo,
)
from src.modules.opportunities.model import OpportunityType

if TYPE_CHECKING:
    from src.modules.contract_proposals.repository import ContractProposalsRepository
    from src.modules.platform_settings.repository import PlatformSettingsRepository


def _to_response(doc: ContractSectionTemplateDocument) -> ContractSectionResponse:
    return ContractSectionResponse(
        id=doc.id,
        title=doc.title,
        content_html=doc.content_html,
        contract_type=doc.contract_type,
        opportunity_types=list(doc.opportunity_types or []),
        sort_order=doc.sort_order,
        created_by=doc.created_by,
        is_active=doc.is_active,
        is_company_editable=doc.is_company_editable,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _system_sections() -> list[SystemSectionInfo]:
    opening = [
        SystemSectionInfo(
            key=item["key"],
            title=item["title"],
            description=item["description"],
            sort_order=item["sort_order"],
            placement="start",
        )
        for item in CORE_SECTION_DEFINITIONS
    ]
    foro = SystemSectionInfo(
        key=FORO_SECTION_DEFINITION["key"],
        title=FORO_SECTION_DEFINITION["title"],
        description=FORO_SECTION_DEFINITION["description"],
        sort_order=FORO_SECTION_DEFINITION["sort_order"],
        placement="end",
    )
    return opening + [foro]


def _reject_foro_title(title: str | None) -> None:
    if title and is_foro_title(title):
        raise ValidationAppError(
            "Do Foro é uma seção fixa do sistema e não pode ser criada como "
            "template administrativo."
        )


class ContractSectionsService:
    def __init__(
        self,
        repository: ContractSectionsRepository,
        proposals_repo: ContractProposalsRepository | None = None,
        platform_settings_repo: PlatformSettingsRepository | None = None,
    ) -> None:
        self._repo = repository
        self._proposals = proposals_repo
        self._platform_settings = platform_settings_repo

    async def _sync_template_to_negotiating(
        self, template: ContractSectionTemplateDocument
    ) -> None:
        if self._proposals is None:
            return
        proposals = await self._proposals.list_negotiating(contract_types=None)
        templates_by_key: dict[str, list[ContractSectionTemplateDocument]] = {}
        for proposal in proposals:
            if not template.is_active:
                if remove_template_section(proposal, template.id):
                    await self._proposals.replace(proposal)
                continue
            cache_key = self._templates_cache_key(proposal)
            if cache_key not in templates_by_key:
                templates_by_key[cache_key] = await self._templates_for_proposal(proposal)
            if upsert_template_section(
                proposal,
                template,
                all_templates=templates_by_key[cache_key],
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
        templates_by_key: dict[str, list[ContractSectionTemplateDocument]] = {}
        for proposal in proposals:
            cache_key = self._templates_cache_key(proposal)
            if cache_key not in templates_by_key:
                templates_by_key[cache_key] = await self._templates_for_proposal(proposal)
            if reorder_proposal_sections(proposal, templates_by_key[cache_key]):
                await self._proposals.replace(proposal)

    def _templates_cache_key(self, proposal) -> str:
        opp_type = proposal_opportunity_type(proposal)
        if opp_type is not None:
            return f"opp:{opp_type}"
        return f"ct:{proposal.contract_type}"

    async def _templates_for_proposal(self, proposal):
        opp_type = proposal_opportunity_type(proposal)
        if opp_type is not None:
            return await self._repo.list_active_by_opportunity_type(opp_type)
        return await self._repo.list_active_by_type(proposal.contract_type)

    async def get_minuta_structure(
        self,
        *,
        contract_type: SectionAppliesTo | None = None,
        opportunity_type: OpportunityType | None = None,
    ) -> MinutaStructureResponse:
        await self._repo.deactivate_foro_templates()
        admin_sections = await self._repo.list_sections(
            skip=0,
            limit=500,
            contract_type=contract_type,
            opportunity_type=opportunity_type,
            active_only=False,
        )
        return MinutaStructureResponse(
            system_sections=_system_sections(),
            admin_sections=[
                _to_response(doc)
                for doc in admin_sections
                if not is_foro_title(doc.title)
            ],
        )

    async def _preview_foro_html(self) -> str:
        city = "São Paulo"
        state = "SP"
        if self._platform_settings is not None:
            settings = await self._platform_settings.get_or_create()
            if settings.foro_city:
                city = settings.foro_city
            if settings.foro_state:
                state = settings.foro_state
        return build_foro_html(
            city=city,
            state=state,
            contractor_legal_name="Empresa Contratante Exemplo Ltda.",
            contracted_legal_name="Empresa Contratada Exemplo Ltda.",
        )

    async def get_contract_preview(
        self, *, opportunity_type: OpportunityType
    ) -> ContractPreviewResponse:
        core = build_core_sections_html(
            contractor_block=(
                "Empresa Contratante Exemplo Ltda., inscrita no CNPJ sob o nº "
                "00.000.000/0001-00, com sede em São Paulo/SP."
            ),
            contracted_block=(
                "Empresa Contratada Exemplo Ltda., inscrita no CNPJ sob o nº "
                "00.000.000/0002-00, com sede em Campinas/SP."
            ),
            opportunity_title="Oportunidade de exemplo",
            opportunity_description=(
                "Descrição de exemplo da oportunidade negociada entre as PARTES."
            ),
            valor="R$ 1.000,00",
            prazo="Contínua",
            opportunity_type=opportunity_type.value,
        )
        templates = await self._repo.list_active_by_opportunity_type(opportunity_type)
        sections: list[ContractPreviewSection] = [
            ContractPreviewSection(title=title, content_html=html, is_system=True)
            for title, html in core
        ]
        sections.extend(
            ContractPreviewSection(
                title=tmpl.title,
                content_html=tmpl.content_html,
                is_system=False,
            )
            for tmpl in templates
            if not is_foro_title(tmpl.title)
        )
        sections.append(
            ContractPreviewSection(
                title=FORO_SECTION_DEFINITION["title"],
                content_html=await self._preview_foro_html(),
                is_system=True,
            )
        )
        title = minuta_title_for(opportunity_type)
        sections_html = "".join(
            f"<h2>{section.title}</h2>"
            f'<div class="section-body">{section.content_html}</div>'
            for section in sections
        )
        html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11pt;
color: #111; line-height: 1.45; }}
h1 {{ font-size: 16pt; text-align: center; margin-bottom: 24pt; }}
h2 {{ font-size: 12pt; margin-top: 18pt; margin-bottom: 8pt;
border-bottom: 1px solid #ccc; padding-bottom: 4pt; }}
.section-body p {{ margin: 0 0 8pt 0; }}
.closing-date {{ text-align: center; margin-top: 18pt; }}
.signatures {{ text-align: center; margin-top: 28pt; }}
.signature {{ text-align: center; margin: 0; }}
.signature-spacer {{ margin: 0; line-height: 1.6; }}
.signature-next {{ margin-top: 36pt; }}
</style>
</head>
<body>
<h1>{title}</h1>
{sections_html}
</body>
</html>"""
        return ContractPreviewResponse(
            opportunity_type=opportunity_type,
            title=title,
            html=html,
            sections=sections,
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
        _reject_foro_title(payload.title)
        doc = ContractSectionTemplateDocument(
            title=payload.title,
            content_html=payload.content_html,
            contract_type=payload.contract_type,
            opportunity_types=list(payload.opportunity_types),
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
        opportunity_type: OpportunityType | None = None,
        active_only: bool = False,
    ) -> ContractSectionListResponse:
        skip = (page - 1) * page_size
        items = await self._repo.list_sections(
            skip=skip,
            limit=page_size,
            contract_type=contract_type,
            opportunity_type=opportunity_type,
            active_only=active_only,
        )
        total = await self._repo.count_sections(
            contract_type=contract_type,
            opportunity_type=opportunity_type,
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
        items = [doc for doc in items if not is_foro_title(doc.title)]
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
        if "title" in patch:
            _reject_foro_title(patch["title"])
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
