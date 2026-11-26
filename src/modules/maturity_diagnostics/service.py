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
    ItemKind,
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
    evaluate,
    items_of,
    normalize_answer,
    score_for,
    split_key,
)
from src.modules.maturity_diagnostics.items import migrate_legacy, new_item_id
from src.modules.maturity_diagnostics.model import (
    CompanySnapshot,
    DiagnosticItem,
    DiagnosticResponse,
    DiagnosticStatus,
    MaturityDiagnosticDocument,
    ResponseSource,
)
from src.modules.maturity_diagnostics.report_pdf import render_report_pdf, report_filename
from src.modules.maturity_diagnostics.report_schema import MaturityReport
from src.modules.maturity_diagnostics.report_service import DiagnosticReportService
from src.modules.maturity_diagnostics.repository import MaturityDiagnosticsRepository
from src.modules.maturity_diagnostics.schema import (
    DiagnosticCompanyItem,
    DiagnosticCompanyListResponse,
    DiagnosticDetail,
    DiagnosticListResponse,
    DiagnosticSummary,
    ItemCreate,
    ItemOut,
    ItemUpdate,
    ResponseOut,
    SaveResponsesRequest,
)
from src.modules.users.repository import UsersRepository
from src.shared.utils.time import utcnow

logger = get_logger(__name__)

AUDIT_RESOURCE = "maturity_diagnostic"
AUDIT_CREATED = "maturity_diagnostic.created"
AUDIT_COMPLETED = "maturity_diagnostic.completed"
AUDIT_REPORT_GENERATED = "maturity_diagnostic.report_generated"
AUDIT_PDF_GENERATED = "maturity_diagnostic.report_pdf_generated"

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
        return agent, scope, await self._migrated(diagnostic), company

    async def _migrated(
        self, diagnostic: MaturityDiagnosticDocument
    ) -> MaturityDiagnosticDocument:
        """Compatibilidade: converte diagnósticos antigos (1.1/1.7 em texto livre).

        Abertos: a conversão é persistida. Concluídos: apenas em memória (o
        documento concluído não é alterado).
        """
        responses, items, changed = migrate_legacy(
            self._catalog, diagnostic.responses, diagnostic.items
        )
        if not changed:
            return diagnostic
        if diagnostic.is_open:
            saved = await self._repo.replace_items_and_responses(diagnostic.id, items, responses)
            if saved is not None:
                logger.info(
                    "maturity_diagnostic_items_migrated",
                    diagnostic_id=str(diagnostic.id),
                    items=len(items),
                )
                return saved
        return diagnostic.model_copy(update={"responses": responses, "items": items})

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
            return self._detail(await self._migrated(existing), company, agent), False

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
            # Chave: ``<pergunta>`` ou ``<pergunta>@<item>`` (perguntas por item).
            key = answer.question_id
            question_id, item_id = split_key(key)
            question = self._catalog.question(question_id)
            if question is None:
                errors[key] = "Pergunta desconhecida."
                continue
            step = self._catalog.step(question.step_id)
            if step is None or step.availability is not StepAvailability.AVAILABLE:
                errors[key] = "Etapa em manutenção."
                continue
            if question.read_only:
                errors[key] = "Dado cadastral não editável no diagnóstico."
                continue
            if question.per_item is not None:
                item = diagnostic.item(item_id) if item_id else None
                if item is None or item.kind != question.per_item:
                    errors[key] = (
                        "Item não encontrado (pode ter sido excluído)."
                        if item_id
                        else "Informe o item desta resposta."
                    )
                    continue
            elif item_id is not None:
                errors[key] = "Esta pergunta é respondida uma única vez por empresa."
                continue
            try:
                value = normalize_answer(question, answer.value)
            except InvalidAnswerError as exc:
                errors[key] = exc.message
                continue
            previous = diagnostic.responses.get(key)
            if (
                previous is not None
                and answer.edited_at is not None
                and _aware(answer.edited_at) < _aware(previous.updated_at)
            ):
                # Edição offline mais antiga que a gravada: mantém a do servidor.
                continue
            updates[key] = _build_response(question, value, previous, agent.id, now)

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
        evaluation = evaluate(
            self._catalog, diagnostic.answer_values(), items=diagnostic.items
        )
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

    # ------------------------------------------------- itens (produtos/resíduos)
    def _validate_item_fields(
        self,
        diagnostic: MaturityDiagnosticDocument,
        kind: ItemKind,
        name: str,
        *,
        exclude_id: str | None = None,
    ) -> str:
        clean = " ".join(name.split())
        if not clean:
            raise ValidationAppError(
                "Item name is required.",
                code="validation_error",
                details={"errors": {"name": "Informe o nome."}},
            )
        meta = self._catalog.item_kind(kind)
        label = meta.label.lower() if meta else "item"
        duplicate = any(
            item.kind == kind and item.id != exclude_id and item.name.casefold() == clean.casefold()
            for item in diagnostic.items
        )
        if duplicate:
            raise ValidationAppError(
                "An item with this name already exists.",
                code="item_duplicate_name",
                details={"errors": {"name": f"Já existe um {label} com esse nome."}},
            )
        return clean

    async def add_item(
        self, firebase_uid: str, diagnostic_id: UUID, payload: ItemCreate
    ) -> DiagnosticDetail:
        """Cadastra um produto (1.1) ou resíduo (1.7) — gera suas perguntas nos eixos."""
        agent, _, diagnostic, company = await self._load_owned(firebase_uid, diagnostic_id)
        self._ensure_editable(diagnostic)
        meta = self._catalog.item_kind(payload.kind)
        if meta is None:
            raise ValidationAppError("Invalid item kind.", code="invalid_item_kind")
        if len(items_of(diagnostic.items, payload.kind)) >= meta.max_items:
            raise ValidationAppError(
                "Maximum number of items reached.",
                code="item_limit_reached",
                details={"errors": {"name": f"Limite de {meta.max_items} itens atingido."}},
            )
        name = self._validate_item_fields(diagnostic, payload.kind, payload.name)
        description = (payload.description or "").strip() or None
        now = utcnow()
        item = DiagnosticItem(
            id=new_item_id(),
            kind=payload.kind,
            name=name,
            description=description,
            created_at=now,
            updated_at=now,
        )
        saved = await self._repo.add_item(diagnostic.id, item)
        if saved is None:
            raise ConflictError(
                "This diagnostic can no longer be edited.", code="diagnostic_closed"
            )
        saved = await self._refresh_evaluation(saved)
        return self._detail(saved, company, agent)

    async def update_item(
        self, firebase_uid: str, diagnostic_id: UUID, item_id: str, payload: ItemUpdate
    ) -> DiagnosticDetail:
        """Renomeia/descreve o item; as respostas continuam vinculadas pelo id."""
        agent, _, diagnostic, company = await self._load_owned(firebase_uid, diagnostic_id)
        self._ensure_editable(diagnostic)
        item = diagnostic.item(item_id)
        if item is None:
            raise NotFoundError("Item not found.", code="item_not_found")
        updated = item.model_copy()
        if "name" in payload.model_fields_set and payload.name is not None:
            updated.name = self._validate_item_fields(
                diagnostic, item.kind, payload.name, exclude_id=item.id
            )
        if "description" in payload.model_fields_set:
            updated.description = (payload.description or "").strip() or None
        updated.updated_at = utcnow()
        saved = await self._repo.update_item(diagnostic.id, updated)
        if saved is None:
            raise ConflictError(
                "This diagnostic can no longer be edited.", code="diagnostic_closed"
            )
        return self._detail(saved, company, agent)

    async def delete_item(
        self, firebase_uid: str, diagnostic_id: UUID, item_id: str
    ) -> DiagnosticDetail:
        """Exclui o item e todas as respostas vinculadas a ele (em todos os eixos)."""
        agent, _, diagnostic, company = await self._load_owned(firebase_uid, diagnostic_id)
        self._ensure_editable(diagnostic)
        if diagnostic.item(item_id) is None:
            raise NotFoundError("Item not found.", code="item_not_found")
        keys = [key for key in diagnostic.responses if split_key(key)[1] == item_id]
        saved = await self._repo.delete_item(diagnostic.id, item_id, keys)
        if saved is None:
            raise ConflictError(
                "This diagnostic can no longer be edited.", code="diagnostic_closed"
            )
        saved = await self._refresh_evaluation(saved)
        logger.info(
            "maturity_diagnostic_item_deleted",
            diagnostic_id=str(diagnostic.id),
            item_id=item_id,
            responses_removed=len(keys),
        )
        return self._detail(saved, company, agent)

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
        evaluation = evaluate(
            self._catalog, diagnostic.answer_values(), items=diagnostic.items
        )
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
        evaluation = evaluate(
            self._catalog, diagnostic.answer_values(), items=diagnostic.items
        )
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
    async def generate_report(
        self, firebase_uid: str, diagnostic_id: UUID
    ) -> tuple[MaturityReport, bool]:
        """Gera e persiste o relatório. Idempotente: reaproveita o já gerado.

        Retorna ``(relatório, gerado_agora)``.
        """
        agent, _, diagnostic, _ = await self._load_owned(firebase_uid, diagnostic_id)
        self._ensure_completed(diagnostic)
        if diagnostic.report:
            return MaturityReport.model_validate(diagnostic.report), False
        report = DiagnosticReportService(self._catalog).build(diagnostic, agent)
        now = utcnow()
        await self._repo.update(
            diagnostic.id,
            {"report": report.model_dump(mode="python"), "report_generated_at": now},
            only_open=False,
        )
        await self._record(
            AUDIT_REPORT_GENERATED,
            diagnostic,
            agent.id,
            after={
                "report_version": report.versions.report_version,
                "methodology_version": report.versions.methodology_version,
            },
        )
        return report, True

    async def get_report(self, firebase_uid: str, diagnostic_id: UUID) -> MaturityReport:
        _, _, diagnostic, _ = await self._load_owned(firebase_uid, diagnostic_id)
        self._ensure_completed(diagnostic)
        if not diagnostic.report:
            raise NotFoundError(
                "The report has not been generated yet.", code="report_not_generated"
            )
        return MaturityReport.model_validate(diagnostic.report)

    async def report_pdf(self, firebase_uid: str, diagnostic_id: UUID) -> tuple[bytes, str]:
        """PDF do relatório persistido. Retorna ``(bytes, nome_do_arquivo)``."""
        agent, _, diagnostic, _ = await self._load_owned(firebase_uid, diagnostic_id)
        self._ensure_completed(diagnostic)
        if not diagnostic.report:
            raise NotFoundError(
                "Generate the report before exporting the PDF.", code="report_not_generated"
            )
        report = MaturityReport.model_validate(diagnostic.report)
        pdf = render_report_pdf(report)
        await self._repo.update(
            diagnostic.id, {"pdf_generated_at": utcnow()}, only_open=False
        )
        await self._record(AUDIT_PDF_GENERATED, diagnostic, agent.id)
        return pdf, report_filename(report)

    @staticmethod
    def _ensure_completed(diagnostic: MaturityDiagnosticDocument) -> None:
        if diagnostic.status != DiagnosticStatus.COMPLETED:
            raise ConflictError(
                "The report is available after the diagnostic is completed.",
                code="diagnostic_not_completed",
            )

    # --------------------------------------------------------------- helpers
    def _evaluation_for(self, diagnostic: MaturityDiagnosticDocument) -> Evaluation:
        """Concluído: resultado congelado (versão do catálogo da época). Aberto: ao vivo."""
        if not diagnostic.is_open and diagnostic.result:
            return Evaluation.model_validate(diagnostic.result)
        return evaluate(self._catalog, diagnostic.answer_values(), items=diagnostic.items)

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
            report_generated_at=diagnostic.report_generated_at,
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
            items=[ItemOut.model_validate(item, from_attributes=True) for item in diagnostic.items],
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


__all__ = ["MaturityDiagnosticsService"]
