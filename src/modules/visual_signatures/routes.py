"""Authenticated routes for the current user's visual signatures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import Response

from src.modules.visual_signatures.deps import build_visual_signatures_service
from src.modules.visual_signatures.model import VisualSignatureKind
from src.modules.visual_signatures.schema import (
    FontOptionResponse,
    InitialsOptionResponse,
    VisualSignatureConfirmRequest,
    VisualSignaturePreviewRequest,
    VisualSignaturePreviewResponse,
    VisualSignatureResponse,
    VisualSignaturesBundleResponse,
)
from src.modules.visual_signatures.service import VisualSignaturesService
from src.shared.dependencies.auth import CurrentUserDep
from src.shared.dependencies.db import get_db

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(prefix="/users/me/visual-signatures", tags=["visual-signatures"])


def _build_service(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> VisualSignaturesService:
    return build_visual_signatures_service(db)


ServiceDep = Annotated[VisualSignaturesService, Depends(_build_service)]


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    forwarded = request.headers.get("x-forwarded-for")
    ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else None)
    )
    return ip, request.headers.get("user-agent")


@router.get(
    "",
    response_model=VisualSignaturesBundleResponse,
    summary="List the current user's confirmed visual signature and rubric.",
)
async def list_mine(
    service: ServiceDep, current_user: CurrentUserDep
) -> VisualSignaturesBundleResponse:
    return await service.list_mine(current_user.uid)


@router.get(
    "/fonts",
    response_model=list[FontOptionResponse],
    summary="List fonts available for automatic generation.",
)
async def list_fonts(
    service: ServiceDep, _current_user: CurrentUserDep
) -> list[FontOptionResponse]:
    return await service.list_fonts()


@router.get(
    "/initials-options",
    response_model=list[InitialsOptionResponse],
    summary="List rubric text variants derived from the profile name.",
)
async def list_initials_options(
    service: ServiceDep, current_user: CurrentUserDep
) -> list[InitialsOptionResponse]:
    return await service.initials_options(current_user.uid)


@router.post(
    "/preview",
    response_model=VisualSignaturePreviewResponse,
    summary="Preview an automatic signature or rubric without persisting it.",
)
async def preview(
    payload: VisualSignaturePreviewRequest,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> VisualSignaturePreviewResponse:
    return await service.preview(payload, firebase_uid=current_user.uid)


@router.post(
    "/automatic",
    response_model=VisualSignatureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm and store an automatically generated signature or rubric.",
)
async def confirm_automatic(
    payload: VisualSignatureConfirmRequest,
    request: Request,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> VisualSignatureResponse:
    ip, user_agent = _client_meta(request)
    return await service.confirm_automatic(
        payload,
        firebase_uid=current_user.uid,
        ip=ip,
        user_agent=user_agent,
    )


@router.post(
    "/manual",
    response_model=VisualSignatureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm and store a hand-drawn signature or rubric.",
)
async def confirm_manual(
    request: Request,
    service: ServiceDep,
    current_user: CurrentUserDep,
    kind: Annotated[VisualSignatureKind, Form()],
    file: UploadFile = File(...),
) -> VisualSignatureResponse:
    ip, user_agent = _client_meta(request)
    return await service.confirm_manual(
        kind=kind,
        file=file,
        firebase_uid=current_user.uid,
        ip=ip,
        user_agent=user_agent,
    )


@router.get(
    "/{signature_id}/image",
    summary="Download the immutable PNG for a confirmed signature or rubric.",
    response_class=Response,
)
async def get_image(
    signature_id: UUID,
    service: ServiceDep,
    current_user: CurrentUserDep,
) -> Response:
    data = await service.image_bytes(signature_id, firebase_uid=current_user.uid)
    return Response(content=data, media_type="image/png")


__all__ = ["router"]
