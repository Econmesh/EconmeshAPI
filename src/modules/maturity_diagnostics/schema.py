"""DTOs HTTP do Diagnóstico de Maturidade Circular."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.modules.companies.model import CompanyRegistrationStatus
from src.modules.maturity_diagnostics.engine import Evaluation
from src.modules.maturity_diagnostics.model import (
    CompanySnapshot,
    DiagnosticStatus,
    ResponseSource,
)
from src.shared.schemas.base import APIModel


class DiagnosticCreate(APIModel):
    company_id: UUID


class AnswerInput(APIModel):
    question_id: str = Field(..., min_length=1, max_length=64)
    value: str | list[str] | None = None
    #: Momento em que o usuário editou (salvamento offline). Respostas mais
    #: antigas do que a gravada no servidor são ignoradas.
    edited_at: datetime | None = None


class SaveResponsesRequest(APIModel):
    answers: list[AnswerInput] = Field(default_factory=list, max_length=100)
    current_step: str | None = Field(default=None, max_length=64)


class ResponseOut(APIModel):
    value: str | list[str] | None = None
    score: int | None = None
    source: ResponseSource
    registry_value: str | None = None
    updated_at: datetime


class DiagnosticSummary(APIModel):
    id: UUID
    company_id: UUID
    company_name: str
    company_tax_id: str
    agent_user_id: UUID
    status: DiagnosticStatus
    progress: int
    current_step: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    #: Quando o relatório foi gerado (``None`` = ainda não gerado).
    report_generated_at: datetime | None = None


class DiagnosticDetail(DiagnosticSummary):
    catalog_version: str
    company: CompanySnapshot
    agent_name: str | None = None
    responses: dict[str, ResponseOut]
    evaluation: Evaluation
    can_edit: bool


class DiagnosticListResponse(APIModel):
    items: list[DiagnosticSummary]
    total: int


class DiagnosticCompanyItem(APIModel):
    company_id: UUID
    legal_name: str
    trade_name: str | None = None
    tax_id: str
    sector: str | None = None
    city: str | None = None
    state: str | None = None
    registration_status: CompanyRegistrationStatus
    open_diagnostic: DiagnosticSummary | None = None
    #: O diagnóstico aberto pertence a outro agente (somente leitura).
    open_by_other_agent: bool = False
    completed: list[DiagnosticSummary] = Field(default_factory=list)


class DiagnosticCompanyListResponse(APIModel):
    items: list[DiagnosticCompanyItem]
    total: int


__all__ = [
    "AnswerInput",
    "DiagnosticCompanyItem",
    "DiagnosticCompanyListResponse",
    "DiagnosticCreate",
    "DiagnosticDetail",
    "DiagnosticListResponse",
    "DiagnosticSummary",
    "ResponseOut",
    "SaveResponsesRequest",
]
