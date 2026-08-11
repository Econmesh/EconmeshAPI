"""HTTP controller for contract proposals."""

from __future__ import annotations

from uuid import UUID

from src.modules.contract_proposals.schema import (
    ApproveProposalResponse,
    ContractProposalCreate,
    ContractProposalListParams,
    ContractProposalListResponse,
    ContractProposalResponse,
    ContractProposalUpdate,
    RejectProposalRequest,
    RequestChangesRequest,
)
from src.modules.contract_proposals.service import ContractProposalsService
from src.shared.dependencies.auth import CurrentUser


class ContractProposalsController:
    def __init__(self, service: ContractProposalsService) -> None:
        self._service = service

    async def create(
        self, payload: ContractProposalCreate, current_user: CurrentUser
    ) -> ContractProposalResponse:
        return await self._service.create(payload, firebase_uid=current_user.uid)

    async def list(
        self, params: ContractProposalListParams, current_user: CurrentUser
    ) -> ContractProposalListResponse:
        return await self._service.list(params, firebase_uid=current_user.uid)

    async def get(
        self, proposal_id: UUID, current_user: CurrentUser
    ) -> ContractProposalResponse:
        return await self._service.get(proposal_id, firebase_uid=current_user.uid)

    async def update(
        self,
        proposal_id: UUID,
        payload: ContractProposalUpdate,
        current_user: CurrentUser,
    ) -> ContractProposalResponse:
        return await self._service.update(
            proposal_id, payload, firebase_uid=current_user.uid
        )

    async def generate_pdf(
        self, proposal_id: UUID, current_user: CurrentUser
    ) -> ContractProposalResponse:
        return await self._service.generate_pdf(
            proposal_id, firebase_uid=current_user.uid
        )

    async def approve(
        self, proposal_id: UUID, current_user: CurrentUser
    ) -> ApproveProposalResponse:
        return await self._service.approve(proposal_id, firebase_uid=current_user.uid)

    async def request_changes(
        self,
        proposal_id: UUID,
        payload: RequestChangesRequest,
        current_user: CurrentUser,
    ) -> ContractProposalResponse:
        return await self._service.request_changes(
            proposal_id, payload, firebase_uid=current_user.uid
        )

    async def reject(
        self,
        proposal_id: UUID,
        payload: RejectProposalRequest,
        current_user: CurrentUser,
    ) -> ContractProposalResponse:
        return await self._service.reject(
            proposal_id, payload, firebase_uid=current_user.uid
        )

    async def admin_list(
        self,
        *,
        page: int,
        page_size: int,
        conversation_id: UUID | None = None,
    ) -> ContractProposalListResponse:
        return await self._service.admin_list(
            page=page, page_size=page_size, conversation_id=conversation_id
        )

    async def admin_get(self, proposal_id: UUID) -> ContractProposalResponse:
        return await self._service.admin_get(proposal_id)


__all__ = ["ContractProposalsController"]
