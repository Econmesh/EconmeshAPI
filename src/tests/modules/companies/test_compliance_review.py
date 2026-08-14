"""Tests for company compliance document review."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import ValidationAppError
from src.modules.auth.model import UserDocument
from src.modules.companies.compliance_review import ComplianceReviewService
from src.modules.companies.model import (
    CompanyComplianceFile,
    CompanyDocument,
    ComplianceDocumentStatus,
)
from src.modules.support.model import (
    SupportTicketDocument,
    SupportTicketSource,
    SupportTicketStatus,
)
from src.shared.utils.ids import new_uuid
from src.shared.utils.time import utcnow

pytestmark = pytest.mark.unit


def _file(**overrides: object) -> CompanyComplianceFile:
    data: dict[str, object] = {
        "storage_key": "econmesh/company-docs/x/lo.pdf",
        "public_url": "https://example.com/lo.pdf",
        "filename": "lo.pdf",
        "content_type": "application/pdf",
        "status": ComplianceDocumentStatus.PENDING,
    }
    data.update(overrides)
    return CompanyComplianceFile.model_validate(data)


def _company(**overrides: object) -> CompanyDocument:
    data: dict[str, object] = {
        "owner_user_id": new_uuid(),
        "legal_name": "Acme Ltda",
        "tax_id": "11222333000181",
        "operating_license": _file(),
        "mtr_document": _file(filename="mtr.pdf", storage_key="econmesh/company-docs/x/mtr.pdf"),
    }
    data.update(overrides)
    return CompanyDocument.model_validate(data)


def _build_service() -> tuple[ComplianceReviewService, dict[str, AsyncMock]]:
    companies = AsyncMock()
    tickets = AsyncMock()
    messages = AsyncMock()
    auth = AsyncMock()
    notifications_repo = AsyncMock()
    email = AsyncMock()
    support_notifications = AsyncMock()
    support_realtime = AsyncMock()
    notification_realtime = AsyncMock()
    presence = AsyncMock()
    presence.is_online = AsyncMock(return_value=True)
    service = ComplianceReviewService(
        companies_repo=companies,
        tickets_repo=tickets,
        messages_repo=messages,
        auth_repo=auth,
        user_notifications_repo=notifications_repo,
        email_sender=email,
        support_notifications=support_notifications,
        support_realtime=support_realtime,
        notification_realtime=notification_realtime,
        presence=presence,
    )
    return service, {
        "companies": companies,
        "tickets": tickets,
        "messages": messages,
        "auth": auth,
        "notifications_repo": notifications_repo,
        "support_notifications": support_notifications,
    }


async def test_enqueue_creates_document_review_ticket() -> None:
    service, deps = _build_service()
    company = _company()
    deps["tickets"].find_open_document_review = AsyncMock(return_value=None)
    deps["tickets"].find_latest_document_review = AsyncMock(return_value=None)
    deps["tickets"].next_document_review_ticket_number = AsyncMock(return_value=1)
    deps["tickets"].create = AsyncMock(side_effect=lambda doc: doc)

    ticket = await service.enqueue(company)

    assert ticket is not None
    assert ticket.source == SupportTicketSource.DOCUMENT_REVIEW
    assert ticket.company_id == company.id
    assert ticket.status == SupportTicketStatus.OPEN
    deps["support_notifications"].notify_admins_document_review.assert_awaited_once()
    deps["messages"].create.assert_awaited_once()


async def test_enqueue_reopens_closed_ticket() -> None:
    service, deps = _build_service()
    company = _company()
    closed = SupportTicketDocument(
        source=SupportTicketSource.DOCUMENT_REVIEW,
        user_id=company.owner_user_id,
        company_id=company.id,
        ticket_number=3,
        subject="Documentos para análise — Acme Ltda",
        status=SupportTicketStatus.CLOSED,
        last_message_at=utcnow(),
        closed_at=utcnow(),
    )
    deps["tickets"].find_open_document_review = AsyncMock(return_value=None)
    deps["tickets"].find_latest_document_review = AsyncMock(return_value=closed)
    reopened = closed.model_copy(update={"status": SupportTicketStatus.OPEN, "closed_at": None})
    deps["tickets"].update = AsyncMock(return_value=reopened)

    ticket = await service.enqueue(company, message="Documento reenviado.")

    assert ticket is not None
    assert ticket.status == SupportTicketStatus.OPEN
    deps["tickets"].create.assert_not_awaited()
    deps["support_notifications"].notify_admins_document_review.assert_awaited_once()


async def test_approve_updates_document_and_notifies_owner() -> None:
    service, deps = _build_service()
    company = _company()
    reviewer_id = new_uuid()
    deps["companies"].get = AsyncMock(return_value=company)
    approved_license = _file(status=ComplianceDocumentStatus.APPROVED)
    updated = company.model_copy(
        update={
            "operating_license": approved_license,
            "mtr_document": _file(status=ComplianceDocumentStatus.PENDING),
        }
    )
    deps["companies"].update = AsyncMock(return_value=updated)
    deps["auth"].get_by_id = AsyncMock(
        return_value=UserDocument(
            id=company.owner_user_id,
            firebase_uid="fb-1",
            email="owner@example.com",
            name="Owner",
        )
    )
    deps["notifications_repo"].create = AsyncMock(side_effect=lambda doc: doc)
    deps["tickets"].find_open_document_review = AsyncMock(return_value=None)

    result = await service.approve(company.id, "operating_license", reviewer_id=reviewer_id)

    patch = deps["companies"].update.await_args.args[1]
    assert patch["operating_license"]["status"] == "approved"
    assert result.operating_license is not None
    deps["notifications_repo"].create.assert_awaited_once()


async def test_reject_requires_reason() -> None:
    service, _deps = _build_service()
    with pytest.raises(ValidationAppError) as exc:
        await service.reject(new_uuid(), "mtr", reviewer_id=new_uuid(), reason="  ")
    assert exc.value.code == "rejection_reason_required"


async def test_reject_stores_reason_and_closes_when_both_reviewed() -> None:
    service, deps = _build_service()
    company = _company(
        operating_license=_file(status=ComplianceDocumentStatus.APPROVED),
        mtr_document=_file(status=ComplianceDocumentStatus.PENDING, filename="mtr.pdf"),
    )
    deps["companies"].get = AsyncMock(return_value=company)
    updated = company.model_copy(
        update={
            "mtr_document": _file(
                status=ComplianceDocumentStatus.REJECTED,
                rejection_reason="Ilegível",
                filename="mtr.pdf",
            )
        }
    )
    deps["companies"].update = AsyncMock(return_value=updated)
    deps["auth"].get_by_id = AsyncMock(return_value=None)
    ticket = SupportTicketDocument(
        source=SupportTicketSource.DOCUMENT_REVIEW,
        user_id=company.owner_user_id,
        company_id=company.id,
        ticket_number=1,
        subject="Documentos",
        status=SupportTicketStatus.OPEN,
    )
    deps["tickets"].find_open_document_review = AsyncMock(return_value=ticket)

    result = await service.reject(
        company.id, "mtr", reviewer_id=new_uuid(), reason="Ilegível"
    )

    patch = deps["companies"].update.await_args.args[1]
    assert patch["mtr_document"]["status"] == "rejected"
    assert patch["mtr_document"]["rejection_reason"] == "Ilegível"
    assert result.mtr_document is not None
    deps["tickets"].update.assert_awaited()
    close_fields = deps["tickets"].update.await_args.args[1]
    assert close_fields["status"] == SupportTicketStatus.CLOSED.value


async def test_approve_keeps_ticket_open_when_other_document_missing() -> None:
    service, deps = _build_service()
    company = _company(
        operating_license=_file(status=ComplianceDocumentStatus.PENDING),
        mtr_document=None,
    )
    reviewer_id = new_uuid()
    deps["companies"].get = AsyncMock(return_value=company)
    updated = company.model_copy(
        update={"operating_license": _file(status=ComplianceDocumentStatus.APPROVED)}
    )
    deps["companies"].update = AsyncMock(return_value=updated)
    deps["auth"].get_by_id = AsyncMock(return_value=None)
    ticket = SupportTicketDocument(
        source=SupportTicketSource.DOCUMENT_REVIEW,
        user_id=company.owner_user_id,
        company_id=company.id,
        ticket_number=1,
        subject="Documentos",
        status=SupportTicketStatus.OPEN,
    )
    deps["tickets"].find_open_document_review = AsyncMock(return_value=ticket)

    await service.approve(company.id, "operating_license", reviewer_id=reviewer_id)

    deps["tickets"].update.assert_not_awaited()


async def test_approve_rejects_already_reviewed_document() -> None:
    service, deps = _build_service()
    company = _company(operating_license=_file(status=ComplianceDocumentStatus.APPROVED))
    deps["companies"].get = AsyncMock(return_value=company)
    with pytest.raises(ValidationAppError) as exc:
        await service.approve(company.id, "operating_license", reviewer_id=new_uuid())
    assert exc.value.code == "document_already_reviewed"
