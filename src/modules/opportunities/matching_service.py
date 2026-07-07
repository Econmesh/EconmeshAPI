"""Matching score calculation between offers and demands."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from src.modules.opportunities.model import OpportunityDocument
from src.modules.opportunities.schema import (
    MatchDetails,
    MatchPotential,
    OpportunityMatch,
    OpportunityResponse,
)
from src.shared.constants.brazil_states import are_neighboring_states

_CRITERION_WEIGHTS = {
    "category": 0.40,
    "technical_detail": 0.30,
    "purity": 0.05,
    "physical_state": 0.05,
    "location": 0.10,
    "quantity": 0.05,
    "price": 0.05,
}

_CATEGORY_MISMATCH_CAP = 30.0
_DETAIL_MISMATCH_CAP = 60.0
_CATEGORY_MISMATCH_FACTOR = 0.25
_DETAIL_MISMATCH_FACTOR = 0.60


@dataclass(frozen=True, slots=True)
class _CriterionScores:
    category: float
    technical_detail: float
    purity: float
    physical_state: float
    location: float
    quantity: float
    price: float


class MatchingService:
    """Pure scoring logic for offer–demand compatibility."""

    @staticmethod
    def _normalize_text(value: str) -> str:
        return value.strip().lower()

    @classmethod
    def _text_similarity_score(cls, left: str, right: str) -> float:
        a = cls._normalize_text(left)
        b = cls._normalize_text(right)
        if a == b:
            return 100.0
        ratio = SequenceMatcher(None, a, b).ratio()
        if ratio >= 0.8:
            return 80.0
        if ratio >= 0.5:
            return 60.0
        return max(0.0, ratio * 100.0)

    @classmethod
    def _category_score(
        cls, offer: OpportunityDocument, demand: OpportunityDocument
    ) -> float:
        if cls._normalize_text(offer.category) == cls._normalize_text(demand.category):
            return 100.0
        return 0.0

    @classmethod
    def _technical_detail_score(
        cls, offer: OpportunityDocument, demand: OpportunityDocument
    ) -> float:
        return cls._text_similarity_score(
            offer.technical_detail, demand.technical_detail
        )

    @staticmethod
    def _purity_score(
        offer_purity: float | None, demand_purity: float | None
    ) -> float:
        if offer_purity is None and demand_purity is None:
            return 100.0
        if offer_purity is None or demand_purity is None:
            return 70.0
        return max(0.0, 100.0 - abs(offer_purity - demand_purity) * 2.0)

    @staticmethod
    def _location_score(
        offer: OpportunityDocument, demand: OpportunityDocument
    ) -> float:
        offer_city = offer.city.strip().lower()
        demand_city = demand.city.strip().lower()
        offer_state = offer.state.upper().strip()
        demand_state = demand.state.upper().strip()

        if offer_city == demand_city and offer_state == demand_state:
            return 100.0
        if offer_state == demand_state:
            return 80.0
        if are_neighboring_states(offer_state, demand_state):
            return 60.0
        return 30.0

    @staticmethod
    def _price_score(
        offer: OpportunityDocument, demand: OpportunityDocument
    ) -> float:
        offer_has_price = offer.price is not None and not offer.price_negotiable
        demand_has_price = demand.price is not None and not demand.price_negotiable

        if not offer_has_price and not demand_has_price:
            return 70.0
        if not offer_has_price or not demand_has_price:
            return 50.0

        assert offer.price is not None
        assert demand.price is not None
        if demand.price == 0:
            return 50.0

        diff_percent = abs(offer.price - demand.price) / demand.price * 100.0
        if diff_percent <= 5:
            return 100.0
        if diff_percent <= 10:
            return 90.0
        if diff_percent <= 20:
            return 70.0
        if diff_percent <= 30:
            return 40.0
        return 0.0

    @staticmethod
    def _quantity_score(
        offer: OpportunityDocument, demand: OpportunityDocument
    ) -> float:
        if offer.unit.strip().lower() != demand.unit.strip().lower():
            return 40.0
        max_qty = max(offer.quantity, demand.quantity, 1.0)
        diff_ratio = abs(offer.quantity - demand.quantity) / max_qty
        return max(0.0, 100.0 - diff_ratio * 100.0)

    @classmethod
    def _criterion_scores(
        cls, offer: OpportunityDocument, demand: OpportunityDocument
    ) -> _CriterionScores:
        return _CriterionScores(
            category=cls._category_score(offer, demand),
            technical_detail=cls._technical_detail_score(offer, demand),
            purity=cls._purity_score(offer.purity_percent, demand.purity_percent),
            physical_state=cls._text_similarity_score(
                offer.physical_state, demand.physical_state
            ),
            location=cls._location_score(offer, demand),
            quantity=cls._quantity_score(offer, demand),
            price=cls._price_score(offer, demand),
        )

    @staticmethod
    def _base_score(criteria: _CriterionScores) -> float:
        return (
            criteria.category * _CRITERION_WEIGHTS["category"]
            + criteria.technical_detail * _CRITERION_WEIGHTS["technical_detail"]
            + criteria.purity * _CRITERION_WEIGHTS["purity"]
            + criteria.physical_state * _CRITERION_WEIGHTS["physical_state"]
            + criteria.location * _CRITERION_WEIGHTS["location"]
            + criteria.quantity * _CRITERION_WEIGHTS["quantity"]
            + criteria.price * _CRITERION_WEIGHTS["price"]
        )

    @classmethod
    def _apply_compatibility_penalty(
        cls,
        base_score: float,
        offer: OpportunityDocument,
        demand: OpportunityDocument,
    ) -> float:
        categories_match = cls._normalize_text(offer.category) == cls._normalize_text(
            demand.category
        )
        details_match = cls._normalize_text(
            offer.technical_detail
        ) == cls._normalize_text(demand.technical_detail)

        score = base_score
        if not categories_match:
            score *= _CATEGORY_MISMATCH_FACTOR
            return min(score, _CATEGORY_MISMATCH_CAP)
        if not details_match:
            score *= _DETAIL_MISMATCH_FACTOR
            return min(score, _DETAIL_MISMATCH_CAP)
        return score

    @staticmethod
    def _classify_potential(score: int) -> MatchPotential:
        if score >= 80:
            return MatchPotential.HIGH
        if score >= 40:
            return MatchPotential.MEDIUM
        return MatchPotential.LOW

    @classmethod
    def calculate(
        cls,
        offer: OpportunityDocument,
        demand: OpportunityDocument,
        *,
        demand_response: OpportunityResponse,
    ) -> OpportunityMatch:
        criteria = cls._criterion_scores(offer, demand)
        base_score = cls._base_score(criteria)
        score = round(
            cls._apply_compatibility_penalty(base_score, offer, demand)
        )
        return OpportunityMatch(
            score=score,
            potential=cls._classify_potential(score),
            details=MatchDetails(
                category=round(criteria.category),
                technical_detail=round(criteria.technical_detail),
                purity=round(criteria.purity),
                physical_state=round(criteria.physical_state),
                location=round(criteria.location),
                quantity=round(criteria.quantity),
                price=round(criteria.price),
            ),
            matched_demand=demand_response,
        )

    @classmethod
    def find_best_match(
        cls,
        offer: OpportunityDocument,
        demands: list[OpportunityDocument],
        *,
        demand_responses: dict[str, OpportunityResponse],
    ) -> OpportunityMatch | None:
        if not demands:
            return None

        best: OpportunityMatch | None = None
        for demand in demands:
            demand_response = demand_responses.get(str(demand.id))
            if demand_response is None:
                continue
            match = cls.calculate(
                offer, demand, demand_response=demand_response
            )
            if best is None or match.score > best.score:
                best = match
        return best


__all__ = ["MatchingService"]
