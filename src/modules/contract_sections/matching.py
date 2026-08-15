"""Match contract section templates to opportunity types."""

from __future__ import annotations

from src.modules.contract_sections.model import ContractType
from src.modules.opportunities.model import OpportunityType

_CONTRACT_TYPE_TO_OPPORTUNITY: dict[ContractType, OpportunityType] = {
    ContractType.FORNECIMENTO: OpportunityType.COMERCIALIZACAO,
    ContractType.PARCERIA: OpportunityType.SIMBIOSE_INDUSTRIAL,
    ContractType.SERVICO: OpportunityType.COMPARTILHAMENTO,
}


def opportunity_type_value(value: OpportunityType | str) -> str:
    return value.value if isinstance(value, OpportunityType) else str(value)


def template_applies_to_opportunity_type(
    opportunity_types: list[OpportunityType] | list[str] | None,
    opportunity_type: OpportunityType | str,
) -> bool:
    """Legacy templates with an empty list apply to every opportunity type."""
    if not opportunity_types:
        return True
    target = opportunity_type_value(opportunity_type)
    return any(opportunity_type_value(item) == target for item in opportunity_types)


def opportunity_type_from_contract_type(
    contract_type: ContractType | str,
) -> OpportunityType | None:
    if isinstance(contract_type, str):
        try:
            contract_type = ContractType(contract_type)
        except ValueError:
            return None
    return _CONTRACT_TYPE_TO_OPPORTUNITY.get(contract_type)


def opportunity_mongo_filter(opportunity_type: OpportunityType | str) -> dict:
    type_value = opportunity_type_value(opportunity_type)
    return {
        "$or": [
            {"opportunity_types": type_value},
            {"opportunity_types": {"$size": 0}},
            {"opportunity_types": {"$exists": False}},
        ]
    }


__all__ = [
    "opportunity_mongo_filter",
    "opportunity_type_from_contract_type",
    "opportunity_type_value",
    "template_applies_to_opportunity_type",
]
