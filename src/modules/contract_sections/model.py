"""Persistence models for contract section templates."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from src.modules.opportunities.model import OpportunityType
from src.shared.schemas.base import DomainDocument


class ContractType(StrEnum):
    """Contract type used when creating a minuta/proposal."""

    SERVICO = "servico"
    FORNECIMENTO = "fornecimento"
    PARCERIA = "parceria"
    OUTRO = "outro"


class SectionAppliesTo(StrEnum):
    """Where an admin section template applies."""

    SERVICO = "servico"
    FORNECIMENTO = "fornecimento"
    PARCERIA = "parceria"
    OUTRO = "outro"
    OPORTUNIDADES = "oportunidades"
    TODOS = "todos"


class ContractSectionTemplateDocument(DomainDocument):
    """Admin-managed default clause for contract proposals."""

    collection_name: ClassVar[str] = "contract_section_templates"

    title: str
    content_html: str
    # Kept as contract_type for API/DB compatibility; values include applies-to scopes.
    contract_type: SectionAppliesTo = SectionAppliesTo.TODOS
    opportunity_types: list[OpportunityType] = Field(
        default_factory=lambda: list(OpportunityType)
    )
    sort_order: int = 0
    created_by: UUID
    is_active: bool = True
    is_company_editable: bool = False


__all__ = [
    "ContractSectionTemplateDocument",
    "ContractType",
    "SectionAppliesTo",
]
