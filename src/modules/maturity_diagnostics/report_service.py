"""``DiagnosticReportService``: monta o relatório a partir do diagnóstico persistido.

Fluxo: respostas persistidas → ``engine.evaluate`` (cálculo) →
``DiagnosticInterpretationService`` (leitura) → ``MaturityReport`` (web e PDF).
"""

from __future__ import annotations

from typing import Any

from src.modules.auth.model import UserDocument
from src.modules.maturity_diagnostics.catalog import (
    Catalog,
    ItemKind,
    Question,
    QuestionType,
    Section,
    StepKind,
)
from src.modules.maturity_diagnostics.engine import (
    AxisStatus,
    Evaluation,
    StepStatus,
    display_answer,
    evaluate,
    items_of,
    response_key,
    score_for,
)
from src.modules.maturity_diagnostics.interpretation import DiagnosticInterpretationService
from src.modules.maturity_diagnostics.methodology import (
    MATURITY_SCALE,
    METHODOLOGY_OBJECTIVE,
    METHODOLOGY_RESULTS,
    METHODOLOGY_SCORING,
    METHODOLOGY_VERSION,
    REPORT_VERSION,
    MaturityScale,
    relative_reading,
)
from src.modules.maturity_diagnostics.model import (
    DiagnosticItem,
    MaturityDiagnosticDocument,
    ResponseSource,
)
from src.modules.maturity_diagnostics.report_schema import (
    MaturityLevelOut,
    MaturityReport,
    ReportAnswerItem,
    ReportAnswerSection,
    ReportAnswerStep,
    ReportAxis,
    ReportDiagnosticInfo,
    ReportField,
    ReportItem,
    ReportMethodology,
    ReportMethodologyItem,
    ReportPerson,
    ReportPillar,
    ReportScope,
    ReportSummary,
    ReportVersions,
)
from src.shared.utils.time import utcnow

_CONTACT_FIELDS = {"name": "q05", "job_title": "q06", "email": "q07", "phone": "q08"}


def _fmt(value: float) -> str:
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


class DiagnosticReportService:
    def __init__(self, catalog: Catalog, scale: MaturityScale = MATURITY_SCALE) -> None:
        self._catalog = catalog
        self._scale = scale
        self._interpreter = DiagnosticInterpretationService(catalog, scale)

    # ------------------------------------------------------------------
    def evaluation_for(self, diagnostic: MaturityDiagnosticDocument) -> Evaluation:
        """Recalcula com as etapas disponíveis na conclusão (reprodutível)."""
        available: set[str] | None = None
        result: dict[str, Any] | None = diagnostic.result
        if result and isinstance(result.get("steps"), list):
            available = {
                step["step_id"]
                for step in result["steps"]
                if step.get("status") != StepStatus.MAINTENANCE.value
                and self._catalog.step(step["step_id"]) is not None
            }
        return evaluate(
            self._catalog,
            diagnostic.answer_values(),
            items=diagnostic.items,
            available_step_ids=available,
        )

    def build(
        self, diagnostic: MaturityDiagnosticDocument, agent: UserDocument | None
    ) -> MaturityReport:
        values = diagnostic.answer_values()
        evaluation = self.evaluation_for(diagnostic)
        company = diagnostic.company_snapshot
        interpretation = self._interpreter.interpret(
            values, evaluation, company_name=company.legal_name, items=diagnostic.items
        )
        visible = set(evaluation.visible_question_ids)

        # ---- identificação
        identification: list[ReportField] = []
        for question in self._catalog.questions:
            step = self._catalog.step(question.step_id)
            if step is None or step.kind is not StepKind.IDENTIFICATION:
                continue
            response = diagnostic.responses.get(question.id)
            value = response.value if response else None
            if not question.registry_field or response is None:
                origin = "diagnostic"
            elif response.source == ResponseSource.REGISTRY:
                origin = "registry"
            elif response.registry_value:
                origin = "adjusted"
            else:
                origin = "diagnostic"
            identification.append(
                ReportField(
                    question_id=question.id,
                    code=question.code,
                    label=question.label,
                    value=display_answer(question, value),
                    origin=origin,
                )
            )
        by_id = {field.question_id: field.value for field in identification}
        contact = ReportPerson(**{key: by_id.get(qid) for key, qid in _CONTACT_FIELDS.items()})

        # ---- eixos e pilares (resultado do motor)
        axes: list[ReportAxis] = []
        for axis in evaluation.axes:
            step = self._catalog.step(axis.step_id)
            if step is None:
                continue
            axes.append(
                ReportAxis(
                    step_id=step.id,
                    order=step.order,
                    title=step.title,
                    short_title=step.short_title,
                    description=step.description,
                    status=axis.status.value,
                    percent=axis.percent,
                    points=axis.points,
                    max_points=axis.max_points,
                    ems_points=axis.ems_points,
                    ems_max=axis.ems_max,
                    scored_questions=axis.scored_questions,
                    reading=relative_reading(axis.percent),
                )
            )
        pillar_meta = {p.id: p for p in self._catalog.pillars}
        worst = evaluation.worst_case
        worst_pillars = {p.pillar_id: p for p in worst.pillars} if worst else {}
        pillars = [
            ReportPillar(
                pillar_id=score.pillar_id,
                code=pillar_meta[score.pillar_id].code,
                name=pillar_meta[score.pillar_id].name,
                ems_weight=pillar_meta[score.pillar_id].ems_weight,
                points=score.points,
                max_points=score.max_points,
                percent=score.percent,
                ems_points=score.ems_points,
                ems_max=score.ems_max,
                answered=score.answered,
                total=score.total,
                reading=relative_reading(score.percent),
                worst_points=worst_pillars[score.pillar_id].points
                if score.pillar_id in worst_pillars
                else None,
                worst_ems_points=worst_pillars[score.pillar_id].ems_points
                if score.pillar_id in worst_pillars
                else None,
            )
            for score in evaluation.pillars
            if score.total > 0
        ]

        # ---- resumo
        ems = evaluation.ems
        partial = any(a.status is not AxisStatus.EVALUATED for a in evaluation.axes)
        percent = round(ems.points * 100 / ems.max_available, 1) if ems.max_available else None
        level = self._interpreter.classify(ems.points, partial=partial)
        headline = (
            f"Score geral de {_fmt(ems.points)} de {_fmt(ems.max_available)} pontos"
            + (" possíveis nos eixos avaliados" if partial else "")
            + "."
        )
        summary = ReportSummary(
            overall_score=ems.points,
            overall_max=ems.max_available,
            overall_percent=percent,
            partial=partial,
            maturity_level=MaturityLevelOut(
                level=level.level,
                name=level.name,
                description=level.description,
                interpretation=level.interpretation,
            )
            if level
            else None,
            maturity_scale_defined=self._scale.official and bool(self._scale.levels),
            headline=headline,
            worst_case_score=worst.ems.points if worst else None,
            worst_case_percent=round(worst.ems.points * 100 / worst.ems.max_available, 1)
            if worst and worst.ems.max_available
            else None,
        )

        evaluated = [a.title for a in axes if a.status == AxisStatus.EVALUATED.value]
        pending = [a.title for a in axes if a.status != AxisStatus.EVALUATED.value]
        scope = ReportScope(
            complete=not pending,
            evaluated_axes=evaluated,
            pending_axes=pending,
            text=(
                "Este diagnóstico avaliou todos os eixos do modelo disponíveis na plataforma."
                if not pending
                else "Este diagnóstico apresenta os resultados das dimensões disponíveis na "
                "plataforma no momento da sua realização. Os demais eixos serão incorporados "
                "progressivamente ao modelo de avaliação."
            ),
        )

        answers, item_sections = self._answers(diagnostic, evaluation, visible)
        return MaturityReport(
            diagnostic_id=diagnostic.id,
            versions=ReportVersions(
                diagnostic_version=diagnostic.catalog_version,
                methodology_version=METHODOLOGY_VERSION,
                report_version=REPORT_VERSION,
                maturity_scale_version=self._scale.version,
            ),
            generated_at=utcnow(),
            diagnostic=ReportDiagnosticInfo(
                id=diagnostic.id,
                status=diagnostic.status.value
                if hasattr(diagnostic.status, "value")
                else str(diagnostic.status),
                started_at=diagnostic.started_at,
                completed_at=diagnostic.completed_at,
                created_at=diagnostic.created_at,
            ),
            company=company,
            contact=contact,
            agent=ReportPerson(
                name=agent.name if agent else None,
                email=str(agent.email) if agent and agent.email else None,
            ),
            identification=identification,
            summary=summary,
            axes=axes,
            pillars=pillars,
            indicators=interpretation.indicators,
            alerts=evaluation.alerts,
            strengths=interpretation.strengths,
            attention_points=interpretation.attention_points,
            opportunities=interpretation.opportunities,
            analysis=interpretation.analysis,
            conclusions=interpretation.conclusions,
            scope=scope,
            methodology=self._methodology(),
            answers=answers,
            products=self._report_items(diagnostic, ItemKind.PRODUCT, item_sections),
            wastes=self._report_items(diagnostic, ItemKind.WASTE, item_sections),
        )

    # ------------------------------------------------------------------
    def _methodology(self) -> ReportMethodology:
        axes = [
            ReportMethodologyItem(title=step.title, description=step.description)
            for step in sorted(self._catalog.steps, key=lambda s: s.order)
            if step.kind is StepKind.AXIS
        ]
        pillars = [
            ReportMethodologyItem(
                title=pillar.name,
                description=f"Peso no EMS: {_fmt(pillar.ems_weight)}%."
                if pillar.ems_weight is not None
                else None,
            )
            for pillar in self._catalog.pillars
        ]
        scale_items = [
            ReportMethodologyItem(
                title=f"Nível {level.level} — {level.name}",
                description=f"{_fmt(level.min_score)} a {_fmt(level.max_score)} pontos. "
                f"{level.description}",
            )
            for level in self._scale.levels
        ]
        note = None
        if not self._scale.official:
            note = (
                "A régua oficial de níveis de maturidade ainda não está cadastrada; por isso "
                "o relatório apresenta o score sem classificação em níveis."
            )
        return ReportMethodology(
            objective=METHODOLOGY_OBJECTIVE,
            axes=axes,
            pillars=pillars,
            scoring=list(METHODOLOGY_SCORING),
            results=list(METHODOLOGY_RESULTS),
            maturity_scale=scale_items if self._scale.official else [],
            maturity_scale_note=note,
        )

    def _answer_item(
        self,
        question: Question,
        key: str,
        diagnostic: MaturityDiagnosticDocument,
        pillar_codes: dict[str, str],
    ) -> ReportAnswerItem:
        response = diagnostic.responses.get(key)
        value = response.value if response else None
        points = score_for(question, value)
        return ReportAnswerItem(
            question_id=key,
            code=question.code,
            label=question.label,
            answer=display_answer(question, value),
            source=response.source if response else None,
            scored=question.scored,
            points=points,
            max_points=question.max_points if question.scored else None,
            pillar_code=pillar_codes.get(question.pillar_id or ""),
        )

    def _section_answers(
        self,
        section: Section,
        diagnostic: MaturityDiagnosticDocument,
        visible: set[str],
        pillar_codes: dict[str, str],
    ) -> tuple[list[ReportAnswerItem], dict[str, list[ReportAnswerItem]]]:
        """Respostas gerais da seção e respostas por item (``item_id → respostas``)."""
        general: list[ReportAnswerItem] = []
        by_item: dict[str, list[ReportAnswerItem]] = {}
        for question in self._catalog.questions:
            if question.section_id != section.id:
                continue
            if question.type is QuestionType.ITEM_LIST:
                names = [item.name for item in items_of(diagnostic.items, question.item_kind)]
                general.append(
                    ReportAnswerItem(
                        question_id=question.id,
                        code=question.code,
                        label=question.label,
                        answer="; ".join(names) or None,
                    )
                )
                continue
            if question.per_item is None:
                if question.id in visible:
                    general.append(
                        self._answer_item(question, question.id, diagnostic, pillar_codes)
                    )
                continue
            for item in items_of(diagnostic.items, question.per_item):
                key = response_key(question.id, item.id)
                if key in visible:
                    by_item.setdefault(item.id, []).append(
                        self._answer_item(question, key, diagnostic, pillar_codes)
                    )
        # Reflexo por item (ex.: 1.8 de cada resíduo em Licenciamento e rastreabilidade).
        reference = section.item_reference
        if reference is not None:
            for item in items_of(diagnostic.items, reference.kind):
                for question_id in reference.question_ids:
                    question = self._catalog.question(question_id)
                    key = response_key(question_id, item.id)
                    if question is not None and key in visible:
                        by_item.setdefault(item.id, []).append(
                            self._answer_item(question, key, diagnostic, pillar_codes)
                        )
        return general, by_item

    def _answers(
        self,
        diagnostic: MaturityDiagnosticDocument,
        evaluation: Evaluation,
        visible: set[str],
    ) -> tuple[list[ReportAnswerStep], dict[str, list[ReportAnswerSection]]]:
        """Respostas por etapa (gerais + uma seção por item) e o índice por item."""
        axis_status = {a.step_id: a.status.value for a in evaluation.axes}
        pillar_codes = {p.id: p.code for p in self._catalog.pillars}
        steps: list[ReportAnswerStep] = []
        item_sections: dict[str, list[ReportAnswerSection]] = {}
        for step in sorted(self._catalog.steps, key=lambda s: s.order):
            status = (
                "identification"
                if step.kind is StepKind.IDENTIFICATION
                else axis_status.get(step.id, AxisStatus.MAINTENANCE.value)
            )
            sections: list[ReportAnswerSection] = []
            if status != AxisStatus.MAINTENANCE.value:
                axis_label = (
                    f"Eixo {step.order - 1}" if step.kind is StepKind.AXIS else step.short_title
                )
                for section in (s for s in self._catalog.sections if s.step_id == step.id):
                    general, by_item = self._section_answers(
                        section, diagnostic, visible, pillar_codes
                    )
                    if general:
                        sections.append(ReportAnswerSection(title=section.title, answers=general))
                    for item in diagnostic.items:
                        answers = by_item.get(item.id)
                        if not answers:
                            continue
                        sections.append(
                            ReportAnswerSection(
                                title=f"{section.title} — {item.name}",
                                answers=answers,
                                item_id=item.id,
                                item_name=item.name,
                                item_kind=item.kind.value,
                            )
                        )
                        item_sections.setdefault(item.id, []).append(
                            ReportAnswerSection(
                                title=f"{axis_label} · {section.title}",
                                answers=answers,
                                item_id=item.id,
                                item_name=item.name,
                                item_kind=item.kind.value,
                            )
                        )
            steps.append(
                ReportAnswerStep(
                    step_id=step.id, title=step.title, status=status, sections=sections
                )
            )
        return steps, item_sections

    def _report_items(
        self,
        diagnostic: MaturityDiagnosticDocument,
        kind: ItemKind,
        item_sections: dict[str, list[ReportAnswerSection]],
    ) -> list[ReportItem]:
        meta = self._catalog.item_kind(kind)
        result: list[ReportItem] = []
        item: DiagnosticItem
        for item in items_of(diagnostic.items, kind):  # type: ignore[assignment]
            sections = item_sections.get(item.id, [])
            scored = [a for section in sections for a in section.answers if a.scored]
            # O reflexo (ex.: 1.8 no Eixo 3) repete uma resposta: conta uma única vez.
            unique = {a.question_id: a for a in scored}.values()
            result.append(
                ReportItem(
                    id=item.id,
                    kind=kind.value,
                    kind_label=meta.label if meta else kind.value,
                    name=item.name,
                    description=item.description,
                    sections=sections,
                    points=int(sum(a.points or 0 for a in unique)),
                    max_points=sum(a.max_points or 0 for a in unique),
                )
            )
        return result


__all__ = ["DiagnosticReportService"]
