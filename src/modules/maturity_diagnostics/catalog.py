"""Catálogo estruturado do Diagnóstico de Maturidade Circular (DMC).

Toda a definição do formulário vive aqui — etapas, seções, perguntas, opções,
pontuações, pilares de cálculo, pesos e regras condicionais. O frontend
renderiza a partir deste catálogo (``GET /dmc/diagnostics/catalog``) e o
backend valida/pontua a partir dele; nenhuma regra fica espalhada na UI.

Conceitos separados de propósito:

* **Etapa / eixo do formulário** (``step_id``): onde a pergunta aparece.
* **Pilar de cálculo** (``pillar_id``): onde a pontuação é contabilizada.

Ex.: a Q31 aparece no Eixo 1 (Fluxos de Materiais), mas pontua no Pilar 2
(Potencial de Simbiose).

Para ativar os Eixos 2–4 basta incluir suas perguntas e trocar a
``availability`` da etapa para ``AVAILABLE`` — progresso, conclusão e
pontuação passam a considerá-los automaticamente.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

CATALOG_VERSION = "2026-10.2"


class StepKind(StrEnum):
    IDENTIFICATION = "identification"
    AXIS = "axis"


class StepAvailability(StrEnum):
    AVAILABLE = "available"
    MAINTENANCE = "maintenance"


class QuestionType(StrEnum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    EMAIL = "email"
    PHONE = "phone"
    TAX_ID = "tax_id"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"


class ConditionOperator(StrEnum):
    #: resposta (seleção única) é um dos ``values``
    IN = "in"
    #: resposta (múltipla seleção) contém algum dos ``values``
    CONTAINS_ANY = "contains_any"


class RegistryField(StrEnum):
    """Campos do cadastro usados para pré-preencher a identificação."""

    LEGAL_NAME = "legal_name"
    TAX_ID = "tax_id"
    SECTOR = "sector"
    CONTACT_NAME = "contact_name"
    CONTACT_JOB_TITLE = "contact_job_title"
    EMAIL = "email"
    PHONE = "phone"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Pillar(_Frozen):
    id: str
    code: str
    name: str


class Option(_Frozen):
    value: str
    label: str
    points: int | None = None


class Condition(_Frozen):
    question_id: str
    operator: ConditionOperator
    values: tuple[str, ...]


class Question(_Frozen):
    id: str
    #: Numeração exibida no formulário (reinicia por etapa: ``ID.1``, ``1.1``, ``2.1``…).
    code: str | None = Field(default=None, description="Numeração exibida.")
    #: Número da pergunta no roteiro original do DMC (rastreabilidade).
    number: int | None = Field(default=None, description="Número de referência no roteiro.")
    step_id: str
    section_id: str
    label: str
    type: QuestionType
    required: bool = True
    placeholder: str | None = None
    help_text: str | None = None
    max_length: int = 5000
    options: tuple[Option, ...] = ()
    #: Todas as condições precisam ser verdadeiras para a pergunta aparecer.
    show_if: tuple[Condition, ...] = ()
    # ---- pontuação
    scored: bool = False
    pillar_id: str | None = None
    pillar_weight: float | None = Field(default=None, description="Peso no pilar (%).")
    ems_weight: float | None = Field(default=None, description="Peso no EMS (%).")
    objective: str | None = None
    # ---- origem cadastral
    registry_field: RegistryField | None = None
    read_only: bool = False

    @property
    def max_points(self) -> int:
        return max((opt.points or 0 for opt in self.options), default=0)

    def option(self, value: str) -> Option | None:
        return next((opt for opt in self.options if opt.value == value), None)


class Section(_Frozen):
    id: str
    step_id: str
    title: str
    description: str | None = None


class Step(_Frozen):
    id: str
    order: int
    kind: StepKind
    title: str
    short_title: str
    description: str | None = None
    availability: StepAvailability = StepAvailability.AVAILABLE
    maintenance_message: str | None = None


class Catalog(_Frozen):
    version: str
    steps: tuple[Step, ...]
    sections: tuple[Section, ...]
    questions: tuple[Question, ...]
    pillars: tuple[Pillar, ...]

    def step(self, step_id: str) -> Step | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def question(self, question_id: str) -> Question | None:
        return self._index.get(question_id)

    @property
    def _index(self) -> dict[str, Question]:
        return {q.id: q for q in self.questions}

    def available_steps(self) -> list[Step]:
        return [s for s in self.steps if s.availability == StepAvailability.AVAILABLE]

    def questions_for_step(self, step_id: str) -> list[Question]:
        return [q for q in self.questions if q.step_id == step_id]


# ---------------------------------------------------------------------------
# Definição
# ---------------------------------------------------------------------------
_MAINTENANCE_MESSAGE = (
    "Este eixo estará disponível em uma próxima atualização do "
    "Diagnóstico de Maturidade Circular."
)

STEP_IDENTIFICATION = "identification"
STEP_MATERIAL_FLOWS = "axis_1_material_flows"
STEP_SYMBIOSIS = "axis_2_symbiosis"
STEP_ESG = "axis_3_esg"
STEP_ECONOMIC = "axis_4_economic"

PILLAR_FM = "fm"
PILLAR_PS = "ps"

_YES_NO = (Option(value="sim", label="Sim"), Option(value="nao", label="Não"))

_STEPS = (
    Step(
        id=STEP_IDENTIFICATION,
        order=1,
        kind=StepKind.IDENTIFICATION,
        title="Identificação (pré-diagnóstico)",
        short_title="Identificação",
        description=(
            "Dados da empresa e do contato responsável. Informações já existentes no "
            "cadastro são preenchidas automaticamente."
        ),
    ),
    Step(
        id=STEP_MATERIAL_FLOWS,
        order=2,
        kind=StepKind.AXIS,
        title="Eixo 1 — Fluxos de Materiais",
        short_title="Fluxos de Materiais",
        description=(
            "Mapeamento dos fluxos de matérias-primas, produtos, resíduos, perdas e "
            "práticas de gestão de materiais da empresa."
        ),
    ),
    Step(
        id=STEP_SYMBIOSIS,
        order=3,
        kind=StepKind.AXIS,
        title="Eixo 2 — Potencial de Simbiose",
        short_title="Potencial de Simbiose",
        availability=StepAvailability.MAINTENANCE,
        maintenance_message=_MAINTENANCE_MESSAGE,
    ),
    Step(
        id=STEP_ESG,
        order=4,
        kind=StepKind.AXIS,
        title="Eixo 3 — Conformidade ESG",
        short_title="Conformidade ESG",
        availability=StepAvailability.MAINTENANCE,
        maintenance_message=_MAINTENANCE_MESSAGE,
    ),
    Step(
        id=STEP_ECONOMIC,
        order=5,
        kind=StepKind.AXIS,
        title="Eixo 4 — Viabilidade Econômica",
        short_title="Viabilidade Econômica",
        availability=StepAvailability.MAINTENANCE,
        maintenance_message=_MAINTENANCE_MESSAGE,
    ),
)

_SECTIONS = (
    Section(id="id_company", step_id=STEP_IDENTIFICATION, title="Dados da empresa"),
    Section(
        id="id_contact",
        step_id=STEP_IDENTIFICATION,
        title="Contato responsável na empresa",
    ),
    Section(
        id="fm_production",
        step_id=STEP_MATERIAL_FLOWS,
        title="Mapeamento de produção e insumos",
    ),
    Section(id="fm_waste", step_id=STEP_MATERIAL_FLOWS, title="Mapeamento de resíduos"),
    Section(
        id="fm_data",
        step_id=STEP_MATERIAL_FLOWS,
        title="Gestão de dados",
        description="Registro e rastreabilidade das informações de geração e consumo.",
    ),
)

_PILLARS = (
    Pillar(id=PILLAR_FM, code="FM", name="Pilar 1 — Fluxo de Materiais"),
    Pillar(id=PILLAR_PS, code="PS", name="Pilar 2 — Potencial de Simbiose"),
)

_ID = STEP_IDENTIFICATION
_FM = STEP_MATERIAL_FLOWS

_QUESTIONS = (
    # ---------------------------------------------------------- Identificação
    Question(
        id="q01", code="ID.1", number=1, step_id=_ID, section_id="id_company", label="Razão Social",
        type=QuestionType.TEXT, max_length=200,
        registry_field=RegistryField.LEGAL_NAME, read_only=True,
    ),
    Question(
        id="q02", code="ID.2", number=2, step_id=_ID, section_id="id_company", label="CNPJ",
        type=QuestionType.TAX_ID, max_length=20,
        registry_field=RegistryField.TAX_ID, read_only=True,
    ),
    Question(
        id="q03", code="ID.3", number=3, step_id=_ID, section_id="id_company",
        label="Segmento/Atividade Principal", type=QuestionType.TEXT, max_length=200,
        registry_field=RegistryField.SECTOR,
    ),
    Question(
        id="q04", code="ID.4", number=4, step_id=_ID, section_id="id_company",
        label="Número de Colaboradores", type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="ate_50", label="Até 50"),
            Option(value="51_200", label="51–200"),
            Option(value="201_500", label="201–500"),
            Option(value="mais_500", label="+500"),
        ),
    ),
    Question(
        id="q05", code="ID.5", number=5, step_id=_ID, section_id="id_contact",
        label="Nome do Responsável",
        type=QuestionType.TEXT, max_length=200, registry_field=RegistryField.CONTACT_NAME,
    ),
    Question(
        id="q06", code="ID.6", number=6, step_id=_ID, section_id="id_contact", label="Cargo",
        type=QuestionType.TEXT, max_length=120,
        registry_field=RegistryField.CONTACT_JOB_TITLE,
    ),
    Question(
        id="q07", code="ID.7", number=7, step_id=_ID, section_id="id_contact", label="E-mail",
        type=QuestionType.EMAIL, max_length=254, registry_field=RegistryField.EMAIL,
    ),
    Question(
        id="q08", code="ID.8", number=8, step_id=_ID, section_id="id_contact",
        label="Telefone/WhatsApp",
        type=QuestionType.PHONE, max_length=30, registry_field=RegistryField.PHONE,
    ),
    # ------------------------- Eixo 1 — 1. Mapeamento de produção e insumos
    Question(
        id="q09", code="1.1", number=9, step_id=_FM, section_id="fm_production",
        label="Principais produtos fabricados", type=QuestionType.LONG_TEXT,
        objective="Contextualização e mapeamento da produção.",
    ),
    Question(
        id="q10", code="1.2", number=10, step_id=_FM, section_id="fm_production",
        label="Principais matérias-primas utilizadas (tipo e volume médio mensal)",
        type=QuestionType.LONG_TEXT,
        objective="Mapeamento dos principais insumos.",
    ),
    Question(
        id="q11", code="1.3", number=11, step_id=_FM, section_id="fm_production",
        label="Existe dependência de insumos provenientes de fora do estado ou país?",
        type=QuestionType.SINGLE_CHOICE, options=_YES_NO,
    ),
    Question(
        id="q12", code="1.4", number=12, step_id=_FM, section_id="fm_production",
        label="Quais insumos possuem maior dependência externa?",
        type=QuestionType.LONG_TEXT,
        show_if=(Condition(question_id="q11", operator=ConditionOperator.IN, values=("sim",)),),
    ),
    Question(
        id="q13", code="1.5", number=13, step_id=_FM, section_id="fm_production",
        label="Essa dependência impacta custos logísticos?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="sim", label="Sim"),
            Option(value="nao", label="Não"),
            Option(value="parcialmente", label="Parcialmente"),
        ),
    ),
    Question(
        id="q37", code="1.6", number=37, step_id=_FM, section_id="fm_production",
        label=(
            "Qual o índice estimado de perda de matéria-prima convertida em "
            "resíduos/refugo?"
        ),
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="menos_2", label="Menos de 2%", points=10),
            Option(value="entre_2_5", label="Entre 2% e 5%", points=5),
            Option(value="acima_5", label="Acima de 5%", points=0),
        ),
        scored=True, pillar_id=PILLAR_FM, pillar_weight=10, ems_weight=3,
        objective=(
            "Indicador de eficiência produtiva. Menor perda representa maior "
            "maturidade circular."
        ),
    ),
    # ------------------------------------- Eixo 1 — 2. Mapeamento de resíduos
    Question(
        id="q14", code="1.7", number=14, step_id=_FM, section_id="fm_waste",
        label="Principais resíduos ou subprodutos gerados (tipo e volume médio mensal)",
        type=QuestionType.LONG_TEXT,
    ),
    Question(
        id="q15", code="1.8", number=15, step_id=_FM, section_id="fm_waste",
        label="Classificação predominante dos resíduos", type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="nao_perigosos", label="Não perigosos"),
            Option(value="perigosos", label="Perigosos"),
            Option(value="ambos", label="Ambos"),
        ),
    ),
    Question(
        id="q29", code="1.9", number=29, step_id=_FM, section_id="fm_waste",
        label="Qual a classificação normativa predominante dos resíduos gerados?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="classe_iib", label="Classe IIB", points=40),
            Option(value="classe_iia", label="Classe IIA", points=25),
            Option(value="classe_i", label="Classe I", points=10),
        ),
        scored=True, pillar_id=PILLAR_FM, pillar_weight=40, ems_weight=12,
    ),
    Question(
        id="q16", code="1.10", number=16, step_id=_FM, section_id="fm_waste",
        label="Qual a frequência de geração?", type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="diaria", label="Diária"),
            Option(value="semanal", label="Semanal"),
            Option(value="mensal", label="Mensal"),
            Option(value="eventual", label="Eventual"),
        ),
    ),
    Question(
        id="q28", code="1.11", number=28, step_id=_FM, section_id="fm_waste",
        label="Como é feita a segregação do resíduo na fonte geradora?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="excelente", label="Excelente", points=40),
            Option(value="parcial", label="Parcial", points=15),
            Option(value="nulo", label="Nulo", points=0),
        ),
        scored=True, pillar_id=PILLAR_FM, pillar_weight=40, ems_weight=12,
    ),
    Question(
        id="q17", code="1.12", number=17, step_id=_FM, section_id="fm_waste",
        label="Existe tratamento interno antes da destinação?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="sim", label="Sim"),
            Option(value="nao", label="Não"),
            Option(value="as_vezes", label="Às vezes"),
        ),
    ),
    Question(
        id="q18", code="1.13", number=18, step_id=_FM, section_id="fm_waste",
        label="Descrever o tipo de tratamento realizado", type=QuestionType.LONG_TEXT,
        show_if=(
            Condition(
                question_id="q17", operator=ConditionOperator.IN, values=("sim", "as_vezes")
            ),
        ),
    ),
    Question(
        id="q19", code="1.14", number=19, step_id=_FM, section_id="fm_waste",
        label="Qual o destino principal dos resíduos?", type=QuestionType.MULTI_CHOICE,
        help_text="Selecione todas as opções aplicáveis.",
        options=(
            Option(value="aterro", label="Aterro"),
            Option(value="coprocessamento", label="Coprocessamento"),
            Option(value="reciclagem", label="Reciclagem"),
            Option(value="venda", label="Venda"),
            Option(value="doacao", label="Doação"),
            Option(value="outro", label="Outro"),
        ),
    ),
    Question(
        id="q19_other", step_id=_FM, section_id="fm_waste",
        label="Descreva o outro destino", type=QuestionType.TEXT, max_length=500,
        show_if=(
            Condition(
                question_id="q19", operator=ConditionOperator.CONTAINS_ANY, values=("outro",)
            ),
        ),
    ),
    Question(
        id="q31", code="1.15", number=31, step_id=_FM, section_id="fm_waste",
        label="Como se comporta a regularidade do fornecimento para uma indústria receptora?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="continuo", label="Contínuo", points=40),
            Option(value="sazonal", label="Sazonal", points=15),
        ),
        # Aparece no Eixo 1, mas é contabilizada no Pilar 2 (PS).
        scored=True, pillar_id=PILLAR_PS, pillar_weight=40, ems_weight=10,
    ),
    # ------------------------------------------- Eixo 1 — 3. Gestão de dados
    Question(
        id="q43", code="1.16", number=43, step_id=_FM, section_id="fm_data",
        label="De que forma os dados de geração e consumo são armazenados?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="erp", label="ERP integrado", points=10),
            Option(value="planilhas", label="Planilhas", points=5),
            Option(value="fisico", label="Registros físicos", points=0),
        ),
        scored=True, pillar_id=PILLAR_FM, pillar_weight=10, ems_weight=3,
        objective="Avaliar maturidade da gestão de dados e capacidade de rastreabilidade.",
    ),
)

CATALOG = Catalog(
    version=CATALOG_VERSION,
    steps=_STEPS,
    sections=_SECTIONS,
    questions=_QUESTIONS,
    pillars=_PILLARS,
)


def get_catalog() -> Catalog:
    return CATALOG


__all__ = [
    "CATALOG",
    "CATALOG_VERSION",
    "Catalog",
    "Condition",
    "ConditionOperator",
    "Option",
    "Pillar",
    "Question",
    "QuestionType",
    "RegistryField",
    "Section",
    "Step",
    "StepAvailability",
    "StepKind",
    "get_catalog",
]
