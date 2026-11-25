"""DMC — produtos e resíduos dinâmicos: cadastro, respostas por item, eixos e relatório.

Cobre os critérios de aceitação da evolução do formulário (múltiplos produtos
na 1.1, múltiplos resíduos na 1.7, Eixo 2 por produto, Eixo 4 por resíduo,
1.8 por resíduo refletida no Eixo 3, consistência e relatório).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from src.core.exceptions import ConflictError, NotFoundError, ValidationAppError
from src.modules.maturity_diagnostics.catalog import CATALOG, PILLAR_PS, ItemKind
from src.modules.maturity_diagnostics.engine import evaluate, response_key, visible_instances
from src.modules.maturity_diagnostics.items import migrate_legacy
from src.modules.maturity_diagnostics.model import (
    DiagnosticItem,
    DiagnosticResponse,
    MaturityDiagnosticDocument,
)
from src.modules.maturity_diagnostics.report_pdf import render_report_pdf
from src.modules.maturity_diagnostics.schema import (
    AnswerInput,
    ItemCreate,
    ItemUpdate,
    SaveResponsesRequest,
)
from src.tests.modules.maturity_diagnostics.test_maturity_diagnostics import (
    AXIS3_ANSWERS,
    IDENTIFICATION_ANSWERS,
    LEGACY_ALL_ANSWERS,
    _company,
    _service,
)

pytestmark = pytest.mark.unit

UID = "agent-uid"


class FakeRepository:
    """Repositório em memória com a mesma semântica do Mongo (cópias a cada leitura)."""

    def __init__(self) -> None:
        self.docs: dict[UUID, MaturityDiagnosticDocument] = {}

    def _copy(self, doc: MaturityDiagnosticDocument | None) -> MaturityDiagnosticDocument | None:
        return doc.model_copy(deep=True) if doc is not None else None

    def _open(self, diagnostic_id: UUID) -> MaturityDiagnosticDocument | None:
        doc = self.docs.get(diagnostic_id)
        return doc if doc is not None and doc.is_open else None

    async def get(self, diagnostic_id: UUID) -> MaturityDiagnosticDocument | None:
        return self._copy(self.docs.get(diagnostic_id))

    async def get_open_for_company(self, company_id: UUID) -> MaturityDiagnosticDocument | None:
        return self._copy(
            next((d for d in self.docs.values() if d.company_id == company_id and d.is_open), None)
        )

    async def create(self, doc: MaturityDiagnosticDocument) -> MaturityDiagnosticDocument:
        self.docs[doc.id] = doc.model_copy(deep=True)
        return doc

    async def save_responses(self, diagnostic_id, responses, *, current_step=None):
        doc = self._open(diagnostic_id)
        if doc is None:
            return None
        doc.responses.update({k: v.model_copy() for k, v in responses.items()})
        if current_step is not None:
            doc.current_step = current_step
        return self._copy(doc)

    async def update(self, diagnostic_id, patch: dict[str, Any], *, only_open: bool = True):
        doc = self._open(diagnostic_id) if only_open else self.docs.get(diagnostic_id)
        if doc is None:
            return None
        data = {**doc.model_dump(mode="python"), **patch}
        self.docs[diagnostic_id] = MaturityDiagnosticDocument.model_validate(data)
        return self._copy(self.docs[diagnostic_id])

    async def add_item(self, diagnostic_id, item: DiagnosticItem):
        doc = self._open(diagnostic_id)
        if doc is None:
            return None
        doc.items.append(item.model_copy())
        return self._copy(doc)

    async def update_item(self, diagnostic_id, item: DiagnosticItem):
        doc = self._open(diagnostic_id)
        if doc is None:
            return None
        doc.items = [item.model_copy() if i.id == item.id else i for i in doc.items]
        return self._copy(doc)

    async def delete_item(self, diagnostic_id, item_id: str, response_keys: list[str]):
        doc = self._open(diagnostic_id)
        if doc is None:
            return None
        doc.items = [i for i in doc.items if i.id != item_id]
        for key in response_keys:
            doc.responses.pop(key, None)
        return self._copy(doc)

    async def replace_items_and_responses(self, diagnostic_id, items, responses):
        doc = self._open(diagnostic_id)
        if doc is None or doc.items:
            return None
        doc.items = [i.model_copy() for i in items]
        doc.responses = dict(responses)
        return self._copy(doc)


async def _setup():
    company = _company()
    service, _, agent = _service(company)
    repo = FakeRepository()
    service._repo = repo  # type: ignore[attr-defined]
    detail, _ = await service.create(UID, company.id)
    return service, repo, detail.id


async def _add(service, diagnostic_id, kind: ItemKind, name: str, description: str | None = None):
    detail = await service.add_item(
        UID, diagnostic_id, ItemCreate(kind=kind, name=name, description=description)
    )
    return detail, next(i for i in detail.items if i.name == name)


async def _answer(service, diagnostic_id, answers: dict[str, object]):
    return await service.save_responses(
        UID,
        diagnostic_id,
        SaveResponsesRequest(
            answers=[AnswerInput(question_id=k, value=v) for k, v in answers.items()]  # type: ignore[arg-type]
        ),
    )


def _keys(detail, question_id: str) -> list[str]:
    return [
        key
        for key in detail.evaluation.visible_question_ids
        if key == question_id or key.startswith(f"{question_id}@")
    ]


# --------------------------------------------------------------- cenários 1–4
async def test_single_product_generates_its_questions() -> None:
    service, _, diag_id = await _setup()
    detail, product = await _add(service, diag_id, ItemKind.PRODUCT, "Embalagens")
    for qid in ("q10", "q11", "q13", "q37", "ps_q25", "ps_q26", "ps_q28"):
        assert _keys(detail, qid) == [response_key(qid, product.id)], qid
    # Cadastro 1.1 atendido; perguntas do produto passam a ser obrigatórias.
    axis1 = next(s for s in detail.evaluation.steps if s.step_id == "axis_1_material_flows")
    assert "q09" not in axis1.missing_required
    assert response_key("q10", product.id) in axis1.missing_required


async def test_three_products_each_with_own_axis_2_section_and_independent_answers() -> None:
    service, _, diag_id = await _setup()
    products = []
    for name in ("Produto A", "Produto B", "Produto C"):
        _, item = await _add(service, diag_id, ItemKind.PRODUCT, name)
        products.append(item)
    detail = await _answer(
        service,
        diag_id,
        {
            response_key("ps_q28", products[0].id): "alta",
            response_key("ps_q28", products[1].id): "baixa",
            response_key("ps_q26", products[2].id): "sim",
            response_key("ps_q27", products[2].id): "Venda de aparas",
        },
    )
    assert len(_keys(detail, "ps_q25")) == 3
    responses = detail.responses
    assert responses[response_key("ps_q28", products[0].id)].value == "alta"
    assert responses[response_key("ps_q28", products[1].id)].value == "baixa"
    assert response_key("ps_q28", products[2].id) not in responses
    # Condicional 2.3 só aparece para o produto que respondeu "Sim" em 2.2.
    assert _keys(detail, "ps_q27") == [response_key("ps_q27", products[2].id)]
    # Capacidade e Interesse continuam uma única vez por empresa.
    for qid in ("ps_q29", "ps_q31", "ps_q32", "ps_q33", "ps_q34"):
        assert _keys(detail, qid) == [qid]
    # Pontuação: média dos produtos respondidos (60 e 0) e pior caso.
    score = next(s for s in detail.evaluation.question_scores if s.question_id == "ps_q28")
    assert (score.points, score.worst_points, score.answered_items, score.total_items) == (
        30,
        0,
        2,
        3,
    )


# --------------------------------------------------------------- cenários 5–7
async def test_multiple_wastes_axis_4_and_axis_3_reflection() -> None:
    service, _, diag_id = await _setup()
    _, w1 = await _add(service, diag_id, ItemKind.WASTE, "Aparas", "2 t/mês")
    _, w2 = await _add(service, diag_id, ItemKind.WASTE, "Lodo")
    detail = await _answer(
        service,
        diag_id,
        {
            response_key("q15", w1.id): "nao_perigosos",
            response_key("q15", w2.id): "perigosos",
            response_key("ve_q44", w1.id): "alto",
            response_key("ve_q44", w2.id): "baixo",
        },
    )
    for qid in ("q15", "q29", "q28", "q31", "ve_q44", "ve_q45", "ve_q47"):
        assert len(_keys(detail, qid)) == 2, qid
    # Eixo 3: Licenciamento continua geral (3.1/3.2) e reflete a 1.8 por resíduo.
    assert _keys(detail, "esg_q35") == ["esg_q35"]
    section = next(s for s in CATALOG.sections if s.id == "esg_licensing")
    assert section.item_reference is not None
    assert section.item_reference.question_ids == ("q15",)
    assert detail.responses[response_key("q15", w2.id)].value == "perigosos"
    # Alterar a 1.8 de um resíduo não interfere no outro.
    detail = await _answer(service, diag_id, {response_key("q15", w1.id): "ambos"})
    assert detail.responses[response_key("q15", w1.id)].value == "ambos"
    assert detail.responses[response_key("q15", w2.id)].value == "perigosos"


# ---------------------------------------------------------------- cenário 8
async def test_edit_and_delete_items_keep_data_consistent() -> None:
    service, repo, diag_id = await _setup()
    _, product = await _add(service, diag_id, ItemKind.PRODUCT, "Produto A")
    _, other = await _add(service, diag_id, ItemKind.PRODUCT, "Produto B")
    _, waste = await _add(service, diag_id, ItemKind.WASTE, "Aparas")
    await _answer(
        service,
        diag_id,
        {
            response_key("q10", product.id): "PEAD",
            response_key("ps_q28", product.id): "alta",
            response_key("q10", other.id): "PP",
            response_key("ve_q44", waste.id): "medio",
        },
    )

    # Renomear: as respostas continuam vinculadas pelo id.
    detail = await service.update_item(
        UID, diag_id, product.id, ItemUpdate(name="Produto A1", description="Linha 1")
    )
    renamed = next(i for i in detail.items if i.id == product.id)
    assert (renamed.name, renamed.description) == ("Produto A1", "Linha 1")
    assert detail.responses[response_key("ps_q28", product.id)].value == "alta"

    # Nome duplicado (sem diferenciar maiúsculas) é recusado.
    with pytest.raises(ValidationAppError) as exc:
        await service.update_item(UID, diag_id, other.id, ItemUpdate(name="produto a1"))
    assert exc.value.code == "item_duplicate_name"
    with pytest.raises(ValidationAppError):
        await service.add_item(UID, diag_id, ItemCreate(kind=ItemKind.PRODUCT, name="PRODUTO B"))
    # Mesmo nome em tipos diferentes é permitido.
    await service.add_item(UID, diag_id, ItemCreate(kind=ItemKind.WASTE, name="Produto B"))

    # Excluir: remove o item e todas as respostas dele, sem afetar os demais.
    detail = await service.delete_item(UID, diag_id, product.id)
    assert all(i.id != product.id for i in detail.items)
    assert not [k for k in detail.responses if k.endswith(f"@{product.id}")]
    assert detail.responses[response_key("q10", other.id)].value == "PP"
    assert detail.responses[response_key("ve_q44", waste.id)].value == "medio"
    assert not [k for k in detail.evaluation.visible_question_ids if product.id in k]
    stored = repo.docs[diag_id]
    assert not [k for k in stored.responses if product.id in k]

    # Respostas para item excluído são recusadas (sem registros órfãos).
    with pytest.raises(ValidationAppError) as exc:
        await _answer(service, diag_id, {response_key("q10", product.id): "volta"})
    assert response_key("q10", product.id) in exc.value.details["errors"]
    with pytest.raises(NotFoundError):
        await service.delete_item(UID, diag_id, product.id)


# --------------------------------------------------------------- cenários 9–10
async def _fill_complete(service, diag_id) -> dict[str, DiagnosticItem]:
    _, a = await _add(service, diag_id, ItemKind.PRODUCT, "Produto A")
    _, b = await _add(service, diag_id, ItemKind.PRODUCT, "Produto B")
    _, w1 = await _add(service, diag_id, ItemKind.WASTE, "Aparas", "2 t/mês")
    _, w2 = await _add(service, diag_id, ItemKind.WASTE, "Lodo", "500 kg/mês")
    answers: dict[str, object] = {
        "q04": "51_200",
        "q06": "Gerente",
        "q43": "planilhas",
        "ps_q29": "nao",
        "ps_q31": "talvez",
        "ps_q32": ["simbiose_industrial"],
        "ps_q33": "nao",
        **AXIS3_ANSWERS,
        "ve_q46": "apenas_custo_zero",
    }
    for product, (loss, demand) in ((a, ("menos_2", "alta")), (b, ("acima_5", "baixa"))):
        answers |= {
            response_key("q10", product.id): "PEAD",
            response_key("q11", product.id): "nao",
            response_key("q13", product.id): "nao",
            response_key("q37", product.id): loss,
            response_key("ps_q25", product.id): "coprocessamento_reciclagem",
            response_key("ps_q26", product.id): "nao",
            response_key("ps_q28", product.id): demand,
        }
    for waste, (klass, cost) in ((w1, ("nao_perigosos", "alto")), (w2, ("perigosos", "baixo"))):
        answers |= {
            response_key("q15", waste.id): klass,
            response_key("q16", waste.id): "diaria",
            response_key("q17", waste.id): "nao",
            response_key("q19", waste.id): ["reciclagem"],
            response_key("q28", waste.id): "excelente",
            response_key("q29", waste.id): "classe_iia",
            response_key("q31", waste.id): "continuo",
            response_key("ve_q44", waste.id): cost,
            response_key("ve_q45", waste.id): "ate_10000",
        }
    await _answer(service, diag_id, answers)
    return {"a": a, "b": b, "w1": w1, "w2": w2}


async def test_save_exit_resume_complete_and_report() -> None:
    service, repo, diag_id = await _setup()
    items = await _fill_complete(service, diag_id)

    # "Sair e voltar": nova leitura traz itens e respostas persistidos.
    resumed = await service.get(UID, diag_id)
    assert [i.name for i in resumed.items] == ["Produto A", "Produto B", "Aparas", "Lodo"]
    assert resumed.evaluation.complete is True
    # Idempotente: reenviar a mesma resposta não duplica chaves.
    before = len(resumed.responses)
    await _answer(service, diag_id, {response_key("q37", items["a"].id): "menos_2"})
    assert len((await service.get(UID, diag_id)).responses) == before

    done = await service.complete(UID, diag_id)
    assert done.can_edit is False
    with pytest.raises(ConflictError):
        await service.add_item(UID, diag_id, ItemCreate(kind=ItemKind.PRODUCT, name="Novo"))

    report, created = await service.generate_report(UID, diag_id)
    assert created is True
    assert [p.name for p in report.products] == ["Produto A", "Produto B"]
    assert [w.name for w in report.wastes] == ["Aparas", "Lodo"]
    lodo = report.wastes[1]
    assert lodo.description == "500 kg/mês"
    titles = [s.title for s in lodo.sections]
    assert any("Mapeamento de resíduos" in t for t in titles)
    assert any("Licenciamento e rastreabilidade" in t for t in titles)
    assert any("Custos de gestão de resíduos" in t for t in titles)
    licensing = next(s for s in lodo.sections if "Licenciamento" in s.title)
    assert [a.answer for a in licensing.answers] == ["Perigosos"]
    costs = next(s for s in lodo.sections if "Custos" in s.title)
    assert costs.answers[0].answer == "Baixo"
    product_b = report.products[1]
    destination = next(s for s in product_b.sections if "Destinação e mercado" in s.title)
    assert {a.answer for a in destination.answers} >= {"Baixa"}
    # Nada de respostas atribuídas ao item errado.
    for entry in report.products + report.wastes:
        for section in entry.sections:
            assert section.item_id == entry.id
            assert all(a.question_id.endswith(f"@{entry.id}") for a in section.answers)

    # Indicadores por item: média no score oficial, pior caso informado.
    indicators = {i.question_id: i for i in report.indicators}
    demand = indicators["ps_q28"]
    assert demand.per_item is True
    assert [(r.item_name, r.points) for r in demand.items] == [("Produto A", 60), ("Produto B", 0)]
    assert (demand.points, demand.worst_points) == (30, 0)
    assert "Pior caso (Produto B)" in (demand.interpretation or "")
    ps = next(p for p in report.pillars if p.pillar_id == PILLAR_PS)
    assert ps.points == pytest.approx(70)  # 1.15 contínuo 40 + 2.4 média 30
    assert ps.worst_points == pytest.approx(40)
    assert report.summary.worst_case_score is not None
    assert report.summary.worst_case_score < report.summary.overall_score
    # Seções por item também aparecem no resumo das respostas por etapa.
    axis2 = next(step for step in report.answers if step.step_id == "axis_2_symbiosis")
    section_titles = [s.title for s in axis2.sections]
    assert "Destinação e mercado de resíduos — Produto A" in section_titles
    assert "Destinação e mercado de resíduos — Produto B" in section_titles
    assert section_titles.count("Capacidade e infraestrutura compartilhável") == 1
    # Contexto por item identifica o resíduo perigoso.
    hazardous = next(f for f in report.attention_points if "perigosos" in f.title.lower())
    assert "Lodo" in hazardous.text and "Aparas" not in hazardous.text

    pdf = render_report_pdf(report)
    import fitz

    text = "".join(page.get_text() for page in fitz.open(stream=pdf, filetype="pdf"))
    assert "Produtos e Resíduos" in text
    assert "Lodo" in text and "Produto B" in text


# ------------------------------------------------------------ compatibilidade
def test_legacy_responses_are_migrated_without_loss() -> None:
    responses = {k: DiagnosticResponse(value=v) for k, v in LEGACY_ALL_ANSWERS.items()}  # type: ignore[arg-type]
    migrated, items, changed = migrate_legacy(CATALOG, responses, [])
    assert changed is True
    product = next(i for i in items if i.kind is ItemKind.PRODUCT)
    waste = next(i for i in items if i.kind is ItemKind.WASTE)
    assert (product.name, waste.name, waste.description) == (
        "Embalagens",
        "Aparas 2 t/mês",
        "Aparas 2 t/mês",
    )
    assert migrated[response_key("q28", waste.id)].value == "excelente"
    assert migrated[response_key("ps_q28", product.id)].value == "media"
    assert "q28" not in migrated and "q09" not in migrated and "q14" not in migrated
    assert migrated["esg_q35"].value == "ativa_regularizada"
    values = {k: r.value for k, r in migrated.items()}
    evaluation = evaluate(CATALOG, values, items=items)
    assert evaluation.complete is True
    assert evaluation.ems.points == pytest.approx(65.75)  # mesmo score do formato anterior
    # Já migrado: nada muda.
    assert migrate_legacy(CATALOG, migrated, items)[2] is False


async def test_open_legacy_diagnostic_is_migrated_and_persisted() -> None:
    service, repo, diag_id = await _setup()
    legacy = repo.docs[diag_id]
    legacy.responses = {k: DiagnosticResponse(value=v) for k, v in LEGACY_ALL_ANSWERS.items()}  # type: ignore[arg-type]
    detail = await service.get(UID, diag_id)
    assert len(detail.items) == 2
    assert len(repo.docs[diag_id].items) == 2  # persistido
    assert detail.evaluation.complete is True
    # Leitura seguinte não cria itens novamente.
    again = await service.get(UID, diag_id)
    assert [i.id for i in again.items] == [i.id for i in detail.items]


def test_visible_instances_follow_item_scope() -> None:
    a = DiagnosticItem(id="a", kind=ItemKind.PRODUCT, name="A")
    b = DiagnosticItem(id="b", kind=ItemKind.PRODUCT, name="B")
    keys = {
        i.key
        for i in visible_instances(CATALOG, {response_key("q11", "a"): "sim"}, [a, b])
    }
    assert response_key("q12", "a") in keys
    assert response_key("q12", "b") not in keys
    assert {"q09", "q14", "q43"} <= keys
    assert IDENTIFICATION_ANSWERS  # importado para manter o conjunto de dados único
