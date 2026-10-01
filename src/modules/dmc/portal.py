"""Company-user entry point for requesting a DMC agent."""

from __future__ import annotations

from src.core.exceptions import NotFoundError
from src.modules.auth.repository import AuthRepository
from src.modules.companies.repository import CompaniesRepository
from src.modules.support.schema import SupportTicketResponse
from src.modules.support.service import SupportService
from src.modules.users.repository import UsersRepository


class DmcPortalService:
    def __init__(
        self,
        *,
        auth: AuthRepository,
        users: UsersRepository,
        companies: CompaniesRepository,
        support: SupportService,
    ) -> None:
        self._auth = auth
        self._users = users
        self._companies = companies
        self._support = support

    async def request_contact(
        self, firebase_uid: str, message: str
    ) -> SupportTicketResponse:
        user = await self._auth.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.")
        profile = await self._users.get_by_user(user.id)
        company = None
        if profile is not None and profile.company_id is not None:
            company = await self._companies.get(profile.company_id)
        if company is None or not company.is_active:
            owned = await self._companies.list_for_owner(user.id, skip=0, limit=1)
            company = owned[0] if owned else None
        company_name = None
        company_id = None
        if company is not None and company.is_active:
            company_name = company.trade_name or company.legal_name
            company_id = company.id
        return await self._support.create_authenticated_dmc_request(
            firebase_uid=firebase_uid,
            message=message,
            company_name=company_name,
            company_id=company_id,
            phone=user.phone,
            position=profile.job_title if profile is not None else None,
        )


__all__ = ["DmcPortalService"]
