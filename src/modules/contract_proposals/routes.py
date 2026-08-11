"""Routes for contract proposals (minutas)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.modules.contract_proposals.controller import ContractProposalsController
from src.modules.contract_proposals.deps import build_contract_proposals_controller
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
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db
from src.shared.dependencies.redis import get_redis

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase
    from redis.asyncio import Redis

router = APIRouter(prefix="/contract-proposals", tags=["contract-proposals"])


def _build_controller(
    db: Annotated["AsyncDatabase", Depends(get_db)],
    redis: Annotated["Redis", Depends(get_redis)],
) -> ContractProposalsController:
    return build_contract_proposals_controller(db, redis)


ControllerDep = Annotated[ContractProposalsController, Depends(_build_controller)]


@router.post(
    "",
    response_model=ContractProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a contract proposal from an opportunity conversation.",
)
async def create_proposal(
    payload: ContractProposalCreate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ContractProposalResponse:
    return await controller.create(payload, current_user)


@router.get(
    "",
    response_model=ContractProposalListResponse,
    summary="List contract proposals for the current user.",
)
async def list_proposals(
    controller: ControllerDep,
    current_user: CurrentUserDep,
    params: Annotated[ContractProposalListParams, Depends(ContractProposalListParams.as_query)],
) -> ContractProposalListResponse:
    return await controller.list(params, current_user)


@router.get(
    "/{proposal_id}",
    response_model=ContractProposalResponse,
    summary="Get a contract proposal.",
)
async def get_proposal(
    proposal_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ContractProposalResponse:
    return await controller.get(proposal_id, current_user)


@router.patch(
    "/{proposal_id}",
    response_model=ContractProposalResponse,
    summary="Update a draft contract proposal.",
)
async def update_proposal(
    proposal_id: UUID,
    payload: ContractProposalUpdate,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ContractProposalResponse:
    return await controller.update(proposal_id, payload, current_user)


@router.post(
    "/{proposal_id}/generate-pdf",
    response_model=ContractProposalResponse,
    summary="Generate PDF and submit for approval.",
)
async def generate_pdf(
    proposal_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ContractProposalResponse:
    return await controller.generate_pdf(proposal_id, current_user)


@router.post(
    "/{proposal_id}/approve",
    response_model=ApproveProposalResponse,
    summary="Approve proposal and create an agreement.",
)
async def approve_proposal(
    proposal_id: UUID,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ApproveProposalResponse:
    return await controller.approve(proposal_id, current_user)


@router.post(
    "/{proposal_id}/request-changes",
    response_model=ContractProposalResponse,
    summary="Request changes on a pending proposal.",
)
async def request_changes(
    proposal_id: UUID,
    payload: RequestChangesRequest,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ContractProposalResponse:
    return await controller.request_changes(proposal_id, payload, current_user)


@router.post(
    "/{proposal_id}/reject",
    response_model=ContractProposalResponse,
    summary="Reject a pending proposal.",
)
async def reject_proposal(
    proposal_id: UUID,
    payload: RejectProposalRequest,
    controller: ControllerDep,
    current_user: CurrentUserDep,
) -> ContractProposalResponse:
    return await controller.reject(proposal_id, payload, current_user)
