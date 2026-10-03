"""Rotas do Diagnóstico de Maturidade Circular — exclusivas do Agente DMC."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from src.modules.auth.repository import AuthRepository
from src.modules.companies.repository import CompaniesRepository
from src.modules.dmc.audit import AuditLog
from src.modules.dmc.repository import AuditEventsRepository, DmcPortfolioRepository
from src.modules.dmc.scope import ScopeService
from src.modules.maturity_diagnostics.catalog import Catalog
from src.modules.maturity_diagnostics.model import DiagnosticStatus
from src.modules.maturity_diagnostics.repository import MaturityDiagnosticsRepository
from src.modules.maturity_diagnostics.schema import (
    DiagnosticCompanyListResponse,
    DiagnosticCreate,
    DiagnosticDetail,
    DiagnosticListResponse,
    DiagnosticReport,
    SaveResponsesRequest,
)
from src.modules.maturity_diagnostics.service import MaturityDiagnosticsService
from src.modules.users.repository import UsersRepository
from src.shared.constants.permissions import Permission
from src.shared.constants.roles import Role
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.rbac import require_permission, require_role

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(
    prefix="/dmc/diagnostics",
    tags=["dmc-diagnostics"],
    dependencies=[
        Depends(require_role(Role.DMC_AGENT)),
        Depends(require_permission(Permission.DIAGNOSTICS_MANAGE)),
    ],
)


def build_service(db: Annotated["AsyncDatabase", Depends(get_db)]) -> MaturityDiagnosticsService:
    return MaturityDiagnosticsService(
        repository=MaturityDiagnosticsRepository(db),
        auth=AuthRepository(db),
        users=UsersRepository(db),
        scope=ScopeService(
            DmcPortfolioRepository(db), CompaniesRepository(db), UsersRepository(db)
        ),
        audit=AuditLog(AuditEventsRepository(db)),
    )


ServiceDep = Annotated[MaturityDiagnosticsService, Depends(build_service)]


@router.get(
    "/catalog",
    response_model=Catalog,
    summary="Estrutura do formulário: etapas, seções, perguntas, regras e pontuação.",
)
async def get_catalog(service: ServiceDep) -> Catalog:
    return service.catalog()


@router.get(
    "/companies",
    response_model=DiagnosticCompanyListResponse,
    summary="Empresas da carteira com o diagnóstico em andamento e o histórico.",
)
async def list_companies(
    service: ServiceDep, current_user: CurrentUserDep
) -> DiagnosticCompanyListResponse:
    return await service.list_companies(current_user.uid)


@router.get("", response_model=DiagnosticListResponse, summary="Diagnósticos do agente.")
async def list_diagnostics(
    service: ServiceDep,
    current_user: CurrentUserDep,
    company_id: UUID | None = Query(default=None),
    status_filter: DiagnosticStatus | None = Query(default=None, alias="status"),
) -> DiagnosticListResponse:
    return await service.list_diagnostics(
        current_user.uid, company_id=company_id, status=status_filter
    )


@router.post(
    "",
    response_model=DiagnosticDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Inicia um diagnóstico — ou retorna o que já está em andamento (200).",
)
async def create_diagnostic(
    payload: DiagnosticCreate,
    response: Response,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> DiagnosticDetail:
    detail, created = await service.create(current_user.uid, payload.company_id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return detail


@router.get("/{diagnostic_id}", response_model=DiagnosticDetail)
async def get_diagnostic(
    diagnostic_id: UUID, service: ServiceDep, current_user: CurrentUserDep
) -> DiagnosticDetail:
    return await service.get(current_user.uid, diagnostic_id)


@router.patch(
    "/{diagnostic_id}/responses",
    response_model=DiagnosticDetail,
    summary="Salvamento (automático ou manual) de respostas e da etapa atual.",
)
async def save_responses(
    diagnostic_id: UUID,
    payload: SaveResponsesRequest,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> DiagnosticDetail:
    return await service.save_responses(current_user.uid, diagnostic_id, payload)


@router.post(
    "/{diagnostic_id}/steps/{step_id}/complete",
    response_model=DiagnosticDetail,
    summary="Valida as obrigatórias da etapa e avança para a próxima.",
)
async def complete_step(
    diagnostic_id: UUID,
    step_id: str,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> DiagnosticDetail:
    return await service.validate_step(current_user.uid, diagnostic_id, step_id)


@router.post(
    "/{diagnostic_id}/complete",
    response_model=DiagnosticDetail,
    summary="Conclui o diagnóstico (todas as etapas disponíveis preenchidas).",
)
async def complete_diagnostic(
    diagnostic_id: UUID, service: ServiceDep, current_user: CurrentUserDep
) -> DiagnosticDetail:
    return await service.complete(current_user.uid, diagnostic_id)


@router.get(
    "/{diagnostic_id}/report",
    response_model=DiagnosticReport,
    summary="Dados estruturados do relatório final (diagnóstico concluído).",
)
async def get_report(
    diagnostic_id: UUID, service: ServiceDep, current_user: CurrentUserDep
) -> DiagnosticReport:
    return await service.report(current_user.uid, diagnostic_id)


__all__ = ["build_service", "router"]
