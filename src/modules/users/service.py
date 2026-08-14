"""Business rules for ``users``."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import UploadFile

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
from src.shared.schemas.responses import StorageUploadResponse
from src.shared.utils.image_upload import extension_from_filename, upload_image_file
from src.shared.utils.storage_keys import avatar_storage_key
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
        has_required_address = bool(
            address is not None
            and address.postal_code
            and address.street
            and address.number
            and address.city
            and address.state
        )

        return all(required_user) and all(required_profile) and has_required_address

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

    async def get_profile_by_id(self, user_id: UUID) -> UserProfileResponse:
        user = await self._auth_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        profile = await self._repo.get_by_user(user.id)
        return self._to_response(user, profile)

    async def delete_profile_for_user(self, user_id: UUID) -> None:
        await self._repo.delete_for_user(user_id)

    async def update_my_profile(
        self, payload: UserProfileUpdate, *, firebase_uid: str
    ) -> UserProfileResponse:
        user = await self._resolve_user(firebase_uid)
        data = payload.model_dump(exclude_unset=True)

        # #region agent log
        try:
            import json as _json
            from pathlib import Path as _Path
            _log = _Path(__file__).resolve().parents[3] / "debug-bb369f.log"
            _bd = data.get("birth_date")
            _log.open("a", encoding="utf-8").write(
                _json.dumps(
                    {
                        "sessionId": "bb369f",
                        "runId": "post-fix",
                        "hypothesisId": "D",
                        "location": "users/service.py:update_my_profile:entry",
                        "message": "profile update entered service",
                        "data": {
                            "keys": sorted(data.keys()),
                            "has_country": "country" in data,
                            "birth_date_type": type(_bd).__name__ if _bd is not None else None,
                            "birth_date_repr": repr(_bd) if _bd is not None else None,
                        },
                        "timestamp": __import__("time").time() * 1000,
                    }
                )
                + "\n"
            )
        except Exception:
            pass
        # #endregion

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

        # #region agent log
        try:
            import json as _json
            from pathlib import Path as _Path
            _set_on_insert_keys = {"_id", "user_id", "created_at", "locale", "preferences", "country"}
            _overlap = sorted(_set_on_insert_keys.intersection(profile_patch.keys()))
            _type_map = {k: type(v).__name__ for k, v in profile_patch.items()}
            _log = _Path(__file__).resolve().parents[3] / "debug-bb369f.log"
            _log.open("a", encoding="utf-8").write(
                _json.dumps(
                    {
                        "sessionId": "bb369f",
                        "hypothesisId": "A,B",
                        "location": "users/service.py:update_my_profile:before_writes",
                        "message": "patches ready before firebase/mongo",
                        "data": {
                            "user_patch_keys": sorted(user_patch.keys()),
                            "profile_patch_keys": sorted(profile_patch.keys()),
                            "set_on_insert_overlap": _overlap,
                            "profile_value_types": _type_map,
                        },
                        "timestamp": __import__("time").time() * 1000,
                    }
                )
                + "\n"
            )
        except Exception:
            pass
        # #endregion

        if user_patch:
            firebase_fields: dict[str, object] = {}
            if "name" in user_patch:
                firebase_fields["display_name"] = user_patch["name"]
            if "email" in user_patch:
                firebase_fields["email"] = user_patch["email"]
            if "picture" in user_patch:
                firebase_fields["photo_url"] = user_patch["picture"]

            if firebase_fields:
                try:
                    await firebase.update_user(user.firebase_uid, **firebase_fields)
                except Exception as _fb_exc:
                    # #region agent log
                    try:
                        import json as _json
                        from pathlib import Path as _Path
                        _log = _Path(__file__).resolve().parents[3] / "debug-bb369f.log"
                        _log.open("a", encoding="utf-8").write(
                            _json.dumps(
                                {
                                    "sessionId": "bb369f",
                                    "hypothesisId": "C",
                                    "location": "users/service.py:update_my_profile:firebase",
                                    "message": "firebase update_user failed",
                                    "data": {
                                        "exc_type": type(_fb_exc).__name__,
                                        "exc_msg": str(_fb_exc)[:300],
                                        "firebase_fields": sorted(firebase_fields.keys()),
                                    },
                                    "timestamp": __import__("time").time() * 1000,
                                }
                            )
                            + "\n"
                        )
                    except Exception:
                        pass
                    # #endregion
                    raise

            updated_user = await self._auth_repo.update_profile(user.id, user_patch)
            if updated_user is None:
                raise NotFoundError("User not found.")
            user = updated_user

        profile = await self._repo.get_by_user(user.id)
        if profile_patch:
            try:
                profile = await self._repo.upsert_for_user(user.id, profile_patch)
                # #region agent log
                try:
                    import json as _json
                    from pathlib import Path as _Path
                    _log = _Path(__file__).resolve().parents[3] / "debug-bb369f.log"
                    _log.open("a", encoding="utf-8").write(
                        _json.dumps(
                            {
                                "sessionId": "bb369f",
                                "runId": "post-fix",
                                "hypothesisId": "A,B",
                                "location": "users/service.py:update_my_profile:upsert_ok",
                                "message": "mongo upsert_for_user succeeded",
                                "data": {
                                    "profile_id": str(profile.id) if profile else None,
                                    "birth_date": str(profile.birth_date) if profile else None,
                                    "country": profile.country if profile else None,
                                },
                                "timestamp": __import__("time").time() * 1000,
                            }
                        )
                        + "\n"
                    )
                except Exception:
                    pass
                # #endregion
            except Exception as _mongo_exc:
                # #region agent log
                try:
                    import json as _json
                    from pathlib import Path as _Path
                    _log = _Path(__file__).resolve().parents[3] / "debug-bb369f.log"
                    _log.open("a", encoding="utf-8").write(
                        _json.dumps(
                            {
                                "sessionId": "bb369f",
                                "runId": "post-fix",
                                "hypothesisId": "A,B",
                                "location": "users/service.py:update_my_profile:upsert",
                                "message": "mongo upsert_for_user failed",
                                "data": {
                                    "exc_type": type(_mongo_exc).__name__,
                                    "exc_msg": str(_mongo_exc)[:400],
                                    "profile_patch_keys": sorted(profile_patch.keys()),
                                },
                                "timestamp": __import__("time").time() * 1000,
                            }
                        )
                        + "\n"
                    )
                except Exception:
                    pass
                # #endregion
                raise

        try:
            result = self._to_response(user, profile)
            # #region agent log
            try:
                import json as _json
                from pathlib import Path as _Path
                _log = _Path(__file__).resolve().parents[3] / "debug-bb369f.log"
                _log.open("a", encoding="utf-8").write(
                    _json.dumps(
                        {
                        "sessionId": "bb369f",
                        "runId": "post-fix-2",
                        "hypothesisId": "E",
                        "location": "users/service.py:update_my_profile:success",
                        "message": "profile update completed",
                        "data": {
                            "is_complete": result.is_complete,
                            "is_complete_type": type(result.is_complete).__name__,
                            "birth_date": str(result.birth_date) if result.birth_date else None,
                        },
                            "timestamp": __import__("time").time() * 1000,
                        }
                    )
                    + "\n"
                )
            except Exception:
                pass
            # #endregion
            return result
        except Exception as _resp_exc:
            # #region agent log
            try:
                import json as _json
                from pathlib import Path as _Path
                _log = _Path(__file__).resolve().parents[3] / "debug-bb369f.log"
                _log.open("a", encoding="utf-8").write(
                    _json.dumps(
                        {
                            "sessionId": "bb369f",
                            "runId": "post-fix",
                            "hypothesisId": "E",
                            "location": "users/service.py:update_my_profile:response",
                            "message": "_to_response failed",
                            "data": {
                                "exc_type": type(_resp_exc).__name__,
                                "exc_msg": str(_resp_exc)[:300],
                            },
                            "timestamp": __import__("time").time() * 1000,
                        }
                    )
                    + "\n"
                )
            except Exception:
                pass
            # #endregion
            raise

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
        storage_key = avatar_storage_key(user.id, extension)
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

    async def upload_avatar(
        self, file: UploadFile, *, firebase_uid: str
    ) -> StorageUploadResponse:
        user = await self._resolve_user(firebase_uid)
        extension = extension_from_filename(file.filename or "avatar.bin")
        storage_key = avatar_storage_key(user.id, extension)
        public_url = await upload_image_file(
            file,
            allowed_types=_ALLOWED_AVATAR_TYPES,
            storage_key=storage_key,
        )

        profile_patch = {
            "picture_url": public_url,
            "picture_storage_key": storage_key,
        }
        await firebase.update_user(user.firebase_uid, photo_url=public_url)
        updated_user = await self._auth_repo.update_profile(
            user.id, {"picture": public_url}
        )
        if updated_user is not None:
            user = updated_user
        await self._repo.upsert_for_user(user.id, profile_patch)

        return StorageUploadResponse(storage_key=storage_key, public_url=public_url)


__all__ = ["UsersService"]
