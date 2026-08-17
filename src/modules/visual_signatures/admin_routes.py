"""Admin read-only routes for user visual signatures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from src.modules.visual_signatures.deps import build_visual_signatures_service
from src.modules.visual_signatures.schema import VisualSignaturesBundleResponse
from src.modules.visual_signatures.service import VisualSignaturesService
from src.shared.constants.roles import Role
from src.shared.dependencies.db import get_db
from src.shared.dependencies.rbac import require_role

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

router = APIRouter(
    prefix="/admin/users",
    tags=["admin-visual-signatures"],
    dependencies=[Depends(require_role(Role.ADMIN))],
)


def _build_service(
    db: Annotated["AsyncDatabase", Depends(get_db)],
) -> VisualSignaturesService:
    return build_visual_signatures_service(db)


ServiceDep = Annotated[VisualSignaturesService, Depends(_build_service)]


@router.get(
    "/{user_id}/visual-signatures",
    response_model=VisualSignaturesBundleResponse,
    summary="Read a user's confirmed visual signature and rubric.",
)
async def list_user_visual_signatures(
    user_id: UUID, service: ServiceDep
) -> VisualSignaturesBundleResponse:
    return await service.list_for_user(user_id)


@router.get(
    "/{user_id}/visual-signatures/{signature_id}/image",
    summary="Download a user's visual signature PNG.",
    response_class=Response,
)
async def get_user_visual_signature_image(
    user_id: UUID,
    signature_id: UUID,
    service: ServiceDep,
) -> Response:
    data = await service.image_bytes(
        signature_id, is_admin=True, expected_user_id=user_id
    )
    return Response(content=data, media_type="image/png")


__all__ = ["router"]
