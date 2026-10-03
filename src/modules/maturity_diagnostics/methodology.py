"""Configuração central da metodologia e das regras de interpretação do relatório.

Tudo o que o relatório "diz" sai daqui: versões, régua de maturidade, faixas
de leitura dos indicadores, textos de interpretação por resposta, oportunidades
e regras contextuais. Nenhum texto interpretativo fica no frontend.

Os textos descrevem apenas o que a resposta registrada indica — não afirmam
fatos sobre a empresa além do que foi respondido.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

#: Versão das regras de cálculo + interpretação. Mudou a regra → nova versão.
METHODOLOGY_VERSION = "2026.10-1"
#: Versão do formato do relatório gerado (estrutura de dados / layout).
REPORT_VERSION = "1.0"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# Régua de maturidade
# ---------------------------------------------------------------------------
class MaturityLevel(_Frozen):
    level: int
    name: str
    #: Faixa do score geral (EMS, 0–100), inclusiva.
    min_score: float
    max_score: float
    description: str
    criteria: str | None = None
    interpretation: str | None = None


class MaturityScale(_Frozen):
    #: ``True`` somente quando a régua for a metodologia oficial cadastrada.
    official: bool
    version: str | None = None
    levels: tuple[MaturityLevel, ...] = ()

    def classify(self, score: float | None) -> MaturityLevel | None:
        if score is None or not self.levels:
            return None
        for level in self.levels:
            if level.min_score <= score <= level.max_score:
                return level
        return None


#: Régua de maturidade (``maturityLevels``).
#:
#: O projeto ainda não possui régua oficial cadastrada, por isso nenhum nível
#: é aplicado e o relatório informa "não classificado". Para ativar, preencha
#: os níveis com nome, faixa, descrição, critérios e interpretação — ex.:
#:
#:     MaturityLevel(level=1, name="Inicial", min_score=0, max_score=20, description="…")
#:
#: e marque ``official=True`` com a versão da régua.
MATURITY_SCALE = MaturityScale(official=False, version=None, levels=())


# ---------------------------------------------------------------------------
# Leitura dos indicadores pontuados
# ---------------------------------------------------------------------------
class Tier(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


#: Faixas pela razão pontos/máximo da pergunta.
TIER_HIGH_MIN_RATIO = 0.75
TIER_MEDIUM_MIN_RATIO = 0.40


def tier_for(points: int, max_points: int) -> Tier:
    ratio = points / max_points if max_points else 0.0
    if ratio >= TIER_HIGH_MIN_RATIO:
        return Tier.HIGH
    if ratio >= TIER_MEDIUM_MIN_RATIO:
        return Tier.MEDIUM
    return Tier.LOW


#: Leitura relativa de pilares/eixos (percentual do máximo).
def relative_reading(percent: float | None) -> str | None:
    if percent is None:
        return None
    if percent >= TIER_HIGH_MIN_RATIO * 100:
        return "resultado alto em relação ao máximo possível"
    if percent >= TIER_MEDIUM_MIN_RATIO * 100:
        return "resultado intermediário em relação ao máximo possível"
    return "resultado baixo em relação ao máximo possível"


class IndicatorContent(_Frozen):
    #: Nome curto do indicador no relatório.
    title: str
    #: Interpretação por valor de opção (chave = ``Option.value``).
    by_option: dict[str, str]
    opportunity_title: str | None = None
    opportunity_text: str | None = None
    #: ``False`` quando pontuação baixa não é um ponto fraco da empresa
    #: (ex.: custo baixo de descarte = menor incentivo, não deficiência).
    attention_on_low: bool = True


INDICATORS: dict[str, IndicatorContent] = {
    # ------------------------------------------------- Pilar 1 — FM
    "q28": IndicatorContent(
        title="Segregação na fonte",
        by_option={
            "excelente": (
                "Segregação na fonte registrada como excelente: indica organização dos "
                "resíduos no ponto de geração, condição que favorece o aproveitamento."
            ),
            "parcial": (
                "Segregação na fonte registrada como parcial: a mistura de resíduos tende "
                "a reduzir as possibilidades de aproveitamento."
            ),
            "nulo": (
                "Não há segregação na fonte: a mistura de resíduos tende a reduzir as "
                "possibilidades de aproveitamento."
            ),
        },
        opportunity_title="Aprimoramento da segregação na fonte",
        opportunity_text=(
            "Avaliar os pontos de geração em que a separação ainda não ocorre de forma "
            "completa e estruturar procedimentos de segregação por tipo de material."
        ),
    ),
    "q29": IndicatorContent(
        title="Classificação normativa dos resíduos",
        by_option={
            "classe_iib": (
                "Predominância de resíduos Classe IIB, perfil que tende a facilitar o "
                "reaproveitamento e a destinação."
            ),
            "classe_iia": (
                "Predominância de resíduos Classe IIA: perfil compatível com "
                "reaproveitamento, podendo exigir tratamento ou caracterização adicional."
            ),
            "classe_i": (
                "Predominância de resíduos Classe I (perigosos): exige controles específicos "
                "de manuseio e destinação, o que restringe alternativas de reaproveitamento."
            ),
        },
        opportunity_title="Gestão dos resíduos conforme a classificação",
        opportunity_text=(
            "Mapear os fluxos classificados como Classe I ou IIA e avaliar alternativas de "
            "tratamento, substituição de insumos ou destinação que ampliem o reaproveitamento."
        ),
    ),
    "q31": IndicatorContent(
        title="Regularidade de fornecimento",
        by_option={
            "continuo": (
                "Fornecimento contínuo para indústria receptora: regularidade que favorece "
                "acordos de simbiose industrial."
            ),
            "sazonal": (
                "Fornecimento sazonal: a irregularidade de volumes pode dificultar acordos "
                "estáveis com indústrias receptoras."
            ),
        },
        opportunity_title="Regularidade de fornecimento",
        opportunity_text=(
            "Avaliar formas de estabilizar a oferta de resíduos e subprodutos (por exemplo, "
            "armazenamento ou consolidação de volumes) para viabilizar parcerias."
        ),
    ),
    "q37": IndicatorContent(
        title="Perda de matéria-prima",
        by_option={
            "menos_2": (
                "Perda estimada de matéria-prima inferior a 2%: indicador favorável de "
                "eficiência produtiva."
            ),
            "entre_2_5": (
                "Perda estimada de matéria-prima entre 2% e 5%: há margem para redução de "
                "perdas no processo."
            ),
            "acima_5": (
                "Perda estimada de matéria-prima acima de 5%: parcela relevante de insumos "
                "convertida em resíduo ou refugo."
            ),
        },
        opportunity_title="Redução de perdas de matéria-prima",
        opportunity_text=(
            "Identificar as etapas do processo com maior geração de refugo e avaliar ações "
            "para reduzir as perdas de matéria-prima."
        ),
    ),
    "q43": IndicatorContent(
        title="Gestão dos dados",
        by_option={
            "erp": (
                "Dados de geração e consumo em ERP integrado: favorece a rastreabilidade e o "
                "acompanhamento dos indicadores."
            ),
            "planilhas": (
                "Dados de geração e consumo em planilhas: há registro, porém com menor "
                "integração e rastreabilidade."
            ),
            "fisico": (
                "Dados de geração e consumo em registros físicos: limita a rastreabilidade e "
                "a análise dos indicadores."
            ),
        },
        opportunity_title="Aprimoramento da rastreabilidade",
        opportunity_text=(
            "Ampliar a digitalização e a integração dos registros de consumo e geração de "
            "resíduos para acompanhar os indicadores com regularidade."
        ),
    ),
    # ------------------------------------------------- Pilar 2 — PS
    "ps_q28": IndicatorContent(
        title="Demanda regional pelo subproduto",
        by_option={
            "alta": (
                "Percepção de alta demanda regional no Nordeste para o subproduto: indica "
                "liquidez de mercado."
            ),
            "media": "Percepção de demanda regional média para o subproduto no Nordeste.",
            "baixa": (
                "Percepção de baixa demanda regional para o subproduto: a comercialização "
                "pode exigir prospecção de novos mercados ou usos."
            ),
        },
        opportunity_title="Desenvolvimento de mercado para subprodutos",
        opportunity_text=(
            "Mapear potenciais compradores e usos alternativos do subproduto na região."
        ),
    ),
    # ------------------------------------------------- Pilar 3 — CL
    "ps_q25": IndicatorContent(
        title="Modelo de destinação final",
        by_option={
            "coprocessamento_reciclagem": (
                "Destinação predominante por coprocessamento ou reciclagem: modelo alinhado "
                "aos critérios de conformidade e valorização de resíduos."
            ),
            "aterro_patio": (
                "Destinação predominante em aterro ou pátio: modelo com menor valorização "
                "dos resíduos."
            ),
        },
        opportunity_title="Revisão do modelo de destinação",
        opportunity_text=(
            "Avaliar alternativas de reciclagem, coprocessamento ou valorização para as "
            "frações hoje encaminhadas a aterro ou pátio."
        ),
    ),
    "esg_q35": IndicatorContent(
        title="Licença de Operação",
        by_option={
            "ativa_regularizada": (
                "Licença de Operação ativa e regularizada: atende ao pré-requisito jurídico "
                "para iniciativas de simbiose."
            ),
            "vencida_inexistente": (
                "Licença de Operação vencida ou inexistente: risco jurídico crítico. A LO "
                "ativa é pré-requisito para a simbiose industrial."
            ),
        },
        opportunity_title="Regularização da Licença de Operação",
        opportunity_text=(
            "Priorizar a regularização da LO junto ao órgão ambiental competente antes de "
            "iniciar parcerias de simbiose."
        ),
    ),
    "esg_q36": IndicatorContent(
        title="MTR Eletrônico",
        by_option={
            "sim_100": (
                "Emissão de MTR Eletrônico em 100% das saídas: indica conformidade com a "
                "rastreabilidade obrigatória."
            ),
            "parcialmente": (
                "Emissão parcial de MTR Eletrônico: parte das saídas de materiais sem "
                "rastreabilidade formal."
            ),
            "nao_emite": (
                "MTR Eletrônico não emitido: lacuna na rastreabilidade obrigatória das "
                "saídas de materiais."
            ),
        },
        opportunity_title="Ampliação da emissão de MTR",
        opportunity_text="Estender a emissão do MTR Eletrônico a todas as saídas de materiais.",
    ),
    "esg_q37": IndicatorContent(
        title="Laudos e caracterizações",
        by_option={
            "sim_menos_1_ano": (
                "Laudos laboratoriais atualizados (menos de 1 ano): caracterização "
                "disponível, usualmente exigida por indústrias receptoras."
            ),
            "parcialmente": "Laudos ou caracterizações disponíveis apenas parcialmente.",
            "nao_possui": (
                "Sem laudos ou caracterizações físico-químicas: indústrias receptoras "
                "costumam exigir a caracterização do resíduo."
            ),
        },
        opportunity_title="Caracterização dos resíduos",
        opportunity_text=(
            "Atualizar ou realizar laudos e caracterizações físico-químicas dos principais "
            "resíduos."
        ),
    ),
    "esg_q38": IndicatorContent(
        title="Homologação de transportadores e receptoras",
        by_option={
            "homologacao_rigorosa": (
                "Homologação rigorosa de transportadores e receptoras: indica governança da "
                "cadeia de destinação."
            ),
            "verificacao_basica": "Verificação básica de transportadores e receptoras.",
            "nao_rastreia": "Transportadores e receptoras não são rastreados ou verificados.",
        },
        opportunity_title="Governança da cadeia de destinação",
        opportunity_text=(
            "Estruturar critérios de homologação e verificação documental de transportadores "
            "e receptoras."
        ),
    ),
    "esg_q39": IndicatorContent(
        title="Histórico regulatório",
        by_option={
            "nenhum_registro": (
                "Nenhum registro de autos de infração ou pendências jurídicas nos últimos "
                "3 anos."
            ),
            "notificacoes_aberto": "Notificações em aberto nos últimos 3 anos.",
            "prefere_nao_declarar": (
                "Histórico de infrações não declarado: não foi possível avaliar a "
                "conformidade histórica."
            ),
        },
        opportunity_title="Regularização de pendências",
        opportunity_text=(
            "Acompanhar e encerrar as notificações em aberto, registrando as ações "
            "corretivas adotadas."
        ),
    ),
    # ------------------------------------------------- Pilar 4 — VE
    "esg_q40": IndicatorContent(
        title="Metas de sustentabilidade",
        by_option={
            "possui_metas": (
                "Metas corporativas formais de sustentabilidade: facilitam a decisão de "
                "investimento em circularidade."
            ),
            "nao_possui": "Sem metas corporativas formais de sustentabilidade.",
        },
        opportunity_title="Definição de metas de sustentabilidade",
        opportunity_text=(
            "Avaliar a definição de metas formais de sustentabilidade que orientem decisões "
            "de investimento em circularidade."
        ),
    ),
    "ve_q44": IndicatorContent(
        title="Custo de descarte e logística",
        by_option={
            "alto": (
                "Custo de descarte e logística classificado como alto: representa incentivo "
                "financeiro para a transição circular."
            ),
            "medio": "Custo de descarte e logística classificado como médio.",
            "baixo": (
                "Custo de descarte e logística classificado como baixo: menor incentivo "
                "financeiro imediato para mudanças no modelo de destinação."
            ),
        },
        attention_on_low=False,
    ),
    "ve_q45": IndicatorContent(
        title="Custo mensal com gestão de resíduos",
        by_option={
            "acima_50000": (
                "Custo mensal com gestão de resíduos acima de R$ 50.000: maior potencial de "
                "retorno para iniciativas de circularidade."
            ),
            "10001_50000": "Custo mensal com gestão de resíduos entre R$ 10.001 e R$ 50.000.",
            "ate_10000": "Custo mensal com gestão de resíduos de até R$ 10.000.",
        },
        attention_on_low=False,
    ),
    "ve_q46": IndicatorContent(
        title="Disponibilidade de investimento (CAPEX)",
        by_option={
            "sim_roi_12m": (
                "Orçamento disponível para investimentos com retorno em até 12 meses: indica "
                "prontidão para investir em circularidade."
            ),
            "apenas_custo_zero": "Disponibilidade apenas para iniciativas de custo zero.",
            "sem_orcamento": (
                "Sem orçamento para circularidade: barreira financeira para novas iniciativas."
            ),
        },
        opportunity_title="Planejamento de investimentos em circularidade",
        opportunity_text=(
            "Priorizar iniciativas de baixo custo e estimar o retorno das ações para apoiar "
            "futuras decisões de investimento."
        ),
    ),
}


# ---------------------------------------------------------------------------
# Regras contextuais (perguntas não pontuadas)
# ---------------------------------------------------------------------------
class ContextKind(StrEnum):
    STRENGTH = "strength"
    ATTENTION = "attention"
    OPPORTUNITY = "opportunity"


class ContextRule(_Frozen):
    question_id: str
    #: Dispara quando a resposta (ou alguma das selecionadas) está entre estes valores.
    values: tuple[str, ...]
    kind: ContextKind
    title: str
    text: str
    #: Pergunta cuja resposta é anexada ao texto (ex.: quais áreas ociosas).
    detail_question_id: str | None = None


CONTEXT_RULES: tuple[ContextRule, ...] = (
    ContextRule(
        question_id="q11",
        values=("sim",),
        kind=ContextKind.ATTENTION,
        title="Dependência de insumos externos",
        text="Foi informada dependência de insumos provenientes de fora do estado ou país.",
        detail_question_id="q12",
    ),
    ContextRule(
        question_id="q13",
        values=("sim", "parcialmente"),
        kind=ContextKind.ATTENTION,
        title="Impacto logístico da dependência externa",
        text="Foi informado que a dependência de insumos externos impacta custos logísticos.",
    ),
    ContextRule(
        question_id="q15",
        values=("perigosos", "ambos"),
        kind=ContextKind.ATTENTION,
        title="Geração de resíduos perigosos",
        text=(
            "Os resíduos gerados incluem frações perigosas, que exigem controles específicos "
            "de manuseio e destinação."
        ),
    ),
    ContextRule(
        question_id="ps_q26",
        values=("sim",),
        kind=ContextKind.STRENGTH,
        title="Resíduo com geração de receita",
        text="Foi informado que ao menos um resíduo já gera receita para a empresa.",
        detail_question_id="ps_q27",
    ),
    ContextRule(
        question_id="ps_q29",
        values=("sim",),
        kind=ContextKind.OPPORTUNITY,
        title="Compartilhamento de capacidade ociosa",
        text=(
            "Foi informada capacidade produtiva ou infraestrutura subutilizada, que pode ser "
            "avaliada para compartilhamento com outras empresas."
        ),
        detail_question_id="ps_q30",
    ),
    ContextRule(
        question_id="ps_q33",
        values=("sim",),
        kind=ContextKind.STRENGTH,
        title="Participação em iniciativas de economia circular",
        text="A empresa já participou de iniciativa de economia circular.",
    ),
)


# ---------------------------------------------------------------------------
# Textos da seção Metodologia (sem fundamentos além do definido no projeto)
# ---------------------------------------------------------------------------
METHODOLOGY_OBJECTIVE = (
    "O Diagnóstico de Maturidade Circular (DMC) é conduzido por um Agente DMC junto à "
    "empresa e organiza as respostas em eixos temáticos. As perguntas pontuadas são "
    "consolidadas em pilares de cálculo ponderados, que compõem o score geral (EMS)."
)

METHODOLOGY_SCORING = (
    "Cada pergunta pontuada atribui pontos à opção escolhida e pertence a um pilar de "
    "cálculo, que pode ser diferente do eixo em que a pergunta aparece no formulário.",
    "A pontuação de um pilar é a soma dos pontos das suas perguntas; o máximo de cada pilar "
    "é 100 pontos.",
    "Cada pergunta tem um peso no EMS. A contribuição de uma resposta é: pontos obtidos ÷ "
    "pontos máximos da pergunta × peso no EMS. O score geral é a soma dessas contribuições.",
    "Perguntas não pontuadas registram o contexto da empresa e são usadas na leitura "
    "qualitativa do relatório, sem alterar o score.",
)

METHODOLOGY_RESULTS = (
    "O score geral varia de 0 a 100 quando todos os eixos são avaliados; quanto maior, mais "
    "próximo do máximo definido pela metodologia.",
    "Os percentuais por eixo e por pilar indicam a proporção alcançada em relação ao máximo "
    "possível naquele recorte.",
    "As interpretações por indicador seguem regras pré-definidas para cada resposta: "
    f"≥ {round(TIER_HIGH_MIN_RATIO * 100)}% do máximo da pergunta é tratado como ponto de "
    f"destaque; entre {round(TIER_MEDIUM_MIN_RATIO * 100)}% e "
    f"{round(TIER_HIGH_MIN_RATIO * 100)}% como ponto de atenção moderado; abaixo de "
    f"{round(TIER_MEDIUM_MIN_RATIO * 100)}% como ponto de atenção.",
    "Oportunidades de melhoria são sugestões derivadas das respostas e não constituem "
    "recomendação técnica definitiva.",
)


__all__ = [
    "CONTEXT_RULES",
    "INDICATORS",
    "MATURITY_SCALE",
    "METHODOLOGY_OBJECTIVE",
    "METHODOLOGY_RESULTS",
    "METHODOLOGY_SCORING",
    "METHODOLOGY_VERSION",
    "REPORT_VERSION",
    "ContextKind",
    "ContextRule",
    "IndicatorContent",
    "MaturityLevel",
    "MaturityScale",
    "Tier",
    "relative_reading",
    "tier_for",
]
