"""Portfolio scope loaded from the database, never from client-supplied ids."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from src.core.exceptions import ForbiddenError
from src.modules.companies.model import CompanyDocument
from src.modules.companies.repository import CompaniesRepository
from src.modules.dmc.model import DmcPortfolioLinkDocument
from src.modules.dmc.repository import DmcPortfolioRepository
from src.modules.users.model import UserProfileDocument
from src.modules.users.repository import UsersRepository


@dataclass
class PortfolioScope:
    agent_user_id: UUID
    links: list[DmcPortfolioLinkDocument] = field(default_factory=list)
    companies: dict[UUID, CompanyDocument] = field(default_factory=dict)
    profiles: list[UserProfileDocument] = field(default_factory=list)
    user_company: dict[UUID, UUID] = field(default_factory=dict)

    @property
    def company_ids(self) -> set[UUID]:
        return set(self.companies)

    def require_company(self, company_id: UUID) -> CompanyDocument:
        company = self.companies.get(company_id)
        if company is None:
            raise ForbiddenError(
                "This company is outside your portfolio.",
                code="outside_scope",
            )
        return company

    def require_user(self, user_id: UUID) -> UUID:
        company_id = self.user_company.get(user_id)
        if company_id is None:
            raise ForbiddenError(
                "This user is outside your portfolio.",
                code="outside_scope",
            )
        return company_id


class ScopeService:
    def __init__(
        self,
        portfolio: DmcPortfolioRepository,
        companies: CompaniesRepository,
        users: UsersRepository,
    ) -> None:
        self._portfolio = portfolio
        self._companies = companies
        self._users = users

    async def for_agent(self, agent_user_id: UUID) -> PortfolioScope:
        links = await self._portfolio.list_for_agent(agent_user_id)
        company_ids = [link.company_id for link in links]
        companies = await self._companies.get_many(company_ids)
        active = {
            company_id: company
            for company_id, company in companies.items()
            if company.is_active
        }
        profiles = await self._users.list_by_company_ids(list(active))
        user_company: dict[UUID, UUID] = {}
        for company in active.values():
            user_company[company.owner_user_id] = company.id
        for profile in profiles:
            if profile.company_id in active and profile.user_id not in user_company:
                user_company[profile.user_id] = profile.company_id
        return PortfolioScope(
            agent_user_id=agent_user_id,
            links=[link for link in links if link.company_id in active],
            companies=active,
            profiles=profiles,
            user_company=user_company,
        )


__all__ = ["PortfolioScope", "ScopeService"]
