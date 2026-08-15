"""Copy and mapping from opportunity type to minuta/contract."""

from __future__ import annotations

from src.modules.contract_sections.model import ContractType
from src.modules.opportunities.model import OpportunityType

MINUTA_TITLES: dict[OpportunityType, str] = {
    OpportunityType.COMERCIALIZACAO: "MINUTA DE CONTRATO DE COMERCIALIZAÇÃO",
    OpportunityType.SIMBIOSE_INDUSTRIAL: (
        "MINUTA DE CONTRATO DE SIMBIOSE INDUSTRIAL"
    ),
    OpportunityType.COMPARTILHAMENTO: (
        "MINUTA DE CONTRATO DE COMPARTILHAMENTO DE ATIVOS"
    ),
}

OPPORTUNITY_TO_CONTRACT_TYPE: dict[OpportunityType, ContractType] = {
    OpportunityType.COMERCIALIZACAO: ContractType.FORNECIMENTO,
    OpportunityType.SIMBIOSE_INDUSTRIAL: ContractType.PARCERIA,
    OpportunityType.COMPARTILHAMENTO: ContractType.SERVICO,
}

_OBJETO_TEMPLATES: dict[OpportunityType, str] = {
    OpportunityType.COMERCIALIZACAO: (
        "<p>A CONTRATADA comercializará os resíduos, matérias-primas ou "
        "subprodutos relacionados à oportunidade <strong>{title}</strong>, "
        "conforme condições de compra e venda acordadas entre as PARTES.</p>"
        "<p>{description}</p>"
    ),
    OpportunityType.SIMBIOSE_INDUSTRIAL: (
        "<p>As PARTES estabelecem uma relação de simbiose industrial para "
        "conexão de fluxos contínuos relacionados à oportunidade "
        "<strong>{title}</strong>, conforme condições acordadas.</p>"
        "<p>{description}</p>"
    ),
    OpportunityType.COMPARTILHAMENTO: (
        "<p>A CONTRATADA disponibilizará em regime de compartilhamento ou "
        "aluguel os ativos ou espaços relacionados à oportunidade "
        "<strong>{title}</strong>, conforme condições acordadas entre as "
        "PARTES.</p>"
        "<p>{description}</p>"
    ),
}

_VALOR_TEMPLATES: dict[OpportunityType, str] = {
    OpportunityType.COMERCIALIZACAO: (
        "<p>O valor acordado para a comercialização será de "
        "<strong>{valor}</strong>.</p>"
    ),
    OpportunityType.SIMBIOSE_INDUSTRIAL: (
        "<p>O valor acordado para a relação de simbiose industrial será de "
        "<strong>{valor}</strong>.</p>"
    ),
    OpportunityType.COMPARTILHAMENTO: (
        "<p>O valor acordado para o compartilhamento de ativos será de "
        "<strong>{valor}</strong>.</p>"
    ),
}

_DEFAULT_OBJETO = (
    "<p>A CONTRATADA prestará os serviços relacionados à oportunidade "
    "<strong>{title}</strong>, conforme condições acordadas entre as PARTES.</p>"
    "<p>{description}</p>"
)
_DEFAULT_VALOR = (
    "<p>O valor acordado para execução dos serviços será de "
    "<strong>{valor}</strong>.</p>"
)


def minuta_title_for(opportunity_type: OpportunityType | str | None) -> str:
    resolved = _as_opportunity_type(opportunity_type)
    if resolved is None:
        return "MINUTA DE CONTRATO DE PRESTAÇÃO DE SERVIÇOS"
    return MINUTA_TITLES[resolved]


def contract_type_for(
    opportunity_type: OpportunityType | str | None,
) -> ContractType:
    resolved = _as_opportunity_type(opportunity_type)
    if resolved is None:
        return ContractType.SERVICO
    return OPPORTUNITY_TO_CONTRACT_TYPE[resolved]


def objeto_html(
    *,
    opportunity_type: OpportunityType | str | None,
    opportunity_title: str,
    opportunity_description: str,
) -> str:
    resolved = _as_opportunity_type(opportunity_type)
    template = _OBJETO_TEMPLATES.get(resolved, _DEFAULT_OBJETO) if resolved else _DEFAULT_OBJETO
    return template.format(title=opportunity_title, description=opportunity_description)


def valor_html(
    *,
    opportunity_type: OpportunityType | str | None,
    valor: str,
) -> str:
    resolved = _as_opportunity_type(opportunity_type)
    template = _VALOR_TEMPLATES.get(resolved, _DEFAULT_VALOR) if resolved else _DEFAULT_VALOR
    return template.format(valor=valor)


def _as_opportunity_type(
    value: OpportunityType | str | None,
) -> OpportunityType | None:
    if value is None:
        return None
    if isinstance(value, OpportunityType):
        return value
    try:
        return OpportunityType(value)
    except ValueError:
        return None


__all__ = [
    "MINUTA_TITLES",
    "OPPORTUNITY_TO_CONTRACT_TYPE",
    "contract_type_for",
    "minuta_title_for",
    "objeto_html",
    "valor_html",
]
