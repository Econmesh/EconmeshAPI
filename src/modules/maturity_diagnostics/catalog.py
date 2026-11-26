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

**Itens dinâmicos (produtos e resíduos).** Perguntas do tipo ``ITEM_LIST``
(1.1 e 1.7) são cadastros: a empresa registra vários produtos/resíduos. Cada
pergunta com ``per_item`` é respondida uma vez *para cada item* daquele tipo —
a resposta é gravada na chave ``"<pergunta>@<item>"``. Condições (``show_if``)
entre perguntas do mesmo tipo de item são avaliadas dentro do próprio item.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

CATALOG_VERSION = "2026-11.1"


class StepKind(StrEnum):
    IDENTIFICATION = "identification"
    AXIS = "axis"


class StepAvailability(StrEnum):
    AVAILABLE = "available"
    MAINTENANCE = "maintenance"


class ItemKind(StrEnum):
    """Tipos de item cadastráveis no diagnóstico."""

    PRODUCT = "product"
    WASTE = "waste"


class QuestionType(StrEnum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    EMAIL = "email"
    PHONE = "phone"
    TAX_ID = "tax_id"
    SINGLE_CHOICE = "single_choice"
    MULTI_CHOICE = "multi_choice"
    #: Cadastro de itens (produtos/resíduos) — respondido pelos endpoints de itens.
    ITEM_LIST = "item_list"


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
    #: Peso do pilar no EMS (%), quando definido.
    ems_weight: float | None = None


class AlertLevel(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"


class Option(_Frozen):
    value: str
    label: str
    points: int | None = None
    #: Alerta gerado quando esta opção é escolhida (ex.: risco jurídico crítico).
    alert_level: AlertLevel | None = None
    alert_message: str | None = None


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
    # ---- itens dinâmicos
    #: Pergunta respondida uma vez para cada item deste tipo.
    per_item: ItemKind | None = None
    #: Para ``ITEM_LIST``: tipo de item cadastrado pela pergunta.
    item_kind: ItemKind | None = None

    @property
    def max_points(self) -> int:
        return max((opt.points or 0 for opt in self.options), default=0)

    def option(self, value: str) -> Option | None:
        return next((opt for opt in self.options if opt.value == value), None)


class ItemReference(_Frozen):
    """Bloco somente leitura que reflete, por item, respostas dadas em outra etapa."""

    kind: ItemKind
    question_ids: tuple[str, ...]
    title: str
    description: str | None = None


class Section(_Frozen):
    id: str
    step_id: str
    title: str
    description: str | None = None
    #: Reflexo por item (ex.: classificação 1.8 de cada resíduo no Eixo 3).
    item_reference: ItemReference | None = None


class ItemKindMeta(_Frozen):
    kind: ItemKind
    label: str
    plural: str
    #: Pergunta ``ITEM_LIST`` que cadastra os itens deste tipo.
    list_question_id: str
    #: Rótulo do campo descritivo opcional do item.
    description_label: str
    max_items: int = 50


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
    item_kinds: tuple[ItemKindMeta, ...] = ()

    def item_kind(self, kind: ItemKind | str) -> ItemKindMeta | None:
        return next((meta for meta in self.item_kinds if meta.kind == kind), None)

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
PILLAR_CL = "cl"
PILLAR_VE = "ve"

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
        description=(
            "Destinação e valorização de resíduos, demanda de mercado, capacidade "
            "ociosa compartilhável e interesse da empresa em iniciativas de simbiose "
            "industrial."
        ),
    ),
    Step(
        id=STEP_ESG,
        order=4,
        kind=StepKind.AXIS,
        title="Eixo 3 — Conformidade ESG",
        short_title="Conformidade ESG",
        description=(
            "Licenciamento, rastreabilidade, caracterização dos resíduos, governança da "
            "cadeia de destinação, histórico regulatório e metas de sustentabilidade."
        ),
    ),
    Step(
        id=STEP_ECONOMIC,
        order=5,
        kind=StepKind.AXIS,
        title="Eixo 4 — Viabilidade Econômica",
        short_title="Viabilidade Econômica",
        description=(
            "Custos atuais com descarte e gestão de resíduos e disponibilidade de "
            "investimento para a transição circular."
        ),
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
    Section(
        id="ps_destination_market",
        step_id=STEP_SYMBIOSIS,
        title="Destinação e mercado de resíduos",
    ),
    Section(
        id="ps_capacity",
        step_id=STEP_SYMBIOSIS,
        title="Capacidade e infraestrutura compartilhável",
    ),
    Section(
        id="ps_engagement",
        step_id=STEP_SYMBIOSIS,
        title="Interesse e engajamento",
    ),
    Section(
        id="esg_licensing",
        step_id=STEP_ESG,
        title="Licenciamento e rastreabilidade",
        item_reference=ItemReference(
            kind=ItemKind.WASTE,
            question_ids=("q15",),
            title="Classificação dos resíduos (pergunta 1.8)",
            description=(
                "Reflexo da classificação informada para cada resíduo no Eixo 1. Para "
                "alterar, edite a pergunta 1.8 no Mapeamento de resíduos."
            ),
        ),
    ),
    Section(
        id="esg_chain",
        step_id=STEP_ESG,
        title="Caracterização e cadeia de destinação",
    ),
    Section(
        id="esg_regulatory",
        step_id=STEP_ESG,
        title="Histórico regulatório",
    ),
    Section(
        id="esg_governance",
        step_id=STEP_ESG,
        title="Governança e metas",
    ),
    Section(
        id="ve_costs",
        step_id=STEP_ECONOMIC,
        title="Custos de gestão de resíduos",
    ),
    Section(
        id="ve_investment",
        step_id=STEP_ECONOMIC,
        title="Capacidade de investimento",
    ),
)

_PILLARS = (
    # FM: 30% = soma dos pesos EMS das suas perguntas (12 + 12 + 3 + 3).
    Pillar(id=PILLAR_FM, code="FM", name="Pilar 1 — Fluxo de Materiais", ems_weight=30),
    Pillar(id=PILLAR_PS, code="PS", name="Pilar 2 — Potencial de Simbiose", ems_weight=25),
    Pillar(id=PILLAR_CL, code="CL", name="Pilar 3 — CL", ems_weight=25),
    Pillar(id=PILLAR_VE, code="VE", name="Pilar 4 — VE", ems_weight=20),
)

_ID = STEP_IDENTIFICATION
_FM = STEP_MATERIAL_FLOWS
_PS = STEP_SYMBIOSIS
_ESG = STEP_ESG
_VE = STEP_ECONOMIC

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
        label="Principais produtos fabricados", type=QuestionType.ITEM_LIST,
        item_kind=ItemKind.PRODUCT,
        help_text=(
            "Cadastre cada produto. As perguntas 1.2 a 1.6 e a seção Destinação e mercado "
            "de resíduos (Eixo 2) serão respondidas para cada produto."
        ),
        objective="Contextualização e mapeamento da produção.",
    ),
    Question(
        id="q10", code="1.2", number=10, step_id=_FM, section_id="fm_production",
        per_item=ItemKind.PRODUCT,
        label="Principais matérias-primas utilizadas (tipo e volume médio mensal)",
        type=QuestionType.LONG_TEXT,
        objective="Mapeamento dos principais insumos.",
    ),
    Question(
        id="q11", code="1.3", number=11, step_id=_FM, section_id="fm_production",
        per_item=ItemKind.PRODUCT,
        label="Existe dependência de insumos provenientes de fora do estado ou país?",
        type=QuestionType.SINGLE_CHOICE, options=_YES_NO,
    ),
    Question(
        id="q12", code="1.4", number=12, step_id=_FM, section_id="fm_production",
        per_item=ItemKind.PRODUCT,
        label="Quais insumos possuem maior dependência externa?",
        type=QuestionType.LONG_TEXT,
        show_if=(Condition(question_id="q11", operator=ConditionOperator.IN, values=("sim",)),),
    ),
    Question(
        id="q13", code="1.5", number=13, step_id=_FM, section_id="fm_production",
        per_item=ItemKind.PRODUCT,
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
        per_item=ItemKind.PRODUCT,
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
        label="Principais resíduos ou subprodutos gerados",
        type=QuestionType.ITEM_LIST, item_kind=ItemKind.WASTE,
        help_text=(
            "Cadastre cada resíduo ou subproduto (tipo e volume médio mensal). As perguntas "
            "1.8 a 1.15 e os Custos de gestão de resíduos (Eixo 4) serão respondidos para "
            "cada resíduo."
        ),
    ),
    Question(
        id="q15", code="1.8", number=15, step_id=_FM, section_id="fm_waste",
        per_item=ItemKind.WASTE,
        label="Classificação predominante dos resíduos", type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="nao_perigosos", label="Não perigosos"),
            Option(value="perigosos", label="Perigosos"),
            Option(value="ambos", label="Ambos"),
        ),
    ),
    Question(
        id="q29", code="1.9", number=29, step_id=_FM, section_id="fm_waste",
        per_item=ItemKind.WASTE,
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
        per_item=ItemKind.WASTE,
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
        per_item=ItemKind.WASTE,
        label="Como você avalia o processo de segregação dos resíduos no local onde são gerados?",
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
        per_item=ItemKind.WASTE,
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
        per_item=ItemKind.WASTE,
        label="Descrever o tipo de tratamento realizado", type=QuestionType.LONG_TEXT,
        show_if=(
            Condition(
                question_id="q17", operator=ConditionOperator.IN, values=("sim", "as_vezes")
            ),
        ),
    ),
    Question(
        id="q19", code="1.14", number=19, step_id=_FM, section_id="fm_waste",
        per_item=ItemKind.WASTE,
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
        per_item=ItemKind.WASTE,
        label="Descreva o outro destino", type=QuestionType.TEXT, max_length=500,
        show_if=(
            Condition(
                question_id="q19", operator=ConditionOperator.CONTAINS_ANY, values=("outro",)
            ),
        ),
    ),
    Question(
        id="q31", code="1.15", number=31, step_id=_FM, section_id="fm_waste",
        per_item=ItemKind.WASTE,
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
    # ----------------------- Eixo 2 — 1. Destinação e mercado de resíduos
    Question(
        id="ps_q25", code="2.1", number=25, step_id=_PS, section_id="ps_destination_market",
        per_item=ItemKind.PRODUCT,
        label="Qual o modelo predominante de rastreabilidade e destinação final adotado?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="coprocessamento_reciclagem", label="Coprocessamento/Reciclagem",
                   points=15),
            Option(value="aterro_patio", label="Aterro/Pátio", points=5),
        ),
        # Aparece no Eixo 2, mas é contabilizada no Pilar 3 (CL).
        scored=True, pillar_id=PILLAR_CL, pillar_weight=15, ems_weight=3.75,
        objective=(
            "Modelo de destinação é critério de conformidade regulatória."
        ),
    ),
    Question(
        id="ps_q26", code="2.2", number=26, step_id=_PS, section_id="ps_destination_market",
        per_item=ItemKind.PRODUCT,
        label="Algum resíduo gera receita para a empresa?",
        type=QuestionType.SINGLE_CHOICE, options=_YES_NO,
    ),
    Question(
        id="ps_q27", code="2.3", number=27, step_id=_PS, section_id="ps_destination_market",
        per_item=ItemKind.PRODUCT,
        label="Qual resíduo gera receita e como ocorre a comercialização?",
        type=QuestionType.LONG_TEXT,
        show_if=(
            Condition(question_id="ps_q26", operator=ConditionOperator.IN, values=("sim",)),
        ),
    ),
    Question(
        id="ps_q28", code="2.4", number=28, step_id=_PS, section_id="ps_destination_market",
        per_item=ItemKind.PRODUCT,
        label=(
            "Qual a percepção de mercado ou demanda regional para o subproduto no Nordeste?"
        ),
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="alta", label="Alta", points=60),
            Option(value="media", label="Média", points=30),
            Option(value="baixa", label="Baixa", points=0),
        ),
        scored=True, pillar_id=PILLAR_PS, pillar_weight=60, ems_weight=15,
        objective="Liquidez de mercado: alta demanda indica múltiplos compradores no Nordeste.",
    ),
    # ------------------ Eixo 2 — 2. Capacidade e infraestrutura compartilhável
    Question(
        id="ps_q29", code="2.5", number=29, step_id=_PS, section_id="ps_capacity",
        label="A empresa possui capacidade produtiva ou infraestrutura subutilizada?",
        type=QuestionType.SINGLE_CHOICE, options=_YES_NO,
    ),
    Question(
        id="ps_q30", code="2.6", number=30, step_id=_PS, section_id="ps_capacity",
        label="Quais áreas possuem capacidade ociosa?",
        type=QuestionType.MULTI_CHOICE,
        help_text="Selecione todas as opções aplicáveis.",
        options=(
            Option(value="equipamentos", label="Equipamentos"),
            Option(value="armazenamento", label="Armazenamento"),
            Option(value="transporte", label="Transporte"),
            Option(value="energia", label="Energia"),
            Option(value="servicos_tecnicos", label="Serviços técnicos"),
        ),
        show_if=(
            Condition(question_id="ps_q29", operator=ConditionOperator.IN, values=("sim",)),
        ),
    ),
    Question(
        id="ps_q31", code="2.7", number=31, step_id=_PS, section_id="ps_capacity",
        label="Haveria interesse em compartilhar essa estrutura com outras empresas?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="sim", label="Sim"),
            Option(value="nao", label="Não"),
            Option(value="talvez", label="Talvez"),
        ),
    ),
    # ------------------------------- Eixo 2 — 3. Interesse e engajamento
    Question(
        id="ps_q32", code="2.8", number=32, step_id=_PS, section_id="ps_engagement",
        label="A empresa teria interesse em:",
        type=QuestionType.MULTI_CHOICE,
        help_text="Selecione todas as opções aplicáveis.",
        options=(
            Option(value="vender_residuos", label="Vender resíduos"),
            Option(value="comprar_insumos", label="Comprar insumos"),
            Option(value="simbiose_industrial", label="Simbiose Industrial"),
            Option(value="compartilhar_infraestrutura", label="Compartilhar infraestrutura"),
            Option(value="receber_diagnostico", label="Receber diagnóstico"),
        ),
    ),
    Question(
        id="ps_q33", code="2.9", number=33, step_id=_PS, section_id="ps_engagement",
        label="Já participou de iniciativa de economia circular?",
        type=QuestionType.SINGLE_CHOICE, options=_YES_NO,
    ),
    Question(
        id="ps_q34", code="2.10", number=34, step_id=_PS, section_id="ps_engagement",
        label="Observações adicionais ou oportunidades percebidas",
        type=QuestionType.LONG_TEXT, required=False,
    ),
    # ---------------------- Eixo 3 — 1. Licenciamento e rastreabilidade
    Question(
        id="esg_q35", code="3.1", number=35, step_id=_ESG, section_id="esg_licensing",
        label="Qual a situação atual da Licença de Operação (LO) da empresa?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="ativa_regularizada", label="Ativa e Regularizada", points=25),
            Option(
                value="vencida_inexistente", label="Vencida ou Inexistente", points=0,
                alert_level=AlertLevel.CRITICAL,
                alert_message=(
                    "Risco crítico: Licença de Operação vencida ou inexistente. A LO ativa "
                    "é pré-requisito para a simbiose industrial."
                ),
            ),
        ),
        scored=True, pillar_id=PILLAR_CL, pillar_weight=25, ems_weight=6.25,
        objective="Trava de segurança jurídica: LO ativa é pré-requisito para simbiose.",
    ),
    Question(
        id="esg_q36", code="3.2", number=36, step_id=_ESG, section_id="esg_licensing",
        label="A empresa emite MTR Eletrônico para as saídas de materiais?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="sim_100", label="Sim 100%", points=25),
            Option(value="parcialmente", label="Parcialmente", points=10),
            Option(value="nao_emite", label="Não emite", points=0),
        ),
        scored=True, pillar_id=PILLAR_CL, pillar_weight=25, ems_weight=6.25,
        objective="Rastreabilidade obrigatória: MTR 100% indica conformidade total.",
    ),
    # --------------- Eixo 3 — 2. Caracterização e cadeia de destinação
    Question(
        id="esg_q37", code="3.3", number=37, step_id=_ESG, section_id="esg_chain",
        label="Possui laudos laboratoriais ou caracterizações físico-químicas atualizadas?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="sim_menos_1_ano", label="Sim menos de 1 ano 100%", points=15),
            Option(value="parcialmente", label="Parcialmente", points=7),
            Option(value="nao_possui", label="Não possui", points=0),
        ),
        scored=True, pillar_id=PILLAR_CL, pillar_weight=15, ems_weight=3.75,
        objective=(
            "Due diligence técnico: a indústria receptora exige caracterização do resíduo."
        ),
    ),
    Question(
        id="esg_q41", code="3.4", number=41, step_id=_ESG, section_id="esg_chain",
        label=(
            "Laudos laboratoriais ou caracterizações físico-químicas atualizadas "
            "(detalhamento)"
        ),
        type=QuestionType.LONG_TEXT, required=False,
        help_text=(
            "Descreva quais laudos existem, laboratórios responsáveis e parâmetros analisados."
        ),
    ),
    Question(
        id="esg_q38", code="3.5", number=38, step_id=_ESG, section_id="esg_chain",
        label="Realiza auditorias ou exige certificações dos transportadores e receptoras?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="homologacao_rigorosa", label="Homologação rigorosa", points=10),
            Option(value="verificacao_basica", label="Verificação básica", points=5),
            Option(value="nao_rastreia", label="Não rastreia", points=0),
        ),
        scored=True, pillar_id=PILLAR_CL, pillar_weight=10, ems_weight=2.5,
        objective="Governança da cadeia de destinação.",
    ),
    Question(
        id="esg_q42", code="3.6", number=42, step_id=_ESG, section_id="esg_chain",
        label="Auditorias ou certificações dos transportadores e receptoras (detalhamento)",
        type=QuestionType.LONG_TEXT, required=False,
        help_text="Descreva quais certificações são exigidas e o processo de homologação.",
    ),
    # ------------------------------------- Eixo 3 — 3. Histórico regulatório
    Question(
        id="esg_q39", code="3.7", number=39, step_id=_ESG, section_id="esg_regulatory",
        label="Histórico de autos de infração ou pendências jurídicas (últimos 3 anos)?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="nenhum_registro", label="Nenhum registro", points=10),
            Option(value="notificacoes_aberto", label="Notificações em aberto", points=3),
            Option(value="prefere_nao_declarar", label="Prefere não declarar", points=0),
        ),
        scored=True, pillar_id=PILLAR_CL, pillar_weight=10, ems_weight=2.5,
        objective="Conformidade histórica.",
    ),
    Question(
        id="esg_q43", code="3.8", number=43, step_id=_ESG, section_id="esg_regulatory",
        label="Histórico de autos de infração ou pendências jurídicas (detalhamento)",
        type=QuestionType.LONG_TEXT, required=False,
        help_text=(
            "Descreva a natureza das infrações, o status de regularização e as ações "
            "corretivas."
        ),
    ),
    # --------------------------------------- Eixo 3 — 4. Governança e metas
    Question(
        id="esg_q40", code="3.9", number=40, step_id=_ESG, section_id="esg_governance",
        label="Possui metas corporativas formais de sustentabilidade?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="possui_metas", label="Possui metas formais", points=25),
            Option(value="nao_possui", label="Não possui", points=5),
        ),
        # Aparece no Eixo 3, mas é contabilizada no Pilar 4 (VE).
        scored=True, pillar_id=PILLAR_VE, pillar_weight=25, ems_weight=5,
        objective="Metas formais facilitam a decisão de investimento (ROI).",
    ),
    # ------------------------ Eixo 4 — 1. Custos de gestão de resíduos
    Question(
        id="ve_q44", code="4.1", number=44, step_id=_VE, section_id="ve_costs",
        per_item=ItemKind.WASTE,
        label="Como classifica o custo atual de descarte e logística associada a este resíduo?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="alto", label="Alto", points=35),
            Option(value="medio", label="Médio", points=20),
            Option(value="baixo", label="Baixo", points=5),
        ),
        scored=True, pillar_id=PILLAR_VE, pillar_weight=35, ems_weight=7,
        objective="Incentivo financeiro: custos altos criam urgência para circularizar.",
    ),
    Question(
        id="ve_q45", code="4.2", number=45, step_id=_VE, section_id="ve_costs",
        per_item=ItemKind.WASTE,
        label="Qual o custo mensal aproximado com a gestão deste resíduo?",
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="acima_50000", label="Acima de R$ 50.000", points=20),
            Option(value="10001_50000", label="Entre R$ 10.001 e R$ 50.000", points=10),
            Option(value="ate_10000", label="Até R$ 10.000", points=5),
        ),
        scored=True, pillar_id=PILLAR_VE, pillar_weight=20, ems_weight=4,
        objective="Impacto financeiro real: custos altos indicam maior ROI potencial.",
    ),
    Question(
        id="ve_q47", code="4.3", number=47, step_id=_VE, section_id="ve_costs",
        per_item=ItemKind.WASTE,
        label="Custo mensal aproximado com a gestão deste resíduo (detalhamento)",
        type=QuestionType.LONG_TEXT, required=False,
        help_text=(
            "Descreva a composição do custo (coleta, transporte, destinação, taxas)."
        ),
    ),
    # ---------------------------- Eixo 4 — 2. Capacidade de investimento
    Question(
        id="ve_q46", code="4.4", number=46, step_id=_VE, section_id="ve_investment",
        label=(
            "Possui orçamento ou disponibilidade de investimento (CAPEX) para circularidade?"
        ),
        type=QuestionType.SINGLE_CHOICE,
        options=(
            Option(value="sim_roi_12m", label="Sim ROI menor que 12 meses", points=20),
            Option(value="apenas_custo_zero", label="Apenas custo zero", points=10),
            Option(value="sem_orcamento", label="Sem orçamento", points=0),
        ),
        scored=True, pillar_id=PILLAR_VE, pillar_weight=20, ems_weight=4,
        objective="Prontidão de investimento: sem orçamento indica barreira financeira.",
    ),
    Question(
        id="ve_q48", code="4.5", number=48, step_id=_VE, section_id="ve_investment",
        label=(
            "Orçamento ou disponibilidade de investimento (CAPEX) para circularidade "
            "(detalhamento)"
        ),
        type=QuestionType.LONG_TEXT, required=False,
        help_text="Descreva fontes de financiamento, limites de CAPEX e critérios de ROI.",
    ),
)

_ITEM_KINDS = (
    ItemKindMeta(
        kind=ItemKind.PRODUCT,
        label="Produto",
        plural="Produtos",
        list_question_id="q09",
        description_label="Descrição (opcional)",
        max_items=30,
    ),
    ItemKindMeta(
        kind=ItemKind.WASTE,
        label="Resíduo",
        plural="Resíduos",
        list_question_id="q14",
        description_label="Tipo e volume médio mensal (opcional)",
        max_items=50,
    ),
)

CATALOG = Catalog(
    version=CATALOG_VERSION,
    steps=_STEPS,
    sections=_SECTIONS,
    questions=_QUESTIONS,
    pillars=_PILLARS,
    item_kinds=_ITEM_KINDS,
)


def get_catalog() -> Catalog:
    return CATALOG


__all__ = [
    "CATALOG",
    "CATALOG_VERSION",
    "AlertLevel",
    "Catalog",
    "Condition",
    "ConditionOperator",
    "ItemKind",
    "ItemKindMeta",
    "ItemReference",
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
