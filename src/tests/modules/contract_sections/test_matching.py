"""Unit tests for opportunity-type matching on contract sections."""

from src.modules.contract_proposals.opportunity_contract import (
    contract_type_for,
    minuta_title_for,
    objeto_html,
)
from src.modules.contract_sections.matching import (
    template_applies_to_opportunity_type,
)
from src.modules.opportunities.model import OpportunityType


def test_empty_opportunity_types_apply_to_all() -> None:
    assert template_applies_to_opportunity_type([], OpportunityType.COMERCIALIZACAO)
    assert template_applies_to_opportunity_type(
        None, OpportunityType.SIMBIOSE_INDUSTRIAL
    )


def test_specific_opportunity_types_filter() -> None:
    types = [OpportunityType.COMERCIALIZACAO, OpportunityType.COMPARTILHAMENTO]
    assert template_applies_to_opportunity_type(
        types, OpportunityType.COMERCIALIZACAO
    )
    assert not template_applies_to_opportunity_type(
        types, OpportunityType.SIMBIOSE_INDUSTRIAL
    )


def test_minuta_title_and_contract_type_follow_opportunity() -> None:
    assert "COMERCIALIZAÇÃO" in minuta_title_for(OpportunityType.COMERCIALIZACAO)
    assert "SIMBIOSE" in minuta_title_for(OpportunityType.SIMBIOSE_INDUSTRIAL)
    assert "COMPARTILHAMENTO" in minuta_title_for(
        OpportunityType.COMPARTILHAMENTO
    )
    assert contract_type_for(OpportunityType.COMERCIALIZACAO).value == "fornecimento"
    assert contract_type_for(OpportunityType.SIMBIOSE_INDUSTRIAL).value == "parceria"
    assert contract_type_for(OpportunityType.COMPARTILHAMENTO).value == "servico"


def test_objeto_html_is_type_specific() -> None:
    comercializacao = objeto_html(
        opportunity_type=OpportunityType.COMERCIALIZACAO,
        opportunity_title="PET",
        opportunity_description="Desc",
    )
    simbiose = objeto_html(
        opportunity_type=OpportunityType.SIMBIOSE_INDUSTRIAL,
        opportunity_title="PET",
        opportunity_description="Desc",
    )
    assert "comercializará" in comercializacao
    assert "simbiose industrial" in simbiose
