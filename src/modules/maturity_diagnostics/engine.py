"""Motor de regras do DMC: visibilidade condicional, validação, progresso e pontuação.

Funções puras sobre o catálogo + respostas — sem I/O — para serem
reutilizadas pelo serviço, pelo relatório e pelos testes.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from src.modules.maturity_diagnostics.catalog import (
    Catalog,
    ConditionOperator,
    Question,
    QuestionType,
    StepKind,
)

AnswerValue = str | list[str] | None

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidAnswerError(ValueError):
    def __init__(self, question_id: str, message: str) -> None:
        super().__init__(message)
        self.question_id = question_id
        self.message = message


class StepStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MAINTENANCE = "maintenance"


class StepProgress(BaseModel):
    step_id: str
    status: StepStatus
    required_total: int = 0
    required_answered: int = 0
    optional_total: int = 0
    optional_answered: int = 0
    not_applicable: int = 0
    percent: int = 0
    missing_required: list[str] = []


class PillarScore(BaseModel):
    pillar_id: str
    points: int
    max_points: int
    percent: float | None
    answered: int
    total: int
    #: Contribuição do pilar no EMS (pontos ponderados) e máximo possível.
    ems_points: float = 0.0
    ems_max: float = 0.0


class AxisStatus(StrEnum):
    EVALUATED = "evaluated"
    MAINTENANCE = "maintenance"


class AxisScore(BaseModel):
    """Resultado por eixo do formulário (perguntas pontuadas localizadas no eixo)."""

    step_id: str
    status: AxisStatus
    points: int = 0
    max_points: int = 0
    ems_points: float = 0.0
    ems_max: float = 0.0
    #: Percentual ponderado pelos pesos no EMS (0–100); ``None`` se não avaliado.
    percent: float | None = None
    scored_questions: int = 0


class EmsScore(BaseModel):
    #: Pontos de EMS obtidos (soma ponderada das perguntas respondidas).
    points: float
    #: Máximo atingível com os eixos atualmente disponíveis.
    max_available: float


class Alert(BaseModel):
    question_id: str
    level: str
    message: str


class Evaluation(BaseModel):
    steps: list[StepProgress]
    progress: int
    required_total: int
    required_answered: int
    pillars: list[PillarScore]
    ems: EmsScore
    complete: bool
    visible_question_ids: list[str]
    #: Alertas disparados pelas respostas (ex.: LO vencida = risco crítico).
    alerts: list[Alert] = []
    axes: list[AxisScore] = []


# --------------------------------------------------------------- visibilidade
def is_visible(question: Question, values: Mapping[str, AnswerValue]) -> bool:
    for condition in question.show_if:
        current = values.get(condition.question_id)
        if condition.operator is ConditionOperator.IN:
            if not isinstance(current, str) or current not in condition.values:
                return False
        elif condition.operator is ConditionOperator.CONTAINS_ANY and (
            not isinstance(current, list) or not set(current) & set(condition.values)
        ):
            return False
    return True


def visible_questions(catalog: Catalog, values: Mapping[str, AnswerValue]) -> list[Question]:
    """Perguntas visíveis, resolvendo dependências encadeadas.

    Uma pergunta só aparece se a pergunta da qual depende também estiver
    visível (respostas ocultas não disparam outras condições).
    """
    effective: dict[str, AnswerValue] = {}
    result: list[Question] = []
    for question in catalog.questions:  # catálogo em ordem de dependência
        if is_visible(question, effective):
            result.append(question)
            effective[question.id] = values.get(question.id)
    return result


def is_answered(value: AnswerValue) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return len(value) > 0
    return bool(value.strip())


# ------------------------------------------------------------------ validação
def normalize_answer(question: Question, raw: Any) -> AnswerValue:
    """Valida e normaliza um valor bruto vindo do cliente. ``None`` limpa."""
    if raw is None:
        return None
    if question.type is QuestionType.MULTI_CHOICE:
        if not isinstance(raw, list):
            raise InvalidAnswerError(question.id, "Esperado uma lista de opções.")
        allowed = {opt.value for opt in question.options}
        seen: list[str] = []
        for item in raw:
            if not isinstance(item, str) or item not in allowed:
                raise InvalidAnswerError(question.id, f"Opção inválida: {item!r}.")
            if item not in seen:
                seen.append(item)
        return seen or None
    if not isinstance(raw, str):
        raise InvalidAnswerError(question.id, "Esperado um texto.")
    value = raw.strip()
    if not value:
        return None
    if question.type is QuestionType.SINGLE_CHOICE:
        if question.option(value) is None:
            raise InvalidAnswerError(question.id, f"Opção inválida: {value!r}.")
        return value
    if len(value) > question.max_length:
        raise InvalidAnswerError(
            question.id, f"Máximo de {question.max_length} caracteres."
        )
    if question.type is QuestionType.EMAIL and not _EMAIL_RE.match(value):
        raise InvalidAnswerError(question.id, "E-mail inválido.")
    if question.type is QuestionType.TAX_ID:
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) != 14:
            raise InvalidAnswerError(question.id, "CNPJ deve ter 14 dígitos.")
        return digits
    if question.type is QuestionType.PHONE:
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) < 8:
            raise InvalidAnswerError(question.id, "Telefone inválido.")
    return value


def display_answer(question: Question, value: AnswerValue) -> str | None:
    """Valor legível de uma resposta (rótulos das opções)."""
    if value is None or (isinstance(value, list) and not value):
        return None
    if isinstance(value, list):
        return ", ".join(
            (question.option(v).label if question.option(v) else v) for v in value  # type: ignore[union-attr]
        )
    if question.options:
        option = question.option(value)
        return option.label if option else value
    if question.type is QuestionType.TAX_ID and len(value) == 14:
        return f"{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:]}"
    return value


def score_for(question: Question, value: AnswerValue) -> int | None:
    if not question.scored or not isinstance(value, str):
        return None
    option = question.option(value)
    return option.points if option is not None else None


# ---------------------------------------------------------- progresso / score
def _percent(done: int, total: int) -> int:
    if total == 0:
        return 100
    return round(done * 100 / total)


def ems_contribution(question: Question, value: AnswerValue) -> float | None:
    """Pontos de EMS de uma resposta: pontos / máximo × peso no EMS."""
    score = score_for(question, value)
    if score is None or not question.max_points:
        return None
    return score / question.max_points * (question.ems_weight or 0.0)


def evaluate(
    catalog: Catalog,
    values: Mapping[str, AnswerValue],
    *,
    available_step_ids: Collection[str] | None = None,
) -> Evaluation:
    """Calcula progresso, pilares, eixos, EMS e alertas.

    ``available_step_ids`` permite reproduzir um diagnóstico concluído com as
    etapas que estavam disponíveis na conclusão (padrão: as do catálogo).
    """
    available = (
        set(available_step_ids)
        if available_step_ids is not None
        else {s.id for s in catalog.available_steps()}
    )
    visible = visible_questions(catalog, values)
    visible_ids = {q.id for q in visible}

    steps: list[StepProgress] = []
    required_total = 0
    required_answered = 0
    for step in sorted(catalog.steps, key=lambda s: s.order):
        if step.id not in available:
            steps.append(StepProgress(step_id=step.id, status=StepStatus.MAINTENANCE))
            continue
        questions = catalog.questions_for_step(step.id)
        progress = StepProgress(step_id=step.id, status=StepStatus.NOT_STARTED)
        any_answered = False
        for question in questions:
            if question.id not in visible_ids:
                progress.not_applicable += 1
                continue
            answered = is_answered(values.get(question.id))
            if not question.read_only:
                # Dados cadastrais travados não indicam que a etapa foi iniciada.
                any_answered = any_answered or answered
            if question.required:
                progress.required_total += 1
                if answered:
                    progress.required_answered += 1
                else:
                    progress.missing_required.append(question.id)
            else:
                progress.optional_total += 1
                if answered:
                    progress.optional_answered += 1
        progress.percent = _percent(progress.required_answered, progress.required_total)
        if progress.required_answered == progress.required_total:
            progress.status = StepStatus.COMPLETED
        elif any_answered:
            progress.status = StepStatus.IN_PROGRESS
        required_total += progress.required_total
        required_answered += progress.required_answered
        steps.append(progress)

    available_step_ids = available
    pillars: list[PillarScore] = []
    ems_points = 0.0
    ems_max = 0.0
    for pillar in catalog.pillars:
        scored = [
            q
            for q in visible
            if q.scored and q.pillar_id == pillar.id and q.step_id in available_step_ids
        ]
        points = 0
        answered = 0
        pillar_ems = 0.0
        for question in scored:
            score = score_for(question, values.get(question.id))
            if score is not None:
                points += score
                answered += 1
                pillar_ems += ems_contribution(question, values.get(question.id)) or 0.0
        max_points = sum(q.max_points for q in scored)
        pillars.append(
            PillarScore(
                pillar_id=pillar.id,
                points=points,
                max_points=max_points,
                percent=round(points * 100 / max_points, 1) if max_points else None,
                answered=answered,
                total=len(scored),
                ems_points=round(pillar_ems, 2),
                ems_max=round(sum(q.ems_weight or 0.0 for q in scored), 2),
            )
        )
    for question in visible:
        if not question.scored or question.step_id not in available_step_ids:
            continue
        weight = question.ems_weight or 0.0
        ems_max += weight
        score = score_for(question, values.get(question.id))
        if score is not None and question.max_points:
            ems_points += score / question.max_points * weight

    axes: list[AxisScore] = []
    for step in sorted(catalog.steps, key=lambda s: s.order):
        if step.kind is not StepKind.AXIS:
            continue
        if step.id not in available_step_ids:
            axes.append(AxisScore(step_id=step.id, status=AxisStatus.MAINTENANCE))
            continue
        scored = [q for q in visible if q.scored and q.step_id == step.id]
        axis = AxisScore(
            step_id=step.id,
            status=AxisStatus.EVALUATED,
            scored_questions=len(scored),
            max_points=sum(q.max_points for q in scored),
            ems_max=sum(q.ems_weight or 0.0 for q in scored),
        )
        for question in scored:
            value = values.get(question.id)
            axis.points += score_for(question, value) or 0
            axis.ems_points += ems_contribution(question, value) or 0.0
        axis.ems_points = round(axis.ems_points, 2)
        axis.ems_max = round(axis.ems_max, 2)
        axis.percent = round(axis.ems_points * 100 / axis.ems_max, 1) if axis.ems_max else None
        axes.append(axis)

    alerts: list[Alert] = []
    for question in visible:
        if question.step_id not in available_step_ids:
            continue
        value = values.get(question.id)
        selected = [value] if isinstance(value, str) else (value or [])
        for item in selected:
            option = question.option(item) if question.options else None
            if option is not None and option.alert_level is not None:
                alerts.append(
                    Alert(
                        question_id=question.id,
                        level=option.alert_level.value,
                        message=option.alert_message or option.label,
                    )
                )

    return Evaluation(
        alerts=alerts,
        axes=axes,
        steps=steps,
        progress=_percent(required_answered, required_total),
        required_total=required_total,
        required_answered=required_answered,
        pillars=pillars,
        ems=EmsScore(points=round(ems_points, 2), max_available=round(ems_max, 2)),
        complete=required_answered == required_total,
        visible_question_ids=[q.id for q in visible],
    )


__all__ = [
    "Alert",
    "AnswerValue",
    "AxisScore",
    "AxisStatus",
    "display_answer",
    "ems_contribution",
    "EmsScore",
    "Evaluation",
    "InvalidAnswerError",
    "PillarScore",
    "StepProgress",
    "StepStatus",
    "evaluate",
    "is_answered",
    "is_visible",
    "normalize_answer",
    "score_for",
    "visible_questions",
]
