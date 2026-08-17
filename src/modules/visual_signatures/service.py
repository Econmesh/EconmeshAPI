"""Business rules for visual signatures and rubrics."""

from __future__ import annotations

import base64
from uuid import UUID

from fastapi import UploadFile

from src.core.crypto import decrypt_string, encrypt_string
from src.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationAppError,
)
from src.core.firebase import firebase
from src.modules.auth.repository import AuthRepository
from src.modules.visual_signatures.fonts import get_font, list_fonts
from src.modules.visual_signatures.initials import initials_options, resolve_initials_text
from src.modules.visual_signatures.model import (
    GENERATION_VERSION,
    VisualSignatureDocument,
    VisualSignatureEventDocument,
    VisualSignatureEventType,
    VisualSignatureKind,
    VisualSignatureSource,
)
from src.modules.visual_signatures.renderer import (
    process_manual_png,
    render_automatic,
    sha256_bytes,
)
from src.modules.visual_signatures.repository import (
    VisualSignatureEventsRepository,
    VisualSignaturesRepository,
)
from src.modules.visual_signatures.schema import (
    FontOptionResponse,
    InitialsOptionResponse,
    VisualSignatureConfirmRequest,
    VisualSignaturePreviewRequest,
    VisualSignaturePreviewResponse,
    VisualSignatureResponse,
    VisualSignaturesBundleResponse,
)
from src.modules.visual_signatures.uniqueness import uniqueness_hmac
from src.shared.utils.ids import new_uuid
from src.shared.utils.storage_keys import signature_storage_key
from src.shared.utils.time import utcnow

_MAX_MANUAL_BYTES = 1024 * 1024
_ALLOWED_MANUAL_TYPES = {"image/png"}


class VisualSignaturesService:
    def __init__(
        self,
        repository: VisualSignaturesRepository,
        events_repository: VisualSignatureEventsRepository,
        auth_repository: AuthRepository,
    ) -> None:
        self._repo = repository
        self._events = events_repository
        self._auth_repo = auth_repository

    async def _resolve_user(self, firebase_uid: str):
        user = await self._auth_repo.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user

    async def list_fonts(self) -> list[FontOptionResponse]:
        return [FontOptionResponse(id=font.id, name=font.name) for font in list_fonts()]

    async def initials_options(self, firebase_uid: str) -> list[InitialsOptionResponse]:
        user = await self._resolve_user(firebase_uid)
        name = (user.name or "").strip()
        if not name:
            raise ValidationAppError(
                "Preencha o nome completo no perfil para gerar a rúbrica.",
                code="profile_name_required",
            )
        return [
            InitialsOptionResponse(id=item["id"], label=item["label"], text=item["text"])
            for item in initials_options(name)
        ]

    async def list_mine(self, firebase_uid: str) -> VisualSignaturesBundleResponse:
        user = await self._resolve_user(firebase_uid)
        return await self.list_for_user(user.id)

    async def list_for_user(self, user_id: UUID) -> VisualSignaturesBundleResponse:
        docs = await self._repo.list_for_user(user_id)
        signature = next(
            (doc for doc in docs if doc.kind == VisualSignatureKind.SIGNATURE), None
        )
        initials = next(
            (doc for doc in docs if doc.kind == VisualSignatureKind.INITIALS), None
        )
        return VisualSignaturesBundleResponse(
            signature=self._to_response(signature) if signature else None,
            initials=self._to_response(initials) if initials else None,
        )

    async def preview(
        self,
        payload: VisualSignaturePreviewRequest,
        *,
        firebase_uid: str,
    ) -> VisualSignaturePreviewResponse:
        user = await self._resolve_user(firebase_uid)
        get_font(payload.font_id)
        source_text = self._source_text(user.name, payload.kind, payload.text_variant)
        hmac_value = uniqueness_hmac(payload.kind, source_text, payload.font_id)
        unique = not await self._repo.uniqueness_taken(hmac_value)
        kind = VisualSignatureKind(payload.kind)
        rendered = render_automatic(
            source_text,
            font_id=payload.font_id,
            kind=kind,
            user_id=user.id,
            signature_id=new_uuid(),
            created_at=utcnow(),
        )
        return VisualSignaturePreviewResponse(
            unique=unique,
            kind=payload.kind,
            font_id=payload.font_id,
            source_text=source_text,
            image_base64=base64.b64encode(rendered.data).decode("ascii"),
            width=rendered.width,
            height=rendered.height,
        )

    async def confirm_automatic(
        self,
        payload: VisualSignatureConfirmRequest,
        *,
        firebase_uid: str,
        ip: str | None,
        user_agent: str | None,
    ) -> VisualSignatureResponse:
        user = await self._resolve_user(firebase_uid)
        kind = VisualSignatureKind(payload.kind)
        await self._ensure_kind_available(user.id, kind)
        get_font(payload.font_id)
        source_text = self._source_text(user.name, kind, payload.text_variant)
        hmac_value = uniqueness_hmac(kind, source_text, payload.font_id)
        if await self._repo.uniqueness_taken(hmac_value):
            raise ConflictError(
                "Já existe uma assinatura gerada com esta combinação de "
                "caracteres e fonte.",
                code="visual_signature_not_unique",
            )
        signature_id = new_uuid()
        created_at = utcnow()
        rendered = render_automatic(
            source_text,
            font_id=payload.font_id,
            kind=kind,
            user_id=user.id,
            signature_id=signature_id,
            created_at=created_at,
        )
        doc = await self._persist(
            signature_id=signature_id,
            user_id=user.id,
            kind=kind,
            source=VisualSignatureSource.AUTOMATIC,
            font_id=payload.font_id,
            source_text=source_text,
            uniqueness_hmac_value=hmac_value,
            rendered=rendered,
            created_at=created_at,
            ip=ip,
            user_agent=user_agent,
        )
        return self._to_response(doc)

    async def confirm_manual(
        self,
        *,
        kind: VisualSignatureKind,
        file: UploadFile,
        firebase_uid: str,
        ip: str | None,
        user_agent: str | None,
    ) -> VisualSignatureResponse:
        user = await self._resolve_user(firebase_uid)
        await self._ensure_kind_available(user.id, kind)
        content_type = (file.content_type or "").lower()
        if content_type not in _ALLOWED_MANUAL_TYPES:
            raise ConflictError("Envie a assinatura em PNG.", code="invalid_content_type")
        raw = await file.read()
        if not raw:
            raise ConflictError("Arquivo vazio.", code="empty_file")
        if len(raw) > _MAX_MANUAL_BYTES:
            raise ConflictError("A imagem excede 1 MB.", code="file_too_large")
        signature_id = new_uuid()
        created_at = utcnow()
        try:
            rendered = process_manual_png(
                raw,
                kind=kind,
                user_id=user.id,
                signature_id=signature_id,
                created_at=created_at,
            )
        except ValueError as exc:
            raise ValidationAppError(
                "Não foi possível ler a imagem da assinatura.",
                code="invalid_signature_image",
            ) from exc
        source_text = (user.name or "").strip()
        doc = await self._persist(
            signature_id=signature_id,
            user_id=user.id,
            kind=kind,
            source=VisualSignatureSource.MANUAL,
            font_id=None,
            source_text=source_text,
            uniqueness_hmac_value=None,
            rendered=rendered,
            created_at=created_at,
            ip=ip,
            user_agent=user_agent,
        )
        return self._to_response(doc)

    async def load_png_for_user(
        self,
        user_id: UUID,
        kind: VisualSignatureKind,
        *,
        agreement_id: UUID | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[VisualSignatureDocument, bytes]:
        doc = await self._repo.get_for_user(user_id, kind)
        if doc is None:
            raise ValidationAppError(
                "Crie sua assinatura visual no perfil antes de assinar o acordo.",
                code="visual_signature_required",
                details={"kind": kind.value},
            )
        data = await self._load_and_verify(
            doc, ip=ip, user_agent=user_agent, agreement_id=agreement_id
        )
        if agreement_id is not None:
            await self._events.create(
                VisualSignatureEventDocument(
                    signature_id=doc.id,
                    user_id=doc.user_id,
                    event_type=VisualSignatureEventType.USED_IN_AGREEMENT,
                    ip=ip,
                    user_agent=user_agent,
                    metadata={"agreement_id": str(agreement_id)},
                )
            )
        return doc, data

    async def image_bytes(
        self,
        signature_id: UUID,
        *,
        firebase_uid: str | None = None,
        actor_user_id: UUID | None = None,
        is_admin: bool = False,
        expected_user_id: UUID | None = None,
    ) -> bytes:
        doc = await self._repo.get(signature_id)
        if doc is None:
            raise NotFoundError("Assinatura não encontrada.")
        if is_admin:
            if expected_user_id is not None and doc.user_id != expected_user_id:
                raise NotFoundError("Assinatura não encontrada.")
        elif actor_user_id is not None:
            if doc.user_id != actor_user_id:
                raise ForbiddenError()
        elif firebase_uid:
            user = await self._resolve_user(firebase_uid)
            if doc.user_id != user.id:
                raise ForbiddenError()
        else:
            raise ForbiddenError()
        return await self._load_and_verify(doc)

    async def _load_and_verify(
        self,
        doc: VisualSignatureDocument,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
        agreement_id: UUID | None = None,
    ) -> bytes:
        data = await firebase.download_storage_bytes(doc.storage_key)
        digest = sha256_bytes(data)
        if digest != doc.sha256:
            metadata = {"stored_sha256": doc.sha256, "computed_sha256": digest}
            if agreement_id is not None:
                metadata["agreement_id"] = str(agreement_id)
            await self._events.create(
                VisualSignatureEventDocument(
                    signature_id=doc.id,
                    user_id=doc.user_id,
                    event_type=VisualSignatureEventType.INTEGRITY_FAILED,
                    ip=ip,
                    user_agent=user_agent,
                    metadata=metadata,
                )
            )
            raise ConflictError(
                "A imagem da assinatura foi alterada e não pode ser utilizada.",
                code="visual_signature_integrity_failed",
            )
        return data

    async def _ensure_kind_available(
        self, user_id: UUID, kind: VisualSignatureKind
    ) -> None:
        existing = await self._repo.get_for_user(user_id, kind)
        if existing is not None:
            raise ConflictError(
                "Você já possui este tipo de assinatura confirmada.",
                code="visual_signature_already_exists",
            )

    def _source_text(
        self,
        name: str | None,
        kind: VisualSignatureKind,
        text_variant: str | None,
    ) -> str:
        full_name = (name or "").strip()
        if not full_name:
            raise ValidationAppError(
                "Preencha o nome completo no perfil para gerar a assinatura.",
                code="profile_name_required",
            )
        if kind == VisualSignatureKind.SIGNATURE:
            return full_name
        variant = text_variant or "all_initials"
        try:
            return resolve_initials_text(full_name, variant)
        except ValueError as exc:
            raise ValidationAppError(
                "Variante de rúbrica inválida.",
                code="invalid_initials_variant",
            ) from exc

    async def _persist(
        self,
        *,
        signature_id: UUID,
        user_id: UUID,
        kind: VisualSignatureKind,
        source: VisualSignatureSource,
        font_id: str | None,
        source_text: str,
        uniqueness_hmac_value: str | None,
        rendered,
        created_at,
        ip: str | None,
        user_agent: str | None,
    ) -> VisualSignatureDocument:
        storage_key = signature_storage_key(user_id, "png")
        await firebase.upload_storage_bytes(
            storage_key,
            rendered.data,
            content_type=rendered.content_type,
        )
        doc = VisualSignatureDocument(
            id=signature_id,
            user_id=user_id,
            kind=kind,
            source=source,
            font_id=font_id,
            source_text_enc=encrypt_string(source_text),
            uniqueness_hmac=uniqueness_hmac_value,
            storage_key=storage_key,
            sha256=rendered.sha256,
            content_type=rendered.content_type,
            width=rendered.width,
            height=rendered.height,
            generation_version=GENERATION_VERSION,
            ip=ip,
            user_agent=user_agent,
            created_at=created_at,
            updated_at=created_at,
        )
        saved = await self._repo.create(doc)
        await self._events.create(
            VisualSignatureEventDocument(
                signature_id=saved.id,
                user_id=user_id,
                event_type=VisualSignatureEventType.CREATED,
                ip=ip,
                user_agent=user_agent,
                metadata={
                    "kind": kind.value,
                    "source": source.value,
                    "sha256": saved.sha256,
                },
            )
        )
        return saved

    @staticmethod
    def _to_response(doc: VisualSignatureDocument) -> VisualSignatureResponse:
        return VisualSignatureResponse(
            id=doc.id,
            kind=doc.kind,
            source=doc.source,
            font_id=doc.font_id,
            source_text=decrypt_string(doc.source_text_enc),
            sha256=doc.sha256,
            width=doc.width,
            height=doc.height,
            generation_version=doc.generation_version,
            created_at=doc.created_at,
        )


__all__ = ["VisualSignaturesService"]
