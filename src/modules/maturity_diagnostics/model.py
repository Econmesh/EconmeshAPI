"""Persistência do Diagnóstico de Maturidade Circular (DMC)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, Field

from src.shared.schemas.base import DomainDocument
from src.shared.utils.time import utcnow


class DiagnosticStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    # Reservados para fluxos futuros.
    REVIEW = "review"
    ARCHIVED = "archived"


#: Status que ainda aceitam edição — no máximo um diagnóstico aberto por empresa.
OPEN_STATUSES: frozenset[DiagnosticStatus] = frozenset(
    {DiagnosticStatus.NOT_STARTED, DiagnosticStatus.IN_PROGRESS, DiagnosticStatus.REVIEW}
)


class ResponseSource(StrEnum):
    #: Valor veio do cadastro da empresa e não foi alterado.
    REGISTRY = "registry"
    #: Valor informado/ajustado pelo agente durante o diagnóstico.
    AGENT = "agent"


class DiagnosticResponse(BaseModel):
    value: str | list[str] | None = None
    score: int | None = None
    source: ResponseSource = ResponseSource.AGENT
    #: Valor original do cadastro (quando a pergunta tem origem cadastral).
    registry_value: str | None = None
    updated_at: datetime = Field(default_factory=utcnow)
    updated_by: UUID | None = None


class CompanySnapshot(BaseModel):
    legal_name: str
    trade_name: str | None = None
    tax_id: str
    sector: str | None = None
    city: str | None = None
    state: str | None = None


class MaturityDiagnosticDocument(DomainDocument):
    collection_name: ClassVar[str] = "maturity_diagnostics"

    company_id: UUID
    agent_user_id: UUID
    status: DiagnosticStatus = DiagnosticStatus.NOT_STARTED
    is_open: bool = True
    catalog_version: str
    progress: int = 0
    current_step: str | None = None
    responses: dict[str, DiagnosticResponse] = Field(default_factory=dict)
    #: Cache do último cálculo (progresso por etapa, pilares, EMS).
    evaluation: dict[str, Any] | None = None
    company_snapshot: CompanySnapshot
    started_at: datetime | None = None
    completed_at: datetime | None = None
    completed_by: UUID | None = None
    #: Resultado congelado no momento da conclusão (base do relatório).
    result: dict[str, Any] | None = None
    #: Relatório gerado (``MaturityReport`` serializado) e marcos de geração.
    report: dict[str, Any] | None = None
    report_generated_at: datetime | None = None
    pdf_generated_at: datetime | None = None

    def answer_values(self) -> dict[str, str | list[str] | None]:
        return {qid: resp.value for qid, resp in self.responses.items()}


__all__ = [
    "OPEN_STATUSES",
    "CompanySnapshot",
    "DiagnosticResponse",
    "DiagnosticStatus",
    "MaturityDiagnosticDocument",
    "ResponseSource",
]
