"""Unit tests for the matching service."""

from __future__ import annotations

from uuid import UUID

import pytest

from src.modules.opportunities.matching_service import MatchingService
from src.modules.opportunities.model import (
    OfferDemand,
    OpportunityDocument,
    OpportunityPeriodicity,
    OpportunityType,
)
from src.modules.opportunities.schema import (
    MatchPotential,
    OpportunityResponse,
)
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

pytestmark = pytest.mark.unit


def _doc(
    *,
    offer_demand: OfferDemand = OfferDemand.GERADOR,
    owner_user_id: UUID | None = None,
    category: str = "Plástico",
    technical_detail: str = "PET",
    purity_percent: float | None = 95.0,
    physical_state: str = "Triturado (Flakes)",
    quantity: float = 10.0,
    unit: str = "tonelada",
    price: float | None = 3500.0,
    price_negotiable: bool = False,
    city: str = "São Paulo",
    state: str = "SP",
) -> OpportunityDocument:
    now = utcnow()
    return OpportunityDocument(
        id=new_uuid(),
        company_id=new_uuid(),
        company_name="Acme Reciclagem",
        owner_user_id=owner_user_id or new_uuid(),
        title="Venda de PET Triturado",
        description="PET triturado de alta qualidade para reciclagem industrial.",
        opportunity_type=OpportunityType.COMERCIALIZACAO,
        offer_demand=offer_demand,
        category=category,
        technical_detail=technical_detail,
        purity_percent=purity_percent,
        physical_state=physical_state,
        periodicity=OpportunityPeriodicity.CONTINUA,
        quantity=quantity,
        unit=unit,
        price=price,
        price_negotiable=price_negotiable,
        city=city,
        state=state,
        images=[],
        created_at=now,
        updated_at=now,
    )


def _response_from_doc(doc: OpportunityDocument) -> OpportunityResponse:
    return OpportunityResponse(
        id=doc.id,
        company_id=doc.company_id,
        company_name=doc.company_name,
        owner_user_id=doc.owner_user_id,
        title=doc.title,
        description=doc.description,
        opportunity_type=doc.opportunity_type,
        offer_demand=doc.offer_demand,
        category=doc.category,
        technical_detail=doc.technical_detail,
        purity_percent=doc.purity_percent,
        physical_state=doc.physical_state,
        periodicity=doc.periodicity,
        quantity=doc.quantity,
        unit=doc.unit,
        price=doc.price,
        price_negotiable=doc.price_negotiable,
        city=doc.city,
        state=doc.state,
        images=[],
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def test_perfect_match_scores_high_and_all_criteria() -> None:
    offer = _doc(offer_demand=OfferDemand.GERADOR)
    demand = _doc(offer_demand=OfferDemand.RECEPTOR)
    demand_response = _response_from_doc(demand)

    match = MatchingService.calculate(offer, demand, demand_response=demand_response)

    assert match.score >= 90
    assert match.potential == MatchPotential.HIGH
    assert match.details.category == 100
    assert match.details.technical_detail == 100
    assert match.details.purity == 100
    assert match.details.physical_state == 100
    assert match.details.location == 100
    assert match.details.price == 100
    assert match.details.quantity == 100


def test_different_category_scores_at_most_30_even_with_perfect_secondary_criteria() -> None:
    offer = _doc(
        offer_demand=OfferDemand.GERADOR,
        category="Plástico",
        technical_detail="PET",
    )
    demand = _doc(
        offer_demand=OfferDemand.RECEPTOR,
        category="Metal",
        technical_detail="Aço Inox 304",
    )
    demand_response = _response_from_doc(demand)

    match = MatchingService.calculate(offer, demand, demand_response=demand_response)

    assert match.score <= 30
    assert match.potential == MatchPotential.LOW
    assert match.details.category == 0


def test_same_category_different_technical_detail_scores_between_40_and_70() -> None:
    offer = _doc(
        offer_demand=OfferDemand.GERADOR,
        category="Plástico",
        technical_detail="PET",
    )
    demand = _doc(
        offer_demand=OfferDemand.RECEPTOR,
        category="Plástico",
        technical_detail="PEAD",
    )
    demand_response = _response_from_doc(demand)

    match = MatchingService.calculate(offer, demand, demand_response=demand_response)

    assert 40 <= match.score <= 70
    assert match.details.category == 100
    assert match.details.technical_detail < 100


def test_same_state_different_city_location_score() -> None:
    offer = _doc(city="Campinas", state="SP")
    demand = _doc(offer_demand=OfferDemand.RECEPTOR, city="São Paulo", state="SP")
    demand_response = _response_from_doc(demand)

    match = MatchingService.calculate(offer, demand, demand_response=demand_response)

    assert match.details.location == 80


def test_neighboring_states_location_score() -> None:
    offer = _doc(state="SP", city="São Paulo")
    demand = _doc(
        offer_demand=OfferDemand.RECEPTOR, state="RJ", city="Rio de Janeiro"
    )
    demand_response = _response_from_doc(demand)

    match = MatchingService.calculate(offer, demand, demand_response=demand_response)

    assert match.details.location == 60


def test_distant_states_location_score() -> None:
    offer = _doc(state="SP", city="São Paulo")
    demand = _doc(
        offer_demand=OfferDemand.RECEPTOR, state="AM", city="Manaus"
    )
    demand_response = _response_from_doc(demand)

    match = MatchingService.calculate(offer, demand, demand_response=demand_response)

    assert match.details.location == 30


@pytest.mark.parametrize(
    ("offer_price", "demand_price", "expected_price_score"),
    [
        (100.0, 100.0, 100),
        (105.0, 100.0, 100),
        (108.0, 100.0, 90),
        (115.0, 100.0, 70),
        (125.0, 100.0, 40),
        (140.0, 100.0, 0),
    ],
)
def test_price_score_tiers(
    offer_price: float, demand_price: float, expected_price_score: int
) -> None:
    offer = _doc(price=offer_price)
    demand = _doc(offer_demand=OfferDemand.RECEPTOR, price=demand_price)
    demand_response = _response_from_doc(demand)

    match = MatchingService.calculate(offer, demand, demand_response=demand_response)

    assert match.details.price == expected_price_score


def test_quantity_score_same_unit() -> None:
    offer = _doc(quantity=10.0, unit="tonelada")
    demand = _doc(offer_demand=OfferDemand.RECEPTOR, quantity=10.0, unit="tonelada")
    demand_response = _response_from_doc(demand)

    match = MatchingService.calculate(offer, demand, demand_response=demand_response)

    assert match.details.quantity == 100


def test_quantity_score_different_units_penalized() -> None:
    offer = _doc(quantity=10.0, unit="tonelada")
    demand = _doc(offer_demand=OfferDemand.RECEPTOR, quantity=10.0, unit="kg")
    demand_response = _response_from_doc(demand)

    match = MatchingService.calculate(offer, demand, demand_response=demand_response)

    assert match.details.quantity == 40


def test_find_best_match_picks_highest_score() -> None:
    offer = _doc(category="Plástico", technical_detail="PET", state="SP")
    weak_demand = _doc(
        offer_demand=OfferDemand.RECEPTOR,
        category="Metal",
        technical_detail="Aço",
        state="AM",
    )
    strong_demand = _doc(
        offer_demand=OfferDemand.RECEPTOR,
        category="Plástico",
        technical_detail="PET",
        state="SP",
    )
    demand_responses = {
        str(weak_demand.id): _response_from_doc(weak_demand),
        str(strong_demand.id): _response_from_doc(strong_demand),
    }

    match = MatchingService.find_best_match(
        offer,
        [weak_demand, strong_demand],
        demand_responses=demand_responses,
    )

    assert match is not None
    assert match.matched_demand.id == strong_demand.id
    assert match.score >= 90


def test_find_best_match_returns_none_for_empty_demands() -> None:
    offer = _doc()
    match = MatchingService.find_best_match(offer, [], demand_responses={})
    assert match is None


def test_potential_classification() -> None:
    offer = _doc()
    high_demand = _doc(offer_demand=OfferDemand.RECEPTOR)
    low_demand = _doc(
        offer_demand=OfferDemand.RECEPTOR,
        category="Metal",
        technical_detail="Ferro",
        physical_state="Sólido",
        state="AM",
        city="Manaus",
        price=10000.0,
        quantity=1.0,
        unit="kg",
    )

    high_match = MatchingService.calculate(
        offer, high_demand, demand_response=_response_from_doc(high_demand)
    )
    low_match = MatchingService.calculate(
        offer, low_demand, demand_response=_response_from_doc(low_demand)
    )

    assert high_match.potential == MatchPotential.HIGH
    assert low_match.potential == MatchPotential.LOW
