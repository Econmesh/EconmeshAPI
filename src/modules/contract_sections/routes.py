"""Routes for active contract section templates (authenticated users)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query

from src.modules.contract_sections.controller import ContractSectionTemplatesController
from src.modules.contract_sections.deps import build_contract_section_templates_controller
from src.modules.contract_sections.model import ContractType
from src.modules.contract_sections.schema import ContractSectionListResponse
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(
    prefix="/contract-section-templates",
    tags=["contract-section-templates"],
)


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> ContractSectionTemplatesController:
    return build_contract_section_templates_controller(db)


ControllerDep = Annotated[
    ContractSectionTemplatesController, Depends(_build_controller)
]


@router.get(
    "",
    response_model=ContractSectionListResponse,
    summary="List active contract section templates.",
)
async def list_active_templates(
    controller: ControllerDep,
    _current_user: CurrentUserDep,
    contract_type: ContractType = Query(default=ContractType.SERVICO),
) -> ContractSectionListResponse:
    return await controller.list_active(contract_type=contract_type)
