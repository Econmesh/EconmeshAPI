"""Diagnóstico de Maturidade Circular: catálogo, motor de regras e serviço."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from src.core.exceptions import ConflictError, ForbiddenError, ValidationAppError
from src.modules.auth.model import UserDocument
from src.modules.companies.model import CompanyAddress, CompanyDocument
from src.modules.dmc.model import DmcPortfolioLinkDocument, PortfolioSource
from src.modules.dmc.scope import PortfolioScope
from src.modules.maturity_diagnostics.catalog import (
    CATALOG,
    PILLAR_FM,
    PILLAR_PS,
    STEP_MATERIAL_FLOWS,
    StepAvailability,
)
from src.modules.maturity_diagnostics.engine import (
    InvalidAnswerError,
    StepStatus,
    evaluate,
    normalize_answer,
    visible_questions,
)
from src.modules.maturity_diagnostics.model import (
    DiagnosticResponse,
    DiagnosticStatus,
    MaturityDiagnosticDocument,
    ResponseSource,
)
from src.modules.maturity_diagnostics.schema import AnswerInput, SaveResponsesRequest
from src.modules.maturity_diagnostics.service import MaturityDiagnosticsService
from src.shared.constants.permissions import Permission, role_has_permission
from src.shared.constants.roles import Role

pytestmark = pytest.mark.unit

IDENTIFICATION_ANSWERS = {
    "q01": "Recicla Sul Ltda",
    "q02": "11222333000181",
    "q03": "Plásticos",
    "q04": "51_200",
    "q05": "Maria",
    "q06": "Gerente",
    "q07": "maria@reciclasul.com.br",
    "q08": "51999990000",
}
AXIS1_ANSWERS = {
    "q09": "Embalagens",
    "q10": "PEAD 10 t/mês",
    "q11": "nao",
    "q13": "parcialmente",
    "q14": "Aparas 2 t/mês",
    "q15": "nao_perigosos",
    "q16": "diaria",
    "q17": "nao",
    "q19": ["reciclagem", "venda"],
    "q28": "excelente",
    "q29": "classe_iia",
    "q31": "sazonal",
    "q37": "entre_2_5",
    "q43": "planilhas",
}


# ------------------------------------------------------------------- catálogo
def test_catalog_keeps_future_axes_in_maintenance_without_questions() -> None:
    steps = {s.id: s for s in CATALOG.steps}
    assert [s.order for s in CATALOG.steps] == [1, 2, 3, 4, 5]
    for step_id in ("axis_2_symbiosis", "axis_3_esg", "axis_4_economic"):
        assert steps[step_id].availability is StepAvailability.MAINTENANCE
        assert CATALOG.questions_for_step(step_id) == []


def test_axis_1_numbering_and_grouping() -> None:
    axis1 = [q for q in CATALOG.questions if q.step_id == STEP_MATERIAL_FLOWS]
    numbered = [q.code for q in axis1 if q.code is not None]
    assert numbered == [f"1.{i}" for i in range(1, 17)]
    identification = [q.code for q in CATALOG.questions if q.step_id == "identification"]
    assert identification == [f"ID.{i}" for i in range(1, 9)]
    sections = {q.id: q.section_id for q in axis1}
    assert sections["q37"] == "fm_production"
    assert {sections["q28"], sections["q29"], sections["q31"]} == {"fm_waste"}
    assert sections["q43"] == "fm_data"
    # Subitem condicional sem número próprio, logo após a pergunta de destino.
    ids = [q.id for q in axis1]
    assert ids.index("q19_other") == ids.index("q19") + 1
    assert next(q for q in axis1 if q.id == "q19_other").code is None
    # Seções do eixo existem e todas têm perguntas.
    axis_sections = [s.id for s in CATALOG.sections if s.step_id == STEP_MATERIAL_FLOWS]
    assert axis_sections == ["fm_production", "fm_waste", "fm_data"]


def test_q31_is_shown_in_axis_1_but_scored_in_symbiosis_pillar() -> None:
    q31 = CATALOG.question("q31")
    assert q31 is not None
    assert q31.step_id == STEP_MATERIAL_FLOWS
    assert q31.pillar_id == PILLAR_PS
    assert (q31.pillar_weight, q31.ems_weight) == (40, 10)


def test_scored_questions_match_specification() -> None:
    expected = {
        "q28": ({"excelente": 40, "parcial": 15, "nulo": 0}, PILLAR_FM, 40, 12),
        "q29": ({"classe_iib": 40, "classe_iia": 25, "classe_i": 10}, PILLAR_FM, 40, 12),
        "q31": ({"continuo": 40, "sazonal": 15}, PILLAR_PS, 40, 10),
        "q37": ({"menos_2": 10, "entre_2_5": 5, "acima_5": 0}, PILLAR_FM, 10, 3),
        "q43": ({"erp": 10, "planilhas": 5, "fisico": 0}, PILLAR_FM, 10, 3),
    }
    scored = {q.id: q for q in CATALOG.questions if q.scored}
    assert set(scored) == set(expected)
    for qid, (points, pillar, pillar_weight, ems_weight) in expected.items():
        question = scored[qid]
        assert {o.value: o.points for o in question.options} == points
        assert question.pillar_id == pillar
        assert question.pillar_weight == pillar_weight
        assert question.ems_weight == ems_weight


def test_dmc_agent_has_diagnostics_permission() -> None:
    assert role_has_permission(Role.DMC_AGENT, Permission.DIAGNOSTICS_MANAGE)
    assert not role_has_permission(Role.VIEWER, Permission.DIAGNOSTICS_MANAGE)


# ---------------------------------------------------------------- condicionais
def test_conditional_questions() -> None:
    ids = lambda values: {q.id for q in visible_questions(CATALOG, values)}  # noqa: E731
    assert "q12" not in ids({"q11": "nao"})
    assert "q12" in ids({"q11": "sim"})
    assert "q18" not in ids({"q17": "nao"})
    assert "q18" in ids({"q17": "sim"})
    assert "q18" in ids({"q17": "as_vezes"})
    assert "q19_other" not in ids({"q19": ["aterro"]})
    assert "q19_other" in ids({"q19": ["aterro", "outro"]})


def test_hidden_answers_do_not_count_or_block_completion() -> None:
    values = {**IDENTIFICATION_ANSWERS, **AXIS1_ANSWERS, "q12": "resposta antiga"}
    evaluation = evaluate(CATALOG, values)
    assert evaluation.complete is True
    assert evaluation.progress == 100
    axis1 = next(s for s in evaluation.steps if s.step_id == STEP_MATERIAL_FLOWS)
    assert axis1.not_applicable == 3  # q12, q18, q19_other
    assert "q12" not in evaluation.visible_question_ids


def test_showing_conditional_question_makes_it_required() -> None:
    values = {**IDENTIFICATION_ANSWERS, **AXIS1_ANSWERS, "q17": "sim"}
    evaluation = evaluate(CATALOG, values)
    axis1 = next(s for s in evaluation.steps if s.step_id == STEP_MATERIAL_FLOWS)
    assert axis1.missing_required == ["q18"]
    assert axis1.status is StepStatus.IN_PROGRESS
    assert evaluation.complete is False


# ------------------------------------------------------------------ pontuação
def test_scoring_by_pillar_and_ems() -> None:
    evaluation = evaluate(CATALOG, {**IDENTIFICATION_ANSWERS, **AXIS1_ANSWERS})
    pillars = {p.pillar_id: p for p in evaluation.pillars}
    # FM: 40 (excelente) + 25 (IIA) + 5 (2–5%) + 5 (planilhas)
    assert (pillars[PILLAR_FM].points, pillars[PILLAR_FM].max_points) == (75, 100)
    # PS: Q31 sazonal = 15 de 40 (perguntas dos demais eixos ainda não existem)
    assert (pillars[PILLAR_PS].points, pillars[PILLAR_PS].max_points) == (15, 40)
    # EMS: 12 + 12*25/40 + 10*15/40 + 3*5/10 + 3*5/10
    assert evaluation.ems.points == pytest.approx(12 + 7.5 + 3.75 + 1.5 + 1.5)
    assert evaluation.ems.max_available == 40


def test_maintenance_steps_do_not_affect_progress() -> None:
    evaluation = evaluate(CATALOG, {})
    statuses = {s.step_id: s.status for s in evaluation.steps}
    assert statuses["axis_2_symbiosis"] is StepStatus.MAINTENANCE
    assert evaluation.required_total == 8 + 14


# ------------------------------------------------------------------- validação
def test_normalize_answer_rejects_invalid_values() -> None:
    q04 = CATALOG.question("q04")
    q19 = CATALOG.question("q19")
    q07 = CATALOG.question("q07")
    assert q04 is not None and q19 is not None and q07 is not None
    with pytest.raises(InvalidAnswerError):
        normalize_answer(q04, "mil")
    with pytest.raises(InvalidAnswerError):
        normalize_answer(q19, ["lixao"])
    with pytest.raises(InvalidAnswerError):
        normalize_answer(q07, "nao-e-email")
    assert normalize_answer(q19, ["venda", "venda", "outro"]) == ["venda", "outro"]
    assert normalize_answer(q04, "  ") is None


# --------------------------------------------------------------------- serviço
def _company(**overrides: object) -> CompanyDocument:
    data: dict[str, object] = {
        "owner_user_id": uuid4(),
        "legal_name": "Recicla Sul Ltda",
        "trade_name": "Recicla Sul",
        "tax_id": "11222333000181",
        "email": "contato@reciclasul.com.br",
        "phone": "51999990000",
        "legal_representative": "Maria",
        "sector": "Plásticos",
        "address": CompanyAddress(city="Porto Alegre", state="RS"),
    }
    data.update(overrides)
    return CompanyDocument(**data)  # type: ignore[arg-type]


def _service(company: CompanyDocument, *, agent: UserDocument | None = None):
    agent = agent or UserDocument(
        firebase_uid="agent-uid", email="agente@econmesh.com", name="Ana", role=Role.DMC_AGENT
    )
    auth = AsyncMock()
    auth.get_by_firebase_uid = AsyncMock(return_value=agent)
    auth.get_by_id = AsyncMock(return_value=None)
    users = AsyncMock()
    users.get_by_user = AsyncMock(return_value=None)
    scope_service = AsyncMock()
    scope_service.for_agent = AsyncMock(
        return_value=PortfolioScope(
            agent_user_id=agent.id,
            links=[
                DmcPortfolioLinkDocument(
                    agent_user_id=agent.id,
                    company_id=company.id,
                    source=PortfolioSource.ASSIGNED,
                )
            ],
            companies={company.id: company},
        )
    )
    repo = AsyncMock()
    repo.get_open_for_company = AsyncMock(return_value=None)
    repo.create = AsyncMock(side_effect=lambda doc: doc)
    audit = AsyncMock()
    service = MaturityDiagnosticsService(
        repository=repo, auth=auth, users=users, scope=scope_service, audit=audit
    )
    return service, repo, agent


async def test_create_prefills_identification_from_registry() -> None:
    company = _company()
    service, repo, agent = _service(company)

    detail, created = await service.create("agent-uid", company.id)

    assert created is True
    doc: MaturityDiagnosticDocument = repo.create.await_args.args[0]
    assert doc.agent_user_id == agent.id
    assert doc.company_id == company.id
    assert doc.status == DiagnosticStatus.NOT_STARTED
    assert doc.responses["q01"].value == "Recicla Sul Ltda"
    assert doc.responses["q02"].value == "11222333000181"
    assert doc.responses["q03"].value == "Plásticos"
    assert doc.responses["q05"].value == "Maria"
    assert doc.responses["q01"].source == ResponseSource.REGISTRY
    assert "q04" not in doc.responses  # não existe no cadastro
    assert detail.current_step == "identification"


async def test_create_rejects_company_outside_portfolio() -> None:
    service, repo, _ = _service(_company())
    with pytest.raises(ForbiddenError):
        await service.create("agent-uid", uuid4())
    repo.create.assert_not_awaited()


async def test_create_resumes_open_diagnostic_of_same_agent() -> None:
    company = _company()
    service, repo, agent = _service(company)
    existing = MaturityDiagnosticDocument(
        company_id=company.id,
        agent_user_id=agent.id,
        catalog_version=CATALOG.version,
        company_snapshot={"legal_name": company.legal_name, "tax_id": company.tax_id},
    )
    repo.get_open_for_company = AsyncMock(return_value=existing)

    detail, created = await service.create("agent-uid", company.id)
    assert created is False
    assert detail.id == existing.id

    existing.agent_user_id = uuid4()
    with pytest.raises(ConflictError) as exc:
        await service.create("agent-uid", company.id)
    assert exc.value.code == "diagnostic_open_by_other_agent"


def _open_diagnostic(company: CompanyDocument, agent: UserDocument, **values: object):
    return MaturityDiagnosticDocument(
        company_id=company.id,
        agent_user_id=agent.id,
        catalog_version=CATALOG.version,
        company_snapshot={"legal_name": company.legal_name, "tax_id": company.tax_id},
        responses={
            qid: DiagnosticResponse(value=value)  # type: ignore[arg-type]
            for qid, value in values.items()
        },
    )


async def test_save_responses_validates_and_scores() -> None:
    company = _company()
    service, repo, agent = _service(company)
    diagnostic = _open_diagnostic(company, agent)
    repo.get = AsyncMock(return_value=diagnostic)

    async def _save(diagnostic_id, responses, *, current_step=None):
        diagnostic.responses.update(responses)
        return diagnostic

    repo.save_responses = AsyncMock(side_effect=_save)
    repo.update = AsyncMock(return_value=diagnostic)

    await service.save_responses(
        "agent-uid",
        diagnostic.id,
        SaveResponsesRequest(
            answers=[
                AnswerInput(question_id="q28", value="parcial"),
                AnswerInput(question_id="q19", value=["outro"]),
            ],
            current_step=STEP_MATERIAL_FLOWS,
        ),
    )
    saved = repo.save_responses.await_args.args[1]
    assert saved["q28"].score == 15
    assert saved["q19"].value == ["outro"]
    patch = repo.update.await_args.args[1]
    assert patch["status"] == DiagnosticStatus.IN_PROGRESS.value

    with pytest.raises(ValidationAppError) as exc:
        await service.save_responses(
            "agent-uid",
            diagnostic.id,
            SaveResponsesRequest(
                answers=[
                    AnswerInput(question_id="q28", value="otimo"),
                    AnswerInput(question_id="q01", value="Outro nome"),
                    AnswerInput(question_id="q99", value="x"),
                ]
            ),
        )
    assert set(exc.value.details["errors"]) == {"q28", "q01", "q99"}


async def test_other_agent_cannot_access_diagnostic() -> None:
    company = _company()
    service, repo, _ = _service(company)
    diagnostic = _open_diagnostic(company, UserDocument(firebase_uid="x", email="x@x.com"))
    repo.get = AsyncMock(return_value=diagnostic)
    with pytest.raises(ForbiddenError):
        await service.get("agent-uid", diagnostic.id)


async def test_complete_requires_all_available_steps() -> None:
    company = _company()
    service, repo, agent = _service(company)
    incomplete = _open_diagnostic(company, agent, **IDENTIFICATION_ANSWERS)
    repo.get = AsyncMock(return_value=incomplete)
    with pytest.raises(ValidationAppError) as exc:
        await service.complete("agent-uid", incomplete.id)
    assert exc.value.code == "diagnostic_incomplete"

    complete = _open_diagnostic(company, agent, **IDENTIFICATION_ANSWERS, **AXIS1_ANSWERS)
    repo.get = AsyncMock(return_value=complete)
    repo.update = AsyncMock(
        side_effect=lambda _id, patch: complete.model_copy(
            update={"status": DiagnosticStatus.COMPLETED, "is_open": False}
        )
    )
    detail = await service.complete("agent-uid", complete.id)
    patch = repo.update.await_args.args[1]
    assert patch["status"] == DiagnosticStatus.COMPLETED.value
    assert patch["is_open"] is False
    assert patch["result"]["ems"]["points"] == pytest.approx(26.25)
    assert detail.can_edit is False


async def test_validate_step_reports_missing_required() -> None:
    company = _company()
    service, repo, agent = _service(company)
    diagnostic = _open_diagnostic(company, agent, q01="Recicla Sul Ltda")
    repo.get = AsyncMock(return_value=diagnostic)
    with pytest.raises(ValidationAppError) as exc:
        await service.validate_step("agent-uid", diagnostic.id, "identification")
    assert exc.value.code == "step_incomplete"
    assert "q04" in exc.value.details["missing"]

    with pytest.raises(ValidationAppError):
        await service.validate_step("agent-uid", diagnostic.id, "axis_2_symbiosis")


async def test_routes_require_dmc_agent(app: FastAPI, client: AsyncClient) -> None:
    from src.shared.dependencies.auth import CurrentUser, get_current_user

    async def _admin() -> CurrentUser:
        return CurrentUser(uid="admin", role=Role.ADMIN)

    app.dependency_overrides[get_current_user] = _admin
    try:
        response = await client.get(
            "/api/v1/dmc/diagnostics/catalog", headers={"Authorization": "Bearer x"}
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


async def test_catalog_route_for_agent(app: FastAPI, client: AsyncClient) -> None:
    from src.shared.dependencies.auth import CurrentUser, get_current_user

    async def _agent() -> CurrentUser:
        return CurrentUser(uid="agent", role=Role.DMC_AGENT)

    app.dependency_overrides[get_current_user] = _agent
    try:
        response = await client.get(
            "/api/v1/dmc/diagnostics/catalog", headers={"Authorization": "Bearer x"}
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body["steps"]) == 5
        assert any(q["id"] == "q31" and q["pillar_id"] == "ps" for q in body["questions"])
    finally:
        app.dependency_overrides.clear()
