"""DTOs HTTP do Diagnóstico de Maturidade Circular."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.modules.companies.model import CompanyRegistrationStatus
from src.modules.maturity_diagnostics.engine import EmsScore, Evaluation, PillarScore
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


class ReportAnswer(APIModel):
    question_id: str
    code: str | None = None
    number: int | None = None
    label: str
    value: str | list[str] | None = None
    display_value: str | None = None
    source: ResponseSource | None = None
    scored: bool = False
    points: int | None = None
    max_points: int | None = None
    pillar_id: str | None = None


class ReportSection(APIModel):
    id: str
    title: str
    answers: list[ReportAnswer]


class ReportStep(APIModel):
    id: str
    title: str
    availability: str
    sections: list[ReportSection]


class ReportPillar(PillarScore):
    code: str
    name: str
    ems_weight: float | None = None


class DiagnosticReport(APIModel):
    """Base estruturada do relatório final (visualização, PDF e compartilhamento)."""

    diagnostic: DiagnosticSummary
    company: CompanySnapshot
    agent_name: str | None = None
    catalog_version: str
    generated_at: datetime
    steps: list[ReportStep]
    pillars: list[ReportPillar]
    ems: EmsScore
    #: Ainda sem régua definida — preenchido quando as faixas forem especificadas.
    maturity_level: str | None = None
    observations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    executive_summary: str | None = None


__all__ = [
    "AnswerInput",
    "DiagnosticCompanyItem",
    "DiagnosticCompanyListResponse",
    "DiagnosticCreate",
    "DiagnosticDetail",
    "DiagnosticListResponse",
    "DiagnosticReport",
    "DiagnosticSummary",
    "ReportAnswer",
    "ReportPillar",
    "ReportSection",
    "ReportStep",
    "ResponseOut",
    "SaveResponsesRequest",
]
