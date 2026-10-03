"""Camada de interpretação do diagnóstico (``DiagnosticInterpretationService``).

Recebe o resultado do motor de cálculo (``engine.evaluate``) e as respostas e
produz a leitura do relatório — indicadores, destaques, pontos de atenção,
oportunidades, análise e conclusão — a partir das regras de
``methodology.py``. Não recalcula pontuação nem contém regras de pesos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.modules.maturity_diagnostics.catalog import Catalog, Question, QuestionType, StepKind
from src.modules.maturity_diagnostics.engine import (
    AnswerValue,
    AxisStatus,
    Evaluation,
    display_answer,
    ems_contribution,
    is_answered,
    score_for,
)
from src.modules.maturity_diagnostics.methodology import (
    CONTEXT_RULES,
    INDICATORS,
    MATURITY_SCALE,
    ContextKind,
    MaturityLevel,
    MaturityScale,
    Tier,
    relative_reading,
    tier_for,
)
from src.modules.maturity_diagnostics.report_schema import (
    ReportAnalysis,
    ReportFinding,
    ReportIndicator,
    ReportOpportunity,
)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "moderate": 2}
_HIGHLIGHT_LIMIT = 3


def _fmt(value: float) -> str:
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} e {items[-1]}"


@dataclass
class Interpretation:
    indicators: list[ReportIndicator] = field(default_factory=list)
    strengths: list[ReportFinding] = field(default_factory=list)
    attention_points: list[ReportFinding] = field(default_factory=list)
    opportunities: list[ReportOpportunity] = field(default_factory=list)
    analysis: ReportAnalysis = field(default_factory=ReportAnalysis)
    conclusions: list[str] = field(default_factory=list)


class DiagnosticInterpretationService:
    def __init__(self, catalog: Catalog, scale: MaturityScale = MATURITY_SCALE) -> None:
        self._catalog = catalog
        self._scale = scale

    # ------------------------------------------------------------- público
    def interpret(
        self,
        values: Mapping[str, AnswerValue],
        evaluation: Evaluation,
        *,
        company_name: str,
    ) -> Interpretation:
        visible = set(evaluation.visible_question_ids)
        evaluated_steps = {
            axis.step_id for axis in evaluation.axes if axis.status is AxisStatus.EVALUATED
        }
        scored = [
            q
            for q in self._catalog.questions
            if q.scored and q.id in visible and q.step_id in evaluated_steps
        ]
        result = Interpretation()
        result.indicators = [self._indicator(q, values.get(q.id)) for q in scored]
        weights = {q.id: q.ems_weight or 0.0 for q in scored}

        # ---- destaques / atenção / oportunidades a partir dos indicadores
        lost: list[tuple[float, Question]] = []
        for indicator, question in zip(result.indicators, scored, strict=True):
            content = INDICATORS.get(question.id)
            if indicator.tier == Tier.HIGH.value:
                result.strengths.append(
                    ReportFinding(
                        title=indicator.title,
                        text=indicator.interpretation or indicator.answer or "",
                        source_question_ids=[question.id],
                    )
                )
                continue
            if indicator.tier == "unanswered" or (content and not content.attention_on_low):
                continue
            result.attention_points.append(
                ReportFinding(
                    title=indicator.title,
                    text=indicator.interpretation or indicator.answer or "",
                    severity="high" if indicator.tier == Tier.LOW.value else "moderate",
                    source_question_ids=[question.id],
                )
            )
            if content and content.opportunity_title:
                gap = (question.ems_weight or 0.0) - (indicator.ems_points or 0.0)
                lost.append((gap, question))

        # ---- alertas críticos sobrepõem a severidade
        for alert in evaluation.alerts:
            finding = next(
                (f for f in result.attention_points if alert.question_id in f.source_question_ids),
                None,
            )
            if finding is not None:
                finding.severity = alert.level
            else:
                result.attention_points.append(
                    ReportFinding(
                        title="Alerta",
                        text=alert.message,
                        severity=alert.level,
                        source_question_ids=[alert.question_id],
                    )
                )

        # ---- regras contextuais (perguntas não pontuadas)
        context_opportunities: list[ReportOpportunity] = []
        for rule in CONTEXT_RULES:
            question = self._catalog.question(rule.question_id)
            if (
                question is None
                or question.id not in visible
                or question.step_id not in evaluated_steps
            ):
                continue
            value = values.get(rule.question_id)
            selected = value if isinstance(value, list) else [value] if value else []
            if not set(selected) & set(rule.values):
                continue
            text = rule.text
            sources = [rule.question_id]
            if rule.detail_question_id:
                detail_q = self._catalog.question(rule.detail_question_id)
                detail = values.get(rule.detail_question_id)
                if detail_q is not None and detail_q.id in visible and is_answered(detail):
                    text = f"{text} Resposta registrada: {display_answer(detail_q, detail)}."
                    sources.append(detail_q.id)
            finding = ReportFinding(title=rule.title, text=text, source_question_ids=sources)
            if rule.kind is ContextKind.STRENGTH:
                result.strengths.append(finding)
            elif rule.kind is ContextKind.ATTENTION:
                finding.severity = "moderate"
                result.attention_points.append(finding)
            else:
                context_opportunities.append(
                    ReportOpportunity(
                        number=0, title=rule.title, text=text, source_question_ids=sources
                    )
                )

        result.attention_points.sort(key=lambda f: _SEVERITY_ORDER.get(f.severity or "", 9))
        # Destaques: indicadores de maior peso primeiro, depois contexto.
        result.strengths.sort(
            key=lambda f: -max((weights.get(qid, 0.0) for qid in f.source_question_ids), default=0)
        )

        # Ordem: alertas críticos primeiro, depois maior perda de pontos no EMS.
        critical = {a.question_id for a in evaluation.alerts if a.level == "critical"}
        lost.sort(key=lambda item: (item[1].id in critical, item[0]), reverse=True)
        opportunities = [
            ReportOpportunity(
                number=0,
                title=INDICATORS[q.id].opportunity_title or "",
                text=INDICATORS[q.id].opportunity_text or "",
                source_question_ids=[q.id],
            )
            for _, q in lost
        ] + context_opportunities
        for index, opportunity in enumerate(opportunities, start=1):
            opportunity.number = index
        result.opportunities = opportunities

        result.analysis = self._analysis(values, evaluation, visible, evaluated_steps, result)
        result.conclusions = self._conclusions(evaluation, result, company_name)
        return result

    def classify(self, score: float | None, *, partial: bool) -> MaturityLevel | None:
        """Nível de maturidade — só com régua oficial e diagnóstico completo."""
        if partial or not self._scale.official:
            return None
        return self._scale.classify(score)

    # ------------------------------------------------------------ privados
    def _indicator(self, question: Question, value: AnswerValue) -> ReportIndicator:
        content = INDICATORS.get(question.id)
        points = score_for(question, value)
        tier = "unanswered" if points is None else tier_for(points, question.max_points).value
        interpretation = None
        if content is not None and isinstance(value, str):
            interpretation = content.by_option.get(value)
        contribution = ems_contribution(question, value)
        return ReportIndicator(
            question_id=question.id,
            code=question.code,
            title=content.title if content else question.label,
            label=question.label,
            step_id=question.step_id,
            pillar_id=question.pillar_id,
            answer=display_answer(question, value),
            points=points,
            max_points=question.max_points,
            percent=round(points * 100 / question.max_points, 1)
            if points is not None and question.max_points
            else None,
            pillar_weight=question.pillar_weight,
            ems_weight=question.ems_weight,
            ems_points=round(contribution, 2) if contribution is not None else None,
            tier=tier,
            interpretation=interpretation,
        )

    def _analysis(
        self,
        values: Mapping[str, AnswerValue],
        evaluation: Evaluation,
        visible: set[str],
        evaluated_steps: set[str],
        result: Interpretation,
    ) -> ReportAnalysis:
        analysis = ReportAnalysis()
        # Dados observados: respostas de contexto (escolhas) dos eixos avaliados.
        for question in self._catalog.questions:
            step = self._catalog.step(question.step_id)
            if (
                step is None
                or question.scored
                or question.id not in visible
                or question.type not in (QuestionType.SINGLE_CHOICE, QuestionType.MULTI_CHOICE)
                or (step.kind is StepKind.AXIS and question.step_id not in evaluated_steps)
            ):
                continue
            value = values.get(question.id)
            if not is_answered(value):
                continue
            label = question.label.rstrip("?:").strip()
            analysis.observed_data.append(f"{label}: {display_answer(question, value)}")

        pillar_names = {p.id: p for p in self._catalog.pillars}
        analysis.calculated_indicators.append(
            f"Score geral (EMS): {_fmt(evaluation.ems.points)} de "
            f"{_fmt(evaluation.ems.max_available)} pontos possíveis."
        )
        for pillar in evaluation.pillars:
            if not pillar.total:
                continue
            meta = pillar_names[pillar.pillar_id]
            analysis.calculated_indicators.append(
                f"{meta.name}: {pillar.points} de {pillar.max_points} pontos "
                f"({_fmt(pillar.percent or 0)}%), contribuição de {_fmt(pillar.ems_points)} de "
                f"{_fmt(pillar.ems_max)} pontos no EMS."
            )
            reading = relative_reading(pillar.percent)
            if reading:
                analysis.interpretation.append(f"{meta.name}: {reading}.")
        for axis in evaluation.axes:
            step = self._catalog.step(axis.step_id)
            if step is None or axis.status is not AxisStatus.EVALUATED or axis.percent is None:
                continue
            analysis.calculated_indicators.append(
                f"{step.title}: {_fmt(axis.percent)}% do máximo ponderado do eixo."
            )
        if result.attention_points:
            analysis.interpretation.append(
                "Os pontos de atenção concentram-se em: "
                f"{_join([f.title.lower() for f in result.attention_points[:_HIGHLIGHT_LIMIT]])}."
            )
        analysis.opportunities = [o.title for o in result.opportunities]
        return analysis

    def _conclusions(
        self, evaluation: Evaluation, result: Interpretation, company_name: str
    ) -> list[str]:
        evaluated = [
            self._catalog.step(a.step_id).title  # type: ignore[union-attr]
            for a in evaluation.axes
            if a.status is AxisStatus.EVALUATED
        ]
        pending = [
            self._catalog.step(a.step_id).title  # type: ignore[union-attr]
            for a in evaluation.axes
            if a.status is not AxisStatus.EVALUATED
        ]
        ems = evaluation.ems
        percent = ems.points * 100 / ems.max_available if ems.max_available else 0
        paragraphs = [
            f"O diagnóstico de {company_name} resultou em score geral de {_fmt(ems.points)} "
            f"de {_fmt(ems.max_available)} pontos possíveis ({_fmt(round(percent, 1))}%), "
            f"considerando {_join(evaluated)}."
        ]
        best = [f.title.lower() for f in result.strengths[:_HIGHLIGHT_LIMIT]]
        if best:
            paragraphs.append(f"Os melhores resultados foram observados em {_join(best)}.")
        attention = [f.title.lower() for f in result.attention_points[:_HIGHLIGHT_LIMIT]]
        if attention:
            paragraphs.append(f"Requerem atenção: {_join(attention)}.")
        if result.opportunities:
            top = [o.title.lower() for o in result.opportunities[:_HIGHLIGHT_LIMIT]]
            plural = "oportunidades" if len(result.opportunities) > 1 else "oportunidade"
            paragraphs.append(
                f"Foram identificadas {len(result.opportunities)} {plural} de melhoria, "
                f"com destaque para {_join(top)}."
            )
        if pending:
            paragraphs.append(
                f"Não foram avaliados neste diagnóstico: {_join(pending)}. O resultado não "
                "representa a avaliação completa do modelo."
            )
        else:
            paragraphs.append("Todos os eixos do modelo foram avaliados neste diagnóstico.")
        if not self._scale.official:
            paragraphs.append(
                "A classificação em nível de maturidade não foi aplicada porque a régua "
                "oficial de maturidade ainda não está cadastrada."
            )
        return paragraphs


__all__ = ["DiagnosticInterpretationService", "Interpretation"]
