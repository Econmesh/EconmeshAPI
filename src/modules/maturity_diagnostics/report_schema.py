"""Modelo de dados do Relatório de Diagnóstico de Maturidade Circular.

O mesmo documento alimenta o relatório web e o PDF. Ele é gerado uma vez a
partir do diagnóstico concluído e persistido (``report`` no diagnóstico), para
continuar reproduzível mesmo se a metodologia mudar depois.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from src.modules.maturity_diagnostics.engine import Alert
from src.modules.maturity_diagnostics.model import CompanySnapshot, ResponseSource
from src.shared.schemas.base import APIModel


class ReportVersions(APIModel):
    #: Versão do questionário (catálogo) usado no diagnóstico.
    diagnostic_version: str
    methodology_version: str
    report_version: str
    maturity_scale_version: str | None = None


class ReportPerson(APIModel):
    name: str | None = None
    job_title: str | None = None
    email: str | None = None
    phone: str | None = None


class ReportDiagnosticInfo(APIModel):
    id: UUID
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class ReportField(APIModel):
    question_id: str
    code: str | None = None
    label: str
    value: str | None = None
    #: ``registry`` = dado cadastral · ``adjusted`` = cadastral ajustado no
    #: diagnóstico · ``diagnostic`` = coletado durante o diagnóstico.
    origin: str


class MaturityLevelOut(APIModel):
    level: int
    name: str
    description: str
    interpretation: str | None = None


class ReportSummary(APIModel):
    overall_score: float
    overall_max: float
    overall_percent: float | None
    #: ``True`` quando algum eixo não foi avaliado (score não cobre o modelo todo).
    partial: bool
    maturity_level: MaturityLevelOut | None = None
    maturity_scale_defined: bool
    headline: str
    #: Score considerando o pior item de cada pergunta (produtos/resíduos).
    worst_case_score: float | None = None
    worst_case_percent: float | None = None


class ReportAxis(APIModel):
    step_id: str
    order: int
    title: str
    short_title: str
    description: str | None = None
    #: ``evaluated`` | ``maintenance``
    status: str
    percent: float | None = None
    points: float = 0
    max_points: int = 0
    ems_points: float = 0.0
    ems_max: float = 0.0
    scored_questions: int = 0
    reading: str | None = None


class ReportPillar(APIModel):
    pillar_id: str
    code: str
    name: str
    ems_weight: float | None = None
    points: float
    max_points: int
    percent: float | None = None
    ems_points: float
    ems_max: float
    answered: int
    total: int
    reading: str | None = None
    #: Mesmo pilar considerando o pior item de cada pergunta.
    worst_points: float | None = None
    worst_ems_points: float | None = None


class ReportIndicatorItem(APIModel):
    """Resposta de um item (produto/resíduo) a um indicador por item."""

    item_id: str
    item_name: str
    answer: str | None = None
    points: int | None = None
    tier: str = "unanswered"


class ReportIndicator(APIModel):
    question_id: str
    code: str | None = None
    title: str
    label: str
    step_id: str
    pillar_id: str | None = None
    answer: str | None = None
    #: Pergunta por item: média dos itens (base do score).
    points: float | None = None
    max_points: int
    percent: float | None = None
    pillar_weight: float | None = None
    ems_weight: float | None = None
    ems_points: float | None = None
    #: ``high`` | ``medium`` | ``low`` | ``unanswered``
    tier: str
    interpretation: str | None = None
    per_item: bool = False
    #: Menor pontuação entre os itens.
    worst_points: int | None = None
    items: list[ReportIndicatorItem] = Field(default_factory=list)


class ReportFinding(APIModel):
    title: str
    text: str
    #: Para pontos de atenção: ``critical`` | ``high`` | ``moderate``.
    severity: str | None = None
    source_question_ids: list[str] = Field(default_factory=list)


class ReportOpportunity(APIModel):
    number: int
    title: str
    text: str
    source_question_ids: list[str] = Field(default_factory=list)


class ReportAnalysis(APIModel):
    observed_data: list[str] = Field(default_factory=list)
    calculated_indicators: list[str] = Field(default_factory=list)
    interpretation: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)


class ReportScope(APIModel):
    complete: bool
    evaluated_axes: list[str]
    pending_axes: list[str]
    text: str


class ReportMethodologyItem(APIModel):
    title: str
    description: str | None = None


class ReportMethodology(APIModel):
    objective: str
    axes: list[ReportMethodologyItem]
    pillars: list[ReportMethodologyItem]
    scoring: list[str]
    results: list[str]
    maturity_scale: list[ReportMethodologyItem] = Field(default_factory=list)
    maturity_scale_note: str | None = None


class ReportAnswerItem(APIModel):
    question_id: str
    code: str | None = None
    label: str
    answer: str | None = None
    source: ResponseSource | None = None
    scored: bool = False
    points: float | None = None
    max_points: int | None = None
    pillar_code: str | None = None


class ReportAnswerSection(APIModel):
    title: str
    answers: list[ReportAnswerItem]
    #: Seção respondida para um produto/resíduo específico.
    item_id: str | None = None
    item_name: str | None = None
    item_kind: str | None = None


class ReportItem(APIModel):
    """Produto ou resíduo cadastrado, com todas as respostas vinculadas a ele."""

    id: str
    kind: str
    kind_label: str
    name: str
    description: str | None = None
    #: Seções (por eixo) com as respostas do item, na ordem do formulário.
    sections: list[ReportAnswerSection] = Field(default_factory=list)
    #: Pontos obtidos / máximos nos indicadores pontuados do item.
    points: int = 0
    max_points: int = 0


class ReportAnswerStep(APIModel):
    step_id: str
    title: str
    status: str
    sections: list[ReportAnswerSection]


class MaturityReport(APIModel):
    """``DiagnosticReport``: documento completo do relatório."""

    diagnostic_id: UUID
    versions: ReportVersions
    generated_at: datetime
    diagnostic: ReportDiagnosticInfo
    company: CompanySnapshot
    contact: ReportPerson
    agent: ReportPerson
    identification: list[ReportField]
    summary: ReportSummary
    axes: list[ReportAxis]
    pillars: list[ReportPillar]
    indicators: list[ReportIndicator]
    alerts: list[Alert] = Field(default_factory=list)
    strengths: list[ReportFinding]
    attention_points: list[ReportFinding]
    opportunities: list[ReportOpportunity]
    analysis: ReportAnalysis
    conclusions: list[str]
    scope: ReportScope
    methodology: ReportMethodology
    answers: list[ReportAnswerStep]
    #: Produtos (1.1) e resíduos (1.7) com as avaliações individuais.
    products: list[ReportItem] = Field(default_factory=list)
    wastes: list[ReportItem] = Field(default_factory=list)


__all__ = [
    "MaturityLevelOut",
    "MaturityReport",
    "ReportAnalysis",
    "ReportAnswerItem",
    "ReportAnswerSection",
    "ReportAnswerStep",
    "ReportAxis",
    "ReportDiagnosticInfo",
    "ReportField",
    "ReportFinding",
    "ReportIndicator",
    "ReportIndicatorItem",
    "ReportItem",
    "ReportMethodology",
    "ReportMethodologyItem",
    "ReportOpportunity",
    "ReportPerson",
    "ReportPillar",
    "ReportScope",
    "ReportSummary",
    "ReportVersions",
]
