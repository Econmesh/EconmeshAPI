"""Regras de negócio do Diagnóstico de Maturidade Circular (DMC).

Autorização: o escopo do agente (carteira) é sempre carregado do banco via
``ScopeService`` — nunca a partir de ids enviados pelo cliente. Um agente só
cria/vê/edita diagnósticos de empresas da sua carteira e, para diagnósticos
existentes, somente os que estão sob sua responsabilidade.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from src.core.logging import get_logger
from src.modules.auth.model import UserDocument
from src.modules.auth.repository import AuthRepository
from src.modules.companies.model import CompanyDocument
from src.modules.dmc.audit import AuditLog
from src.modules.dmc.scope import PortfolioScope, ScopeService
from src.modules.maturity_diagnostics.catalog import (
    Catalog,
    Question,
    QuestionType,
    RegistryField,
    StepAvailability,
    get_catalog,
)
from src.modules.maturity_diagnostics.engine import (
    AnswerValue,
    Evaluation,
    InvalidAnswerError,
    StepStatus,
    evaluate,
    normalize_answer,
    score_for,
)
from src.modules.maturity_diagnostics.model import (
    CompanySnapshot,
    DiagnosticResponse,
    DiagnosticStatus,
    MaturityDiagnosticDocument,
    ResponseSource,
)
from src.modules.maturity_diagnostics.repository import MaturityDiagnosticsRepository
from src.modules.maturity_diagnostics.schema import (
    DiagnosticCompanyItem,
    DiagnosticCompanyListResponse,
    DiagnosticDetail,
    DiagnosticListResponse,
    DiagnosticReport,
    DiagnosticSummary,
    ReportAnswer,
    ReportPillar,
    ReportSection,
    ReportStep,
    ResponseOut,
    SaveResponsesRequest,
)
from src.modules.users.repository import UsersRepository
from src.shared.utils.time import utcnow

logger = get_logger(__name__)

AUDIT_RESOURCE = "maturity_diagnostic"
AUDIT_CREATED = "maturity_diagnostic.created"
AUDIT_COMPLETED = "maturity_diagnostic.completed"

_COMPLETED_PER_COMPANY = 5


class MaturityDiagnosticsService:
    def __init__(
        self,
        *,
        repository: MaturityDiagnosticsRepository,
        auth: AuthRepository,
        users: UsersRepository,
        scope: ScopeService,
        audit: AuditLog | None = None,
        catalog: Catalog | None = None,
    ) -> None:
        self._repo = repository
        self._auth = auth
        self._users = users
        self._scope = scope
        self._audit = audit
        self._catalog = catalog or get_catalog()

    # ------------------------------------------------------------- contexto
    async def _context(self, firebase_uid: str) -> tuple[UserDocument, PortfolioScope]:
        agent = await self._auth.get_by_firebase_uid(firebase_uid)
        if agent is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return agent, await self._scope.for_agent(agent.id)

    async def _load_owned(
        self, firebase_uid: str, diagnostic_id: UUID
    ) -> tuple[UserDocument, PortfolioScope, MaturityDiagnosticDocument, CompanyDocument]:
        agent, scope = await self._context(firebase_uid)
        diagnostic = await self._repo.get(diagnostic_id)
        if diagnostic is None:
            raise NotFoundError("Diagnostic not found.", code="diagnostic_not_found")
        company = scope.require_company(diagnostic.company_id)
        if diagnostic.agent_user_id != agent.id:
            raise ForbiddenError(
                "This diagnostic belongs to another DMC agent.",
                code="diagnostic_other_agent",
            )
        return agent, scope, diagnostic, company

    # -------------------------------------------------------------- leitura
    def catalog(self) -> Catalog:
        return self._catalog

    async def list_companies(self, firebase_uid: str) -> DiagnosticCompanyListResponse:
        agent, scope = await self._context(firebase_uid)
        company_ids = [
            link.company_id for link in scope.links if link.company_id in scope.companies
        ]
        diagnostics = await self._repo.list_for_companies(company_ids)
        by_company: dict[UUID, list[MaturityDiagnosticDocument]] = {}
        for diagnostic in diagnostics:
            by_company.setdefault(diagnostic.company_id, []).append(diagnostic)

        items: list[DiagnosticCompanyItem] = []
        for company_id in company_ids:
            company = scope.companies[company_id]
            history = by_company.get(company_id, [])
            open_diag = next((d for d in history if d.is_open), None)
            completed = [
                self._summary(d, company)
                for d in history
                if d.status == DiagnosticStatus.COMPLETED and d.agent_user_id == agent.id
            ][:_COMPLETED_PER_COMPANY]
            address = company.address
            items.append(
                DiagnosticCompanyItem(
                    company_id=company.id,
                    legal_name=company.legal_name,
                    trade_name=company.trade_name,
                    tax_id=company.tax_id,
                    sector=company.sector,
                    city=address.city if address else None,
                    state=address.state if address else None,
                    registration_status=company.registration_status,
                    open_diagnostic=(
                        self._summary(open_diag, company)
                        if open_diag is not None and open_diag.agent_user_id == agent.id
                        else None
                    ),
                    open_by_other_agent=(
                        open_diag is not None and open_diag.agent_user_id != agent.id
                    ),
                    completed=completed,
                )
            )
        return DiagnosticCompanyListResponse(items=items, total=len(items))

    async def list_diagnostics(
        self,
        firebase_uid: str,
        *,
        company_id: UUID | None = None,
        status: DiagnosticStatus | None = None,
    ) -> DiagnosticListResponse:
        agent, scope = await self._context(firebase_uid)
        if company_id is not None:
            scope.require_company(company_id)
        docs = await self._repo.list_for_agent(
            agent.id,
            company_ids=list(scope.company_ids),
            company_id=company_id,
            status=status,
        )
        items = [
            self._summary(doc, scope.companies[doc.company_id])
            for doc in docs
            if doc.company_id in scope.companies
        ]
        return DiagnosticListResponse(items=items, total=len(items))

    async def get(self, firebase_uid: str, diagnostic_id: UUID) -> DiagnosticDetail:
        agent, _, diagnostic, company = await self._load_owned(firebase_uid, diagnostic_id)
        return self._detail(diagnostic, company, agent)

    # ------------------------------------------------------------- criação
    async def create(
        self, firebase_uid: str, company_id: UUID
    ) -> tuple[DiagnosticDetail, bool]:
        """Inicia (ou retoma) o diagnóstico. Retorna ``(detalhe, criado)``."""
        agent, scope = await self._context(firebase_uid)
        company = scope.require_company(company_id)
        existing = await self._repo.get_open_for_company(company.id)
        if existing is not None:
            if existing.agent_user_id != agent.id:
                raise ConflictError(
                    "Another DMC agent has an open diagnostic for this company.",
                    code="diagnostic_open_by_other_agent",
                )
            return self._detail(existing, company, agent), False

        responses = await self._registry_prefill(company, agent.id)
        values = {qid: resp.value for qid, resp in responses.items()}
        evaluation = evaluate(self._catalog, values)
        first_step = self._catalog.available_steps()[0].id
        diagnostic = MaturityDiagnosticDocument(
            company_id=company.id,
            agent_user_id=agent.id,
            catalog_version=self._catalog.version,
            responses=responses,
            current_step=first_step,
            progress=evaluation.progress,
            evaluation=evaluation.model_dump(mode="python"),
            company_snapshot=_company_snapshot(company),
        )
        created = await self._repo.create(diagnostic)
        await self._record(AUDIT_CREATED, created, agent.id, after={"company_id": company.id})
        logger.info(
            "maturity_diagnostic_created",
            diagnostic_id=str(created.id),
            company_id=str(company.id),
            agent_user_id=str(agent.id),
        )
        return self._detail(created, company, agent), True

    async def _registry_prefill(
        self, company: CompanyDocument, agent_id: UUID
    ) -> dict[str, DiagnosticResponse]:
        owner = (
            await self._auth.get_by_id(company.owner_user_id)
            if company.owner_user_id is not None
            else None
        )
        profile = (
            await self._users.get_by_user(company.owner_user_id)
            if company.owner_user_id is not None
            else None
        )
        registry: dict[RegistryField, str | None] = {
            RegistryField.LEGAL_NAME: company.legal_name,
            RegistryField.TAX_ID: company.tax_id,
            RegistryField.SECTOR: company.sector,
            RegistryField.CONTACT_NAME: company.legal_representative
            or (owner.name if owner else None),
            RegistryField.CONTACT_JOB_TITLE: profile.job_title if profile else None,
            RegistryField.EMAIL: company.email or (str(owner.email) if owner else None),
            RegistryField.PHONE: company.phone or (owner.phone if owner else None),
        }
        now = utcnow()
        responses: dict[str, DiagnosticResponse] = {}
        for question in self._catalog.questions:
            if question.registry_field is None:
                continue
            raw = registry.get(question.registry_field)
            if not raw or not str(raw).strip():
                continue
            try:
                value = normalize_answer(question, str(raw))
            except InvalidAnswerError:
                # Cadastro com formato inesperado: o agente corrige no formulário.
                value = None if not question.read_only else str(raw).strip()
            if value is None:
                continue
            responses[question.id] = DiagnosticResponse(
                value=value,
                source=ResponseSource.REGISTRY,
                registry_value=str(raw).strip(),
                updated_at=now,
                updated_by=agent_id,
            )
        return responses

    # ---------------------------------------------------- salvamento (autosave)
    async def save_responses(
        self, firebase_uid: str, diagnostic_id: UUID, payload: SaveResponsesRequest
    ) -> DiagnosticDetail:
        agent, _, diagnostic, company = await self._load_owned(firebase_uid, diagnostic_id)
        self._ensure_editable(diagnostic)
        if payload.current_step is not None:
            step = self._catalog.step(payload.current_step)
            if step is None or step.availability is not StepAvailability.AVAILABLE:
                raise ValidationAppError("Invalid step.", code="invalid_step")

        errors: dict[str, str] = {}
        updates: dict[str, DiagnosticResponse] = {}
        now = utcnow()
        for answer in payload.answers:
            question = self._catalog.question(answer.question_id)
            if question is None:
                errors[answer.question_id] = "Pergunta desconhecida."
                continue
            step = self._catalog.step(question.step_id)
            if step is None or step.availability is not StepAvailability.AVAILABLE:
                errors[question.id] = "Etapa em manutenção."
                continue
            if question.read_only:
                errors[question.id] = "Dado cadastral não editável no diagnóstico."
                continue
            try:
                value = normalize_answer(question, answer.value)
            except InvalidAnswerError as exc:
                errors[question.id] = exc.message
                continue
            previous = diagnostic.responses.get(question.id)
            if (
                previous is not None
                and answer.edited_at is not None
                and _aware(answer.edited_at) < _aware(previous.updated_at)
            ):
                # Edição offline mais antiga que a gravada: mantém a do servidor.
                continue
            updates[question.id] = _build_response(question, value, previous, agent.id, now)

        if errors:
            raise ValidationAppError(
                "Some answers are invalid.",
                code="validation_error",
                details={"errors": errors},
            )
        saved = diagnostic
        if updates or payload.current_step is not None:
            result = await self._repo.save_responses(
                diagnostic.id, updates, current_step=payload.current_step
            )
            if result is None:
                raise ConflictError(
                    "This diagnostic can no longer be edited.", code="diagnostic_closed"
                )
            saved = result
        if updates:
            saved = await self._refresh_evaluation(saved)
        return self._detail(saved, company, agent)

    async def _refresh_evaluation(
        self, diagnostic: MaturityDiagnosticDocument
    ) -> MaturityDiagnosticDocument:
        evaluation = evaluate(self._catalog, diagnostic.answer_values())
        patch: dict[str, Any] = {
            "progress": evaluation.progress,
            "evaluation": evaluation.model_dump(mode="python"),
        }
        if diagnostic.status == DiagnosticStatus.NOT_STARTED:
            patch["status"] = DiagnosticStatus.IN_PROGRESS.value
        if diagnostic.started_at is None:
            patch["started_at"] = utcnow()
        updated = await self._repo.update(diagnostic.id, patch)
        return updated or diagnostic

    # ------------------------------------------------------------- conclusão
    async def validate_step(
        self, firebase_uid: str, diagnostic_id: UUID, step_id: str
    ) -> DiagnosticDetail:
        """Confere se a etapa pode ser concluída e avança para a próxima disponível."""
        agent, _, diagnostic, company = await self._load_owned(firebase_uid, diagnostic_id)
        self._ensure_editable(diagnostic)
        step = self._catalog.step(step_id)
        if step is None or step.availability is not StepAvailability.AVAILABLE:
            raise ValidationAppError("Invalid step.", code="invalid_step")
        evaluation = evaluate(self._catalog, diagnostic.answer_values())
        progress = next(s for s in evaluation.steps if s.step_id == step_id)
        if progress.missing_required:
            raise ValidationAppError(
                "Answer all required questions to complete this step.",
                code="step_incomplete",
                details={
                    "missing": progress.missing_required,
                    "errors": dict.fromkeys(progress.missing_required, "Campo obrigatório."),
                },
            )
        next_step = self._next_available_step(step_id)
        updated = await self._repo.update(
            diagnostic.id, {"current_step": next_step or step_id}
        )
        return self._detail(updated or diagnostic, company, agent)

    async def complete(self, firebase_uid: str, diagnostic_id: UUID) -> DiagnosticDetail:
        agent, _, diagnostic, company = await self._load_owned(firebase_uid, diagnostic_id)
        self._ensure_editable(diagnostic)
        evaluation = evaluate(self._catalog, diagnostic.answer_values())
        if not evaluation.complete:
            missing = [q for s in evaluation.steps for q in s.missing_required]
            raise ValidationAppError(
                "Answer all required questions before completing the diagnostic.",
                code="diagnostic_incomplete",
                details={"missing": missing},
            )
        now = utcnow()
        result = {
            **evaluation.model_dump(mode="python"),
            "catalog_version": self._catalog.version,
            "completed_at": now,
        }
        updated = await self._repo.update(
            diagnostic.id,
            {
                "status": DiagnosticStatus.COMPLETED.value,
                "is_open": False,
                "progress": evaluation.progress,
                "evaluation": evaluation.model_dump(mode="python"),
                "result": result,
                "completed_at": now,
                "completed_by": agent.id,
                "company_snapshot": _company_snapshot(company).model_dump(),
            },
        )
        if updated is None:
            raise ConflictError(
                "This diagnostic can no longer be edited.", code="diagnostic_closed"
            )
        await self._record(
            AUDIT_COMPLETED,
            updated,
            agent.id,
            after={
                "progress": evaluation.progress,
                "ems_points": evaluation.ems.points,
                "pillars": {p.pillar_id: p.points for p in evaluation.pillars},
            },
        )
        return self._detail(updated, company, agent)

    # --------------------------------------------------------------- relatório
    async def report(self, firebase_uid: str, diagnostic_id: UUID) -> DiagnosticReport:
        agent, _, diagnostic, company = await self._load_owned(firebase_uid, diagnostic_id)
        if diagnostic.status != DiagnosticStatus.COMPLETED:
            raise ConflictError(
                "The report is available after the diagnostic is completed.",
                code="diagnostic_not_completed",
            )
        evaluation = self._evaluation_for(diagnostic)
        visible = set(evaluation.visible_question_ids)
        # Etapas que estavam em manutenção quando o diagnóstico foi concluído
        # continuam assim no relatório, mesmo que tenham sido ativadas depois.
        maintenance_at_completion = {
            progress.step_id
            for progress in evaluation.steps
            if progress.status is StepStatus.MAINTENANCE
        }
        steps: list[ReportStep] = []
        for step in sorted(self._catalog.steps, key=lambda s: s.order):
            sections: list[ReportSection] = []
            for section in (s for s in self._catalog.sections if s.step_id == step.id):
                answers = [
                    _report_answer(q, diagnostic.responses.get(q.id))
                    for q in self._catalog.questions
                    if q.section_id == section.id and q.id in visible
                ]
                sections.append(ReportSection(id=section.id, title=section.title, answers=answers))
            steps.append(
                ReportStep(
                    id=step.id,
                    title=step.title,
                    availability=(
                        StepAvailability.MAINTENANCE.value
                        if step.id in maintenance_at_completion
                        else step.availability.value
                    ),
                    sections=sections,
                )
            )
        pillar_meta = {p.id: p for p in self._catalog.pillars}
        pillars = [
            ReportPillar(
                **score.model_dump(),
                code=pillar_meta[score.pillar_id].code,
                name=pillar_meta[score.pillar_id].name,
                ems_weight=pillar_meta[score.pillar_id].ems_weight,
            )
            for score in evaluation.pillars
        ]
        return DiagnosticReport(
            diagnostic=self._summary(diagnostic, company),
            company=diagnostic.company_snapshot,
            agent_name=agent.name or str(agent.email),
            catalog_version=diagnostic.catalog_version,
            generated_at=utcnow(),
            steps=steps,
            pillars=pillars,
            ems=evaluation.ems,
            alerts=evaluation.alerts,
        )

    # --------------------------------------------------------------- helpers
    def _evaluation_for(self, diagnostic: MaturityDiagnosticDocument) -> Evaluation:
        """Concluído: resultado congelado (versão do catálogo da época). Aberto: ao vivo."""
        if not diagnostic.is_open and diagnostic.result:
            return Evaluation.model_validate(diagnostic.result)
        return evaluate(self._catalog, diagnostic.answer_values())

    def _next_available_step(self, step_id: str) -> str | None:
        ordered = sorted(self._catalog.available_steps(), key=lambda s: s.order)
        ids = [s.id for s in ordered]
        if step_id not in ids:
            return None
        index = ids.index(step_id)
        return ids[index + 1] if index + 1 < len(ids) else None

    @staticmethod
    def _ensure_editable(diagnostic: MaturityDiagnosticDocument) -> None:
        if not diagnostic.is_open:
            raise ConflictError(
                "This diagnostic is completed and can no longer be edited.",
                code="diagnostic_closed",
            )

    def _summary(
        self, diagnostic: MaturityDiagnosticDocument, company: CompanyDocument | None
    ) -> DiagnosticSummary:
        snapshot = diagnostic.company_snapshot
        return DiagnosticSummary(
            id=diagnostic.id,
            company_id=diagnostic.company_id,
            company_name=(company.trade_name or company.legal_name)
            if company is not None
            else (snapshot.trade_name or snapshot.legal_name),
            company_tax_id=company.tax_id if company is not None else snapshot.tax_id,
            agent_user_id=diagnostic.agent_user_id,
            status=diagnostic.status,
            progress=diagnostic.progress,
            current_step=diagnostic.current_step,
            created_at=diagnostic.created_at,
            updated_at=diagnostic.updated_at,
            started_at=diagnostic.started_at,
            completed_at=diagnostic.completed_at,
        )

    def _detail(
        self,
        diagnostic: MaturityDiagnosticDocument,
        company: CompanyDocument,
        agent: UserDocument,
    ) -> DiagnosticDetail:
        evaluation = self._evaluation_for(diagnostic)
        summary = self._summary(diagnostic, company)
        return DiagnosticDetail(
            **summary.model_dump(),
            catalog_version=diagnostic.catalog_version,
            company=(
                diagnostic.company_snapshot
                if not diagnostic.is_open
                else _company_snapshot(company)
            ),
            agent_name=agent.name or str(agent.email),
            responses={
                qid: ResponseOut(
                    value=resp.value,
                    score=resp.score,
                    source=resp.source,
                    registry_value=resp.registry_value,
                    updated_at=resp.updated_at,
                )
                for qid, resp in diagnostic.responses.items()
            },
            evaluation=evaluation,
            can_edit=diagnostic.is_open,
        )

    async def _record(
        self,
        action: str,
        diagnostic: MaturityDiagnosticDocument,
        actor_id: UUID,
        *,
        after: dict[str, Any] | None = None,
    ) -> None:
        if self._audit is None:
            return
        try:
            await self._audit.record(
                action,
                resource_type=AUDIT_RESOURCE,
                resource_id=diagnostic.id,
                actor_user_id=actor_id,
                after=after,
            )
        except Exception:  # noqa: BLE001 — auditoria não pode quebrar o fluxo
            logger.exception("maturity_diagnostic_audit_failed", diagnostic_id=str(diagnostic.id))


# ------------------------------------------------------------------- funções
def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _company_snapshot(company: CompanyDocument) -> CompanySnapshot:
    address = company.address
    return CompanySnapshot(
        legal_name=company.legal_name,
        trade_name=company.trade_name,
        tax_id=company.tax_id,
        sector=company.sector,
        city=address.city if address else None,
        state=address.state if address else None,
    )


def _build_response(
    question: Question,
    value: AnswerValue,
    previous: DiagnosticResponse | None,
    agent_id: UUID,
    now: datetime,
) -> DiagnosticResponse:
    registry_value = previous.registry_value if previous is not None else None
    source = ResponseSource.AGENT
    if registry_value is not None and isinstance(value, str):
        comparable = value
        original = registry_value
        if question.type in (QuestionType.PHONE, QuestionType.TAX_ID):
            comparable = "".join(ch for ch in value if ch.isdigit())
            original = "".join(ch for ch in registry_value if ch.isdigit())
        if comparable == original:
            source = ResponseSource.REGISTRY
    return DiagnosticResponse(
        value=value,
        score=score_for(question, value),
        source=source,
        registry_value=registry_value,
        updated_at=now,
        updated_by=agent_id,
    )


def _display_value(question: Question, value: AnswerValue) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        labels = [(question.option(v).label if question.option(v) else v) for v in value]
        return ", ".join(labels)
    if question.options:
        option = question.option(value)
        return option.label if option else value
    return value


def _report_answer(question: Question, response: DiagnosticResponse | None) -> ReportAnswer:
    value = response.value if response else None
    return ReportAnswer(
        question_id=question.id,
        code=question.code,
        number=question.number,
        label=question.label,
        value=value,
        display_value=_display_value(question, value),
        source=response.source if response else None,
        scored=question.scored,
        points=score_for(question, value),
        max_points=question.max_points if question.scored else None,
        pillar_id=question.pillar_id,
    )


__all__ = ["MaturityDiagnosticsService"]
