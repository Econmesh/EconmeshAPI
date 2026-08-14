"""Business logic assembling dashboard payloads."""

from __future__ import annotations

import asyncio
from uuid import UUID

from src.core.exceptions import NotFoundError
from src.modules.agreements.model import AgreementStatus
from src.modules.auth.repository import AuthRepository
from src.modules.contract_proposals.model import ContractProposalStatus
from src.modules.conversations.model import ConversationStatus
from src.modules.dashboard.labels import (
    AGREEMENT_STATUS_LABELS,
    OFFER_DEMAND_LABELS,
    OPPORTUNITY_TYPE_LABELS,
    PENDING_AGREEMENT_STATUSES,
    PROPOSAL_STATUS_LABELS,
    SUPPORT_STATUS_LABELS,
)
from src.modules.dashboard.repository import DashboardRepository
from src.modules.dashboard.schema import (
    AdminDashboardResponse,
    DashboardActionItem,
    DashboardTotals,
    FunnelStage,
    NamedCount,
    TimeSeriesPoint,
    UserDashboardResponse,
)
from src.modules.support.model import SupportTicketStatus


class DashboardService:
    def __init__(
        self,
        repository: DashboardRepository,
        auth_repository: AuthRepository,
    ) -> None:
        self._repo = repository
        self._auth_repo = auth_repository

    async def _resolve_user_id(self, firebase_uid: str) -> UUID:
        user = await self._auth_repo.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user.id

    @staticmethod
    def _named(
        rows: list[tuple[str, int]],
        labels: dict[str, str],
    ) -> list[NamedCount]:
        return [
            NamedCount(key=key, count=count, label=labels.get(key, key))
            for key, count in rows
        ]

    async def get_admin_dashboard(self, *, days: int = 30) -> AdminDashboardResponse:
        days = max(7, min(days, 90))
        base_opp = {"is_active": True}
        base_conv = {"is_active": True}
        base_prop = {"is_active": True}
        base_agr = {"is_active": True}

        (
            users,
            companies,
            opportunities,
            opportunities_active,
            conversations,
            conversations_open,
            proposals,
            proposals_pending,
            agreements,
            agreements_pending,
            agreements_signed,
            support_open,
            by_agr_status,
            by_prop_status,
            by_opp_type,
            by_offer_demand,
            by_state,
            by_support,
            gmv_tuple,
            series,
        ) = await asyncio.gather(
            self._repo.count_users({"is_active": True}),
            self._repo.count_companies({"is_active": True}),
            self._repo.count_opportunities({}),
            self._repo.count_opportunities(base_opp),
            self._repo.count_conversations({}),
            self._repo.count_conversations(
                {**base_conv, "status": ConversationStatus.OPEN.value}
            ),
            self._repo.count_proposals({}),
            self._repo.count_proposals(
                {
                    **base_prop,
                    "status": ContractProposalStatus.PENDING_APPROVAL.value,
                }
            ),
            self._repo.count_agreements({}),
            self._repo.count_agreements(
                {
                    **base_agr,
                    "status": {"$in": list(PENDING_AGREEMENT_STATUSES)},
                }
            ),
            self._repo.count_agreements(
                {**base_agr, "status": AgreementStatus.SIGNED.value}
            ),
            self._repo.count_support(
                {
                    "status": {
                        "$in": [
                            SupportTicketStatus.OPEN.value,
                            SupportTicketStatus.IN_PROGRESS.value,
                        ]
                    }
                }
            ),
            self._repo.group_agreements_by(base_agr, "status"),
            self._repo.group_proposals_by(base_prop, "status"),
            self._repo.group_opportunities_by(base_opp, "opportunity_type"),
            self._repo.group_opportunities_by(base_opp, "offer_demand"),
            self._repo.group_opportunities_by(base_opp, "state", limit=10),
            self._repo.group_support_by({}, "status"),
            self._repo.opportunity_gmv(base_opp),
            self._repo.daily_series(
                days=days,
                opportunity_match=base_opp,
                conversation_match=base_conv,
                proposal_match=base_prop,
                agreement_match=base_agr,
            ),
        )

        estimated_gmv, with_price, negotiable = gmv_tuple

        funnel = [
            FunnelStage(key="opportunities", label="Oportunidades", count=opportunities_active),
            FunnelStage(key="conversations", label="Conversas", count=conversations),
            FunnelStage(key="proposals", label="Minutas", count=proposals),
            FunnelStage(
                key="agreements_pending",
                label="Acordos em andamento",
                count=agreements_pending,
            ),
            FunnelStage(
                key="agreements_signed",
                label="Acordos assinados",
                count=agreements_signed,
            ),
        ]

        return AdminDashboardResponse(
            totals=DashboardTotals(
                users=users,
                companies=companies,
                opportunities=opportunities,
                opportunities_active=opportunities_active,
                conversations=conversations,
                conversations_open=conversations_open,
                proposals=proposals,
                proposals_pending=proposals_pending,
                agreements=agreements,
                agreements_pending=agreements_pending,
                agreements_signed=agreements_signed,
                support_open=support_open,
            ),
            funnel=funnel,
            agreements_by_status=self._named(by_agr_status, AGREEMENT_STATUS_LABELS),
            proposals_by_status=self._named(by_prop_status, PROPOSAL_STATUS_LABELS),
            opportunities_by_type=self._named(by_opp_type, OPPORTUNITY_TYPE_LABELS),
            opportunities_by_offer_demand=self._named(
                by_offer_demand, OFFER_DEMAND_LABELS
            ),
            opportunities_by_state=[
                NamedCount(key=k, count=c, label=k) for k, c in by_state
            ],
            support_by_status=self._named(by_support, SUPPORT_STATUS_LABELS),
            timeseries=[TimeSeriesPoint.model_validate(p) for p in series],
            estimated_gmv=round(estimated_gmv, 2),
            opportunities_with_price=with_price,
            opportunities_price_negotiable=negotiable,
            days=days,
        )

    async def get_user_dashboard(
        self, *, firebase_uid: str, days: int = 30
    ) -> UserDashboardResponse:
        days = max(7, min(days, 90))
        user_id = await self._resolve_user_id(firebase_uid)
        company_ids = await self._repo.list_company_ids_for_owner(user_id)

        opp_match = self._repo.user_opportunity_match(user_id, company_ids)
        conv_match = self._repo.user_conversation_match(user_id)
        prop_match = self._repo.user_proposal_match(user_id)
        agr_match = self._repo.user_agreement_match(user_id, company_ids)
        support_match = {"user_id": user_id}

        (
            companies,
            opportunities_active,
            conversations,
            conversations_open,
            proposals,
            proposals_pending,
            agreements,
            agreements_pending,
            agreements_signed,
            support_open,
            by_agr_status,
            by_prop_status,
            by_opp_type,
            by_offer_demand,
            gmv_tuple,
            series,
            pending_props,
            pending_agrs,
            open_convs,
        ) = await asyncio.gather(
            self._repo.count_companies(
                {"owner_user_id": user_id, "is_active": True}
            ),
            self._repo.count_opportunities(opp_match),
            self._repo.count_conversations(conv_match),
            self._repo.count_conversations(
                {**conv_match, "status": ConversationStatus.OPEN.value}
            ),
            self._repo.count_proposals(prop_match),
            self._repo.count_proposals(
                {
                    **prop_match,
                    "status": ContractProposalStatus.PENDING_APPROVAL.value,
                }
            ),
            self._repo.count_agreements(agr_match),
            self._repo.count_agreements(
                {
                    **agr_match,
                    "status": {"$in": list(PENDING_AGREEMENT_STATUSES)},
                }
            ),
            self._repo.count_agreements(
                {**agr_match, "status": AgreementStatus.SIGNED.value}
            ),
            self._repo.count_support(
                {
                    **support_match,
                    "status": {
                        "$in": [
                            SupportTicketStatus.OPEN.value,
                            SupportTicketStatus.IN_PROGRESS.value,
                        ]
                    },
                }
            ),
            self._repo.group_agreements_by(agr_match, "status"),
            self._repo.group_proposals_by(prop_match, "status"),
            self._repo.group_opportunities_by(opp_match, "opportunity_type"),
            self._repo.group_opportunities_by(opp_match, "offer_demand"),
            self._repo.opportunity_gmv(opp_match),
            self._repo.daily_series(
                days=days,
                opportunity_match=opp_match,
                conversation_match=conv_match,
                proposal_match=prop_match,
                agreement_match=agr_match,
            ),
            self._repo.list_pending_proposals_for_user(user_id),
            self._repo.list_pending_agreements_for_user(user_id, company_ids),
            self._repo.list_open_conversations_for_user(user_id),
        )

        estimated_gmv, _, _ = gmv_tuple

        funnel = [
            FunnelStage(
                key="opportunities",
                label="Oportunidades",
                count=opportunities_active,
            ),
            FunnelStage(key="conversations", label="Conversas", count=conversations),
            FunnelStage(key="proposals", label="Minutas", count=proposals),
            FunnelStage(
                key="agreements_pending",
                label="Acordos em andamento",
                count=agreements_pending,
            ),
            FunnelStage(
                key="agreements_signed",
                label="Acordos assinados",
                count=agreements_signed,
            ),
        ]

        action_items: list[DashboardActionItem] = []
        for doc in pending_props:
            action_items.append(
                DashboardActionItem(
                    kind="proposal",
                    title=str(doc.get("title") or "Minuta pendente"),
                    href=f"/dashboard/minutas/{doc['_id']}",
                    meta="Aguardando aprovação",
                )
            )
        for doc in pending_agrs:
            status = str(doc.get("status") or "")
            action_items.append(
                DashboardActionItem(
                    kind="agreement",
                    title=str(doc.get("title") or "Acordo pendente"),
                    href=f"/dashboard/acordos/{doc['_id']}",
                    meta=AGREEMENT_STATUS_LABELS.get(status, status),
                )
            )
        for doc in open_convs:
            action_items.append(
                DashboardActionItem(
                    kind="conversation",
                    title=str(doc.get("opportunity_title") or "Conversa aberta"),
                    href=f"/dashboard/conversas/{doc['_id']}",
                    meta="Conversa aberta",
                )
            )

        return UserDashboardResponse(
            totals=DashboardTotals(
                companies=companies,
                opportunities_active=opportunities_active,
                opportunities=opportunities_active,
                conversations=conversations,
                conversations_open=conversations_open,
                proposals=proposals,
                proposals_pending=proposals_pending,
                agreements=agreements,
                agreements_pending=agreements_pending,
                agreements_signed=agreements_signed,
                support_open=support_open,
            ),
            funnel=funnel,
            agreements_by_status=self._named(by_agr_status, AGREEMENT_STATUS_LABELS),
            proposals_by_status=self._named(by_prop_status, PROPOSAL_STATUS_LABELS),
            opportunities_by_type=self._named(by_opp_type, OPPORTUNITY_TYPE_LABELS),
            opportunities_by_offer_demand=self._named(
                by_offer_demand, OFFER_DEMAND_LABELS
            ),
            timeseries=[TimeSeriesPoint.model_validate(p) for p in series],
            estimated_gmv=round(estimated_gmv, 2),
            action_items=action_items[:12],
            days=days,
        )


__all__ = ["DashboardService"]
