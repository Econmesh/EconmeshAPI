"""Schemas for platform and user dashboard aggregates."""

from __future__ import annotations

from pydantic import Field

from src.shared.schemas.base import APIModel


class NamedCount(APIModel):
    key: str
    count: int
    label: str | None = None


class FunnelStage(APIModel):
    key: str
    label: str
    count: int


class TimeSeriesPoint(APIModel):
    date: str
    opportunities: int = 0
    conversations: int = 0
    proposals: int = 0
    agreements_signed: int = 0


class DashboardTotals(APIModel):
    users: int = 0
    companies: int = 0
    opportunities: int = 0
    opportunities_active: int = 0
    conversations: int = 0
    conversations_open: int = 0
    proposals: int = 0
    proposals_pending: int = 0
    agreements: int = 0
    agreements_pending: int = 0
    agreements_signed: int = 0
    support_open: int = 0


class DashboardActionItem(APIModel):
    kind: str
    title: str
    href: str
    meta: str | None = None


class AdminDashboardResponse(APIModel):
    totals: DashboardTotals
    funnel: list[FunnelStage] = Field(default_factory=list)
    agreements_by_status: list[NamedCount] = Field(default_factory=list)
    proposals_by_status: list[NamedCount] = Field(default_factory=list)
    opportunities_by_type: list[NamedCount] = Field(default_factory=list)
    opportunities_by_offer_demand: list[NamedCount] = Field(default_factory=list)
    opportunities_by_state: list[NamedCount] = Field(default_factory=list)
    support_by_status: list[NamedCount] = Field(default_factory=list)
    timeseries: list[TimeSeriesPoint] = Field(default_factory=list)
    estimated_gmv: float = 0.0
    opportunities_with_price: int = 0
    opportunities_price_negotiable: int = 0
    days: int = 30


class UserDashboardResponse(APIModel):
    totals: DashboardTotals
    funnel: list[FunnelStage] = Field(default_factory=list)
    agreements_by_status: list[NamedCount] = Field(default_factory=list)
    proposals_by_status: list[NamedCount] = Field(default_factory=list)
    opportunities_by_type: list[NamedCount] = Field(default_factory=list)
    opportunities_by_offer_demand: list[NamedCount] = Field(default_factory=list)
    timeseries: list[TimeSeriesPoint] = Field(default_factory=list)
    estimated_gmv: float = 0.0
    action_items: list[DashboardActionItem] = Field(default_factory=list)
    days: int = 30


__all__ = [
    "AdminDashboardResponse",
    "DashboardActionItem",
    "DashboardTotals",
    "FunnelStage",
    "NamedCount",
    "TimeSeriesPoint",
    "UserDashboardResponse",
]
