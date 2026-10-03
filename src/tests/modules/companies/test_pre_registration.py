"""Pre-registration (pré-cadastro) by DMC agents and claim at signup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from src.core.exceptions import ConflictError, NotFoundError
from src.infrastructure.redis.client import redis_manager
from src.modules.auth.model import UserDocument
from src.modules.companies.model import (
    CompanyAddress,
    CompanyDocument,
    CompanyRegistrationStatus,
    is_pre_registered,
)
from src.modules.companies.schema import (
    CompanyCreate,
    PreRegistrationCreate,
    PreRegistrationMatch,
    PreRegistrationMatchList,
)
from src.modules.companies.service import CompaniesService, mask_tax_id
from src.modules.dmc.model import AuditAction, PortfolioSource
from src.shared.constants.permissions import Permission, role_has_permission
from src.shared.constants.roles import Role

pytestmark = pytest.mark.unit


def _pre_registered(**overrides: object) -> CompanyDocument:
    data: dict[str, object] = {
        "owner_user_id": None,
        "registration_status": CompanyRegistrationStatus.PRE_REGISTERED,
        "legal_name": "Recicla Sul Ltda",
        "trade_name": "Recicla Sul",
        "tax_id": "11222333000181",
        "email": "contato@reciclasul.com.br",
        "phone": "51999990000",
        "address": CompanyAddress(city="Porto Alegre", state="RS"),
    }
    data.update(overrides)
    return CompanyDocument(**data)  # type: ignore[arg-type]


def test_mask_tax_id_hides_middle_digits() -> None:
    assert mask_tax_id("11222333000181") == "11.222.***/****-81"


def test_is_pre_registered() -> None:
    assert is_pre_registered(_pre_registered())
    assert not is_pre_registered(_pre_registered(owner_user_id=uuid4()))
    assert not is_pre_registered(
        _pre_registered(registration_status=CompanyRegistrationStatus.COMPLETE)
    )
    assert not is_pre_registered(_pre_registered(is_active=False))
    assert not is_pre_registered(None)


def test_dmc_agent_can_pre_register() -> None:
    assert role_has_permission(Role.DMC_AGENT, Permission.COMPANIES_PRE_REGISTER)
    assert not role_has_permission(Role.VIEWER, Permission.COMPANIES_PRE_REGISTER)


async def test_search_requires_minimum_query_and_masks_cnpj() -> None:
    repo = AsyncMock()
    repo.search_pre_registrations = AsyncMock(return_value=[_pre_registered()])
    service = CompaniesService(repo, AsyncMock())

    assert (await service.search_pre_registrations("ab")).items == []
    assert (await service.search_pre_registrations("1122")).items == []
    repo.search_pre_registrations.assert_not_awaited()

    result = await service.search_pre_registrations("recicla")
    assert len(result.items) == 1
    match = result.items[0]
    assert match.tax_id_masked == "11.222.***/****-81"
    assert match.city == "Porto Alegre"
    assert "email" not in match.model_dump()


async def test_prefill_only_for_unclaimed_pre_registration() -> None:
    repo = AsyncMock()
    company = _pre_registered()
    repo.get_pre_registration = AsyncMock(return_value=company)
    service = CompaniesService(repo, AsyncMock())

    prefill = await service.get_pre_registration_prefill(company.id)
    assert prefill.tax_id == "11222333000181"
    assert prefill.email == "contato@reciclasul.com.br"

    repo.get_pre_registration = AsyncMock(return_value=None)
    with pytest.raises(NotFoundError):
        await service.get_pre_registration_prefill(company.id)


async def test_create_company_claims_pre_registration() -> None:
    user = UserDocument(firebase_uid="fb-1", email="dono@reciclasul.com.br")
    existing = _pre_registered(sector="Reciclagem")
    repo = AsyncMock()
    repo.count_for_owner = AsyncMock(return_value=0)
    repo.get_by_tax_id = AsyncMock(return_value=existing)
    claimed = existing.model_copy(
        update={
            "owner_user_id": user.id,
            "registration_status": CompanyRegistrationStatus.COMPLETE,
        }
    )
    repo.claim_pre_registration = AsyncMock(return_value=claimed)
    auth_repo = AsyncMock()
    auth_repo.get_by_firebase_uid = AsyncMock(return_value=user)
    service = CompaniesService(repo, auth_repo)

    response = await service.create(
        CompanyCreate(legal_name="Recicla Sul Ltda", tax_id="11222333000181"),
        firebase_uid="fb-1",
    )

    repo.create.assert_not_awaited()
    company_id, patch = repo.claim_pre_registration.await_args.args
    assert company_id == existing.id
    assert patch["owner_user_id"] == user.id
    assert patch["sector"] == "Reciclagem"  # kept from the DMC pre-registration
    assert response.id == existing.id
    assert response.registration_status == CompanyRegistrationStatus.COMPLETE


async def test_create_company_conflicts_with_complete_company() -> None:
    user = UserDocument(firebase_uid="fb-1", email="dono@reciclasul.com.br")
    repo = AsyncMock()
    repo.count_for_owner = AsyncMock(return_value=0)
    repo.get_by_tax_id = AsyncMock(
        return_value=_pre_registered(
            owner_user_id=uuid4(), registration_status=CompanyRegistrationStatus.COMPLETE
        )
    )
    auth_repo = AsyncMock()
    auth_repo.get_by_firebase_uid = AsyncMock(return_value=user)
    service = CompaniesService(repo, auth_repo)

    with pytest.raises(ConflictError) as exc:
        await service.create(
            CompanyCreate(legal_name="Recicla Sul Ltda", tax_id="11222333000181"),
            firebase_uid="fb-1",
        )
    assert exc.value.code == "tax_id_exists"


def _agent_service(companies: AsyncMock, portfolio: AsyncMock, audit: AsyncMock):
    from src.modules.dmc.agent_service import DmcAgentService

    agent = UserDocument(
        firebase_uid="agent-uid", email="agente@econmesh.com", role=Role.DMC_AGENT
    )
    auth = AsyncMock()
    auth.get_by_firebase_uid = AsyncMock(return_value=agent)
    service = DmcAgentService(
        auth=auth,
        companies=companies,
        scope=AsyncMock(),
        conversations=AsyncMock(),
        messages=AsyncMock(),
        batches=AsyncMock(),
        user_notifications=AsyncMock(),
        tickets=AsyncMock(),
        ticket_messages=AsyncMock(),
        opportunities=AsyncMock(),
        support_notifications=AsyncMock(),
        audit=audit,
        portfolio=portfolio,
    )
    return service, agent


async def test_dmc_pre_register_creates_ownerless_company_in_portfolio() -> None:
    companies = AsyncMock()
    companies.get_by_tax_id = AsyncMock(return_value=None)
    companies.create = AsyncMock(side_effect=lambda doc: doc)
    portfolio = AsyncMock()
    audit = AsyncMock()
    service, agent = _agent_service(companies, portfolio, audit)

    detail = await service.pre_register_company(
        "agent-uid",
        PreRegistrationCreate(legal_name="Recicla Sul Ltda", tax_id="11.222.333/0001-81"),
    )

    created: CompanyDocument = companies.create.await_args.args[0]
    assert created.owner_user_id is None
    assert created.registration_status == CompanyRegistrationStatus.PRE_REGISTERED
    assert created.tax_id == "11222333000181"
    link = portfolio.create.await_args.args[0]
    assert link.agent_user_id == agent.id
    assert link.company_id == created.id
    assert link.source == PortfolioSource.REGISTERED
    assert audit.record.await_args.args[0] == AuditAction.COMPANY_PRE_REGISTERED
    assert detail.registration_status == CompanyRegistrationStatus.PRE_REGISTERED
    assert detail.in_portfolio is True


async def test_dmc_pre_register_rejects_existing_cnpj() -> None:
    companies = AsyncMock()
    companies.get_by_tax_id = AsyncMock(return_value=_pre_registered())
    portfolio = AsyncMock()
    service, _ = _agent_service(companies, portfolio, AsyncMock())

    with pytest.raises(ConflictError) as exc:
        await service.pre_register_company(
            "agent-uid",
            PreRegistrationCreate(legal_name="Recicla Sul Ltda", tax_id="11222333000181"),
        )
    assert exc.value.code == "tax_id_exists"
    companies.create.assert_not_awaited()
    portfolio.create.assert_not_awaited()


async def test_signup_claims_pre_registration() -> None:
    from src.modules.auth.schema import RegisterCompanyInput
    from src.modules.auth.service import AuthService

    existing = _pre_registered()
    companies = AsyncMock()
    companies.get_by_tax_id = AsyncMock(return_value=existing)
    companies.claim_pre_registration = AsyncMock(
        side_effect=lambda company_id, patch: existing.model_copy(update=patch)
    )
    users = AsyncMock()
    service = AuthService(
        repository=AsyncMock(),
        redis_client=AsyncMock(),
        firebase_client=MagicMock(),
        email_client=MagicMock(),
        companies_repository=companies,
        users_repository=users,
    )
    user = UserDocument(firebase_uid="fb-2", email="dono@reciclasul.com.br", name="Maria")
    payload = RegisterCompanyInput(
        legal_name="Recicla Sul Ltda",
        tax_id="11222333000181",
        email="financeiro@reciclasul.com.br",
        phone="51999990000",
        address={
            "postal_code": "90000000",
            "street": "Rua A",
            "number": "10",
            "city": "Porto Alegre",
            "state": "RS",
        },
    )

    await service._assert_tax_id_available(payload)  # no conflict for a pre-registration
    await service._attach_company(user, payload)

    companies.create.assert_not_awaited()
    company_id, patch = companies.claim_pre_registration.await_args.args
    assert company_id == existing.id
    assert patch["owner_user_id"] == user.id
    assert patch["email"] == "financeiro@reciclasul.com.br"
    users.upsert_for_user.assert_awaited_once_with(user.id, {"company_id": existing.id})


async def test_signup_restores_pre_registration_when_profile_link_fails() -> None:
    from src.modules.auth.schema import RegisterCompanyInput
    from src.modules.auth.service import AuthService

    existing = _pre_registered()
    companies = AsyncMock()
    companies.get_by_tax_id = AsyncMock(return_value=existing)
    companies.claim_pre_registration = AsyncMock(
        side_effect=lambda company_id, patch: existing.model_copy(update=patch)
    )
    users = AsyncMock()
    users.upsert_for_user = AsyncMock(side_effect=RuntimeError("db down"))
    service = AuthService(
        repository=AsyncMock(),
        redis_client=AsyncMock(),
        firebase_client=MagicMock(),
        email_client=MagicMock(),
        companies_repository=companies,
        users_repository=users,
    )
    user = UserDocument(firebase_uid="fb-3", email="dono@reciclasul.com.br")
    payload = RegisterCompanyInput(
        legal_name="Recicla Sul Ltda",
        tax_id="11222333000181",
        email="financeiro@reciclasul.com.br",
        phone="51999990000",
        address={
            "postal_code": "90000000",
            "street": "Rua A",
            "number": "10",
            "city": "Porto Alegre",
            "state": "RS",
        },
    )

    with pytest.raises(RuntimeError):
        await service._attach_company(user, payload)
    companies.restore.assert_awaited_once_with(existing)
    companies.hard_delete.assert_not_awaited()


async def test_public_search_route_needs_no_auth(app: FastAPI, client: AsyncClient) -> None:
    from src.modules.companies.controller import CompaniesController
    from src.modules.companies.routes import _build_controller

    match = PreRegistrationMatch(
        id=uuid4(), legal_name="Recicla Sul Ltda", tax_id_masked="11.222.***/****-81"
    )

    class _Stub(CompaniesController):
        def __init__(self) -> None:
            pass

        async def search_pre_registrations(self, q: str) -> PreRegistrationMatchList:
            assert q == "recicla"
            return PreRegistrationMatchList(items=[match])

    redis_manager.client.incr = AsyncMock(return_value=1)
    app.dependency_overrides[_build_controller] = lambda: _Stub()
    try:
        response = await client.get("/api/v1/companies/pre-registrations/search?q=recicla")
        assert response.status_code == 200
        assert response.json()["items"][0]["tax_id_masked"] == "11.222.***/****-81"

        redis_manager.client.incr = AsyncMock(return_value=31)
        limited = await client.get("/api/v1/companies/pre-registrations/search?q=recicla")
        assert limited.status_code == 429
    finally:
        app.dependency_overrides.clear()
