"""Business rules for ``users``."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from src.core.exceptions import ConflictError, NotFoundError
from src.core.firebase import firebase
from src.modules.auth.model import UserDocument
from src.modules.auth.repository import AuthRepository
from src.modules.users.model import UserProfileAddress, UserProfileDocument
from src.modules.users.repository import UsersRepository
from src.modules.users.schema import (
    AvatarPresignRequest,
    AvatarPresignResponse,
    ProfileAddressResponse,
    UserProfileResponse,
    UserProfileUpdate,
)
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

_ALLOWED_AVATAR_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


class UsersService:
    def __init__(
        self,
        repository: UsersRepository,
        auth_repository: AuthRepository,
    ) -> None:
        self._repo = repository
        self._auth_repo = auth_repository

    async def _resolve_user(self, firebase_uid: str) -> UserDocument:
        user = await self._auth_repo.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user

    @staticmethod
    def _picture_url(user: UserDocument, profile: UserProfileDocument | None) -> str | None:
        if profile is not None and profile.picture_url:
            return profile.picture_url
        return user.picture

    @staticmethod
    def _is_profile_complete(
        user: UserDocument, profile: UserProfileDocument | None
    ) -> bool:
        if profile is None:
            return False

        address = profile.address
        required_user = [user.name, user.email, user.phone]
        required_profile = [profile.cpf, profile.birth_date, profile.job_title, profile.country]
        required_address = (
            address is not None
            and address.postal_code
            and address.street
            and address.number
            and address.city
            and address.state
        )

        return all(required_user) and all(required_profile) and required_address

    def _to_response(
        self, user: UserDocument, profile: UserProfileDocument | None
    ) -> UserProfileResponse:
        address = None
        if profile is not None and profile.address is not None:
            address = ProfileAddressResponse.model_validate(profile.address.model_dump())

        updated_at = profile.updated_at if profile is not None else user.updated_at
        created_at = profile.created_at if profile is not None else user.created_at

        return UserProfileResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            picture=self._picture_url(user, profile),
            picture_storage_key=profile.picture_storage_key if profile else None,
            cpf=profile.cpf if profile else None,
            birth_date=profile.birth_date if profile else None,
            job_title=profile.job_title if profile else None,
            address=address,
            country=profile.country if profile else "BR",
            is_complete=self._is_profile_complete(user, profile),
            created_at=created_at,
            updated_at=updated_at,
        )

    async def get_my_profile(self, *, firebase_uid: str) -> UserProfileResponse:
        user = await self._resolve_user(firebase_uid)
        profile = await self._repo.get_by_user(user.id)
        return self._to_response(user, profile)

    async def update_my_profile(
        self, payload: UserProfileUpdate, *, firebase_uid: str
    ) -> UserProfileResponse:
        user = await self._resolve_user(firebase_uid)
        data = payload.model_dump(exclude_unset=True)

        user_patch: dict[str, object] = {}
        profile_patch: dict[str, object] = {}

        for key in ("name", "email", "phone"):
            if key in data:
                user_patch[key] = data.pop(key)

        picture_url = data.pop("picture_url", None)
        picture_storage_key = data.pop("picture_storage_key", None)
        if picture_url is not None:
            user_patch["picture"] = picture_url
            profile_patch["picture_url"] = picture_url
        if picture_storage_key is not None:
            profile_patch["picture_storage_key"] = picture_storage_key

        if "address" in data and data["address"] is not None:
            data["address"] = UserProfileAddress.model_validate(data["address"]).model_dump()

        profile_patch.update(data)

        if user_patch:
            firebase_fields: dict[str, object] = {}
            if "name" in user_patch:
                firebase_fields["display_name"] = user_patch["name"]
            if "email" in user_patch:
                firebase_fields["email"] = user_patch["email"]
            if "picture" in user_patch:
                firebase_fields["photo_url"] = user_patch["picture"]

            if firebase_fields:
                await firebase.update_user(user.firebase_uid, **firebase_fields)

            updated_user = await self._auth_repo.update_profile(user.id, user_patch)
            if updated_user is None:
                raise NotFoundError("User not found.")
            user = updated_user

        profile = await self._repo.get_by_user(user.id)
        if profile_patch:
            profile = await self._repo.upsert_for_user(user.id, profile_patch)

        return self._to_response(user, profile)

    async def presign_avatar(
        self, payload: AvatarPresignRequest, *, firebase_uid: str
    ) -> AvatarPresignResponse:
        user = await self._resolve_user(firebase_uid)
        content_type = payload.content_type.lower()
        if content_type not in _ALLOWED_AVATAR_TYPES:
            raise ConflictError(
                "Unsupported image type. Use JPEG, PNG, WebP or GIF.",
                code="invalid_content_type",
            )

        extension = (
            payload.filename.rsplit(".", 1)[-1].lower()
            if "." in payload.filename
            else "bin"
        )
        storage_key = f"users/{user.id}/{new_uuid()}.{extension}"
        expires_in = 900
        expires_at = utcnow() + timedelta(seconds=expires_in)

        upload_url, public_url = await firebase.presign_storage_upload(
            storage_key,
            content_type=content_type,
            expires_in=expires_in,
        )

        return AvatarPresignResponse(
            upload_url=upload_url,
            storage_key=storage_key,
            public_url=public_url,
            expires_at=expires_at,
        )


__all__ = ["UsersService"]
