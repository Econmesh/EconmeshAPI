"""Motor de regras do DMC: visibilidade condicional, validação, progresso e pontuação.

Funções puras sobre o catálogo + respostas + itens — sem I/O — para serem
reutilizadas pelo serviço, pelo relatório e pelos testes.

**Instâncias.** Perguntas com ``per_item`` geram uma *instância* por item
cadastrado do mesmo tipo (produto/resíduo); a resposta de cada instância fica
na chave ``"<pergunta>@<item>"`` (``response_key``). Perguntas gerais têm uma
única instância, com a chave igual ao id da pergunta.

**Consolidação da pontuação.** Uma pergunta pontuada respondida por vários
itens entra no pilar/EMS pela **média** dos pontos dos itens (score oficial).
O **pior caso** (menor pontuação entre os itens) é calculado em paralelo
(``Evaluation.worst_case``) como leitura conservadora.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel

from src.modules.maturity_diagnostics.catalog import (
    Catalog,
    ConditionOperator,
    ItemKind,
    Question,
    QuestionType,
    StepKind,
)

AnswerValue = str | list[str] | None

#: Separador entre pergunta e item na chave da resposta (``q10@a1b2c3``).
ITEM_KEY_SEPARATOR = "@"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ItemRef(Protocol):
    """Qualquer objeto com ``id`` e ``kind`` (ex.: ``DiagnosticItem``)."""

    @property
    def id(self) -> str: ...

    @property
    def kind(self) -> ItemKind | str: ...


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


class ScoreAggregation(StrEnum):
    #: Média dos itens — score oficial.
    AVERAGE = "average"
    #: Menor pontuação entre os itens — leitura conservadora.
    WORST = "worst"


class StepProgress(BaseModel):
    step_id: str
    status: StepStatus
    required_total: int = 0
    required_answered: int = 0
    optional_total: int = 0
    optional_answered: int = 0
    not_applicable: int = 0
    percent: int = 0
    #: Chaves das respostas obrigatórias pendentes (``q10@<item>`` para perguntas por item).
    missing_required: list[str] = []


class PillarScore(BaseModel):
    pillar_id: str
    points: float
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
    points: float = 0
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


class ItemScore(BaseModel):
    item_id: str
    points: int | None = None


class QuestionScore(BaseModel):
    """Pontuação consolidada de uma pergunta pontuada (geral ou por item)."""

    question_id: str
    step_id: str
    pillar_id: str | None = None
    #: Média dos itens (perguntas gerais: a própria pontuação).
    points: float | None = None
    #: Menor pontuação entre os itens respondidos.
    worst_points: int | None = None
    max_points: int = 0
    ems_weight: float = 0.0
    per_item: bool = False
    answered_items: int = 0
    total_items: int = 0
    items: list[ItemScore] = []


class ScoreSet(BaseModel):
    aggregation: ScoreAggregation
    pillars: list[PillarScore]
    axes: list[AxisScore]
    ems: EmsScore


class Alert(BaseModel):
    question_id: str
    level: str
    message: str
    #: Item (produto/resíduo) da resposta que disparou o alerta, quando houver.
    item_id: str | None = None


class Evaluation(BaseModel):
    steps: list[StepProgress]
    progress: int
    required_total: int
    required_answered: int
    pillars: list[PillarScore]
    ems: EmsScore
    complete: bool
    #: Chaves das instâncias visíveis (``q09``, ``q10@<item>``…).
    visible_question_ids: list[str]
    #: Alertas disparados pelas respostas (ex.: LO vencida = risco crítico).
    alerts: list[Alert] = []
    axes: list[AxisScore] = []
    #: Detalhe por pergunta pontuada, inclusive a pontuação de cada item.
    question_scores: list[QuestionScore] = []
    #: Mesmo cálculo considerando o pior item de cada pergunta.
    worst_case: ScoreSet | None = None


# ------------------------------------------------------------------- chaves
def response_key(question_id: str, item_id: str | None = None) -> str:
    return f"{question_id}{ITEM_KEY_SEPARATOR}{item_id}" if item_id else question_id


def split_key(key: str) -> tuple[str, str | None]:
    """``"q10@abc"`` → ``("q10", "abc")``; ``"q10"`` → ``("q10", None)``."""
    question_id, separator, item_id = key.partition(ITEM_KEY_SEPARATOR)
    if not separator:
        return key, None
    return question_id, item_id or None


@dataclass(frozen=True)
class QuestionInstance:
    question: Question
    item_id: str | None = None

    @property
    def key(self) -> str:
        return response_key(self.question.id, self.item_id)


def items_of(items: Sequence[ItemRef], kind: ItemKind | str | None) -> list[ItemRef]:
    return [item for item in items if item.kind == kind]


def question_instances(
    catalog: Catalog, items: Sequence[ItemRef] = ()
) -> list[QuestionInstance]:
    """Instâncias na ordem do catálogo (dependências antes dos dependentes)."""
    result: list[QuestionInstance] = []
    for question in catalog.questions:
        if question.per_item is None:
            result.append(QuestionInstance(question))
        else:
            result.extend(
                QuestionInstance(question, item.id) for item in items_of(items, question.per_item)
            )
    return result


# --------------------------------------------------------------- visibilidade
def _condition_key(
    catalog: Catalog | None, condition_question_id: str, item_id: str | None
) -> str:
    if item_id is None:
        return condition_question_id
    source = catalog.question(condition_question_id) if catalog is not None else None
    if source is not None and source.per_item is None:
        return condition_question_id
    return response_key(condition_question_id, item_id)


def is_visible(
    question: Question,
    values: Mapping[str, AnswerValue],
    item_id: str | None = None,
    catalog: Catalog | None = None,
) -> bool:
    for condition in question.show_if:
        current = values.get(_condition_key(catalog, condition.question_id, item_id))
        if condition.operator is ConditionOperator.IN:
            if not isinstance(current, str) or current not in condition.values:
                return False
        elif condition.operator is ConditionOperator.CONTAINS_ANY and (
            not isinstance(current, list) or not set(current) & set(condition.values)
        ):
            return False
    return True


def visible_instances(
    catalog: Catalog, values: Mapping[str, AnswerValue], items: Sequence[ItemRef] = ()
) -> list[QuestionInstance]:
    """Instâncias visíveis, resolvendo dependências encadeadas.

    Uma instância só aparece se a instância da qual depende (do mesmo item,
    quando a condição é por item) também estiver visível.
    """
    effective: dict[str, AnswerValue] = {}
    result: list[QuestionInstance] = []
    for instance in question_instances(catalog, items):
        if is_visible(instance.question, effective, instance.item_id, catalog):
            result.append(instance)
            effective[instance.key] = values.get(instance.key)
    return result


def visible_questions(
    catalog: Catalog, values: Mapping[str, AnswerValue], items: Sequence[ItemRef] = ()
) -> list[Question]:
    """Perguntas com ao menos uma instância visível (perguntas gerais incluídas)."""
    seen: set[str] = set()
    result: list[Question] = []
    for instance in visible_instances(catalog, values, items):
        if instance.question.id not in seen:
            seen.add(instance.question.id)
            result.append(instance.question)
    return result


def is_answered(value: AnswerValue) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return len(value) > 0
    return bool(value.strip())


def instance_answered(
    instance: QuestionInstance, values: Mapping[str, AnswerValue], items: Sequence[ItemRef]
) -> bool:
    question = instance.question
    if question.type is QuestionType.ITEM_LIST:
        return bool(items_of(items, question.item_kind))
    return is_answered(values.get(instance.key))


# ------------------------------------------------------------------ validação
def normalize_answer(question: Question, raw: Any) -> AnswerValue:
    """Valida e normaliza um valor bruto vindo do cliente. ``None`` limpa."""
    if question.type is QuestionType.ITEM_LIST:
        raise InvalidAnswerError(
            question.id, "Use o cadastro de itens para adicionar, editar ou excluir."
        )
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


def points_contribution(question: Question, points: float | None) -> float | None:
    """Pontos de EMS: pontos / máximo × peso no EMS."""
    if points is None or not question.max_points:
        return None
    return points / question.max_points * (question.ems_weight or 0.0)


def ems_contribution(question: Question, value: AnswerValue) -> float | None:
    """Pontos de EMS de uma resposta: pontos / máximo × peso no EMS."""
    return points_contribution(question, score_for(question, value))


def _question_scores(
    catalog: Catalog,
    visible: Sequence[QuestionInstance],
    values: Mapping[str, AnswerValue],
    available: Collection[str],
) -> list[QuestionScore]:
    grouped: dict[str, list[QuestionInstance]] = {}
    for instance in visible:
        question = instance.question
        if question.scored and question.step_id in available:
            grouped.setdefault(question.id, []).append(instance)
    result: list[QuestionScore] = []
    for question in catalog.questions:
        instances = grouped.get(question.id)
        if not instances:
            continue
        item_scores = [
            ItemScore(item_id=inst.item_id or "", points=score_for(question, values.get(inst.key)))
            for inst in instances
        ]
        answered = [s.points for s in item_scores if s.points is not None]
        result.append(
            QuestionScore(
                question_id=question.id,
                step_id=question.step_id,
                pillar_id=question.pillar_id,
                points=round(sum(answered) / len(answered), 2) if answered else None,
                worst_points=min(answered) if answered else None,
                max_points=question.max_points,
                ems_weight=question.ems_weight or 0.0,
                per_item=question.per_item is not None,
                answered_items=len(answered),
                total_items=len(instances),
                items=item_scores if question.per_item is not None else [],
            )
        )
    return result


def _score_set(
    catalog: Catalog,
    scores: Sequence[QuestionScore],
    available: Collection[str],
    aggregation: ScoreAggregation,
) -> ScoreSet:
    def pts(score: QuestionScore) -> float | None:
        if aggregation is ScoreAggregation.WORST:
            return float(score.worst_points) if score.worst_points is not None else None
        return score.points

    def contribution(score: QuestionScore) -> float:
        value = pts(score)
        if value is None or not score.max_points:
            return 0.0
        return value / score.max_points * score.ems_weight

    pillars: list[PillarScore] = []
    for pillar in catalog.pillars:
        scored = [s for s in scores if s.pillar_id == pillar.id]
        answered = [s for s in scored if pts(s) is not None]
        points = round(sum(pts(s) or 0.0 for s in answered), 2)
        max_points = sum(s.max_points for s in scored)
        pillars.append(
            PillarScore(
                pillar_id=pillar.id,
                points=points,
                max_points=max_points,
                percent=round(points * 100 / max_points, 1) if max_points else None,
                answered=len(answered),
                total=len(scored),
                ems_points=round(sum(contribution(s) for s in scored), 2),
                ems_max=round(sum(s.ems_weight for s in scored), 2),
            )
        )

    axes: list[AxisScore] = []
    for step in sorted(catalog.steps, key=lambda s: s.order):
        if step.kind is not StepKind.AXIS:
            continue
        if step.id not in available:
            axes.append(AxisScore(step_id=step.id, status=AxisStatus.MAINTENANCE))
            continue
        scored = [s for s in scores if s.step_id == step.id]
        ems_points = round(sum(contribution(s) for s in scored), 2)
        ems_max = round(sum(s.ems_weight for s in scored), 2)
        axes.append(
            AxisScore(
                step_id=step.id,
                status=AxisStatus.EVALUATED,
                scored_questions=len(scored),
                points=round(sum(pts(s) or 0.0 for s in scored), 2),
                max_points=sum(s.max_points for s in scored),
                ems_points=ems_points,
                ems_max=ems_max,
                percent=round(ems_points * 100 / ems_max, 1) if ems_max else None,
            )
        )

    ems = EmsScore(
        points=round(sum(contribution(s) for s in scores), 2),
        max_available=round(sum(s.ems_weight for s in scores), 2),
    )
    return ScoreSet(aggregation=aggregation, pillars=pillars, axes=axes, ems=ems)


def evaluate(
    catalog: Catalog,
    values: Mapping[str, AnswerValue],
    *,
    items: Sequence[ItemRef] = (),
    available_step_ids: Collection[str] | None = None,
) -> Evaluation:
    """Calcula progresso, pilares, eixos, EMS e alertas.

    ``items`` são os produtos/resíduos cadastrados. ``available_step_ids``
    permite reproduzir um diagnóstico concluído com as etapas que estavam
    disponíveis na conclusão (padrão: as do catálogo).
    """
    available = (
        set(available_step_ids)
        if available_step_ids is not None
        else {s.id for s in catalog.available_steps()}
    )
    all_instances = question_instances(catalog, items)
    visible = visible_instances(catalog, values, items)
    visible_keys = {inst.key for inst in visible}

    steps: list[StepProgress] = []
    required_total = 0
    required_answered = 0
    for step in sorted(catalog.steps, key=lambda s: s.order):
        if step.id not in available:
            steps.append(StepProgress(step_id=step.id, status=StepStatus.MAINTENANCE))
            continue
        progress = StepProgress(step_id=step.id, status=StepStatus.NOT_STARTED)
        any_answered = False
        for instance in all_instances:
            question = instance.question
            if question.step_id != step.id:
                continue
            if instance.key not in visible_keys:
                progress.not_applicable += 1
                continue
            answered = instance_answered(instance, values, items)
            if not question.read_only:
                # Dados cadastrais travados não indicam que a etapa foi iniciada.
                any_answered = any_answered or answered
            if question.required:
                progress.required_total += 1
                if answered:
                    progress.required_answered += 1
                else:
                    progress.missing_required.append(instance.key)
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

    question_scores = _question_scores(catalog, visible, values, available)
    main = _score_set(catalog, question_scores, available, ScoreAggregation.AVERAGE)
    worst = _score_set(catalog, question_scores, available, ScoreAggregation.WORST)

    alerts: list[Alert] = []
    for instance in visible:
        question = instance.question
        if question.step_id not in available:
            continue
        value = values.get(instance.key)
        selected = [value] if isinstance(value, str) else (value or [])
        for item in selected:
            option = question.option(item) if question.options else None
            if option is not None and option.alert_level is not None:
                alerts.append(
                    Alert(
                        question_id=question.id,
                        level=option.alert_level.value,
                        message=option.alert_message or option.label,
                        item_id=instance.item_id,
                    )
                )

    return Evaluation(
        alerts=alerts,
        axes=main.axes,
        steps=steps,
        progress=_percent(required_answered, required_total),
        required_total=required_total,
        required_answered=required_answered,
        pillars=main.pillars,
        ems=main.ems,
        complete=required_answered == required_total,
        visible_question_ids=[inst.key for inst in visible],
        question_scores=question_scores,
        worst_case=worst,
    )


__all__ = [
    "ITEM_KEY_SEPARATOR",
    "Alert",
    "AnswerValue",
    "AxisScore",
    "AxisStatus",
    "display_answer",
    "ems_contribution",
    "EmsScore",
    "Evaluation",
    "InvalidAnswerError",
    "ItemRef",
    "ItemScore",
    "PillarScore",
    "QuestionInstance",
    "QuestionScore",
    "ScoreAggregation",
    "ScoreSet",
    "StepProgress",
    "StepStatus",
    "evaluate",
    "instance_answered",
    "is_answered",
    "is_visible",
    "items_of",
    "normalize_answer",
    "points_contribution",
    "question_instances",
    "response_key",
    "score_for",
    "split_key",
    "visible_instances",
    "visible_questions",
]
