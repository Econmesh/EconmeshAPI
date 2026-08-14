"""Tests for agreement eligibility completeness checks."""

from __future__ import annotations

import pytest

from src.modules.agreements.eligibility import company_missing_fields
from src.modules.companies.model import (
    CompanyAddress,
    CompanyComplianceFile,
    CompanyDocument,
    ComplianceDocumentStatus,
)
from src.shared.utils.ids import new_uuid

pytestmark = pytest.mark.unit


def _doc(**overrides: object) -> CompanyDocument:
    data: dict[str, object] = {
        "owner_user_id": new_uuid(),
        "legal_name": "Acme Ltda",
        "trade_name": "Acme",
        "tax_id": "11222333000181",
        "email": "contato@acme.com",
        "phone": "11999990000",
        "legal_representative": "Alice Doe",
        "address": CompanyAddress(
            postal_code="01310100",
            street="Av. Paulista",
            number="1000",
            city="São Paulo",
            state="SP",
        ),
        "operating_license": CompanyComplianceFile(
            storage_key="econmesh/company-docs/x/lo.pdf",
            public_url="https://example.com/lo.pdf",
            filename="lo.pdf",
            content_type="application/pdf",
            status=ComplianceDocumentStatus.APPROVED,
        ),
        "mtr_document": CompanyComplianceFile(
            storage_key="econmesh/company-docs/x/mtr.pdf",
            public_url="https://example.com/mtr.pdf",
            filename="mtr.pdf",
            content_type="application/pdf",
            status=ComplianceDocumentStatus.APPROVED,
        ),
    }
    data.update(overrides)
    return CompanyDocument.model_validate(data)


def test_company_missing_fields_empty_when_complete() -> None:
    assert company_missing_fields(_doc()) == []


def test_company_missing_fields_requires_compliance_documents() -> None:
    missing = company_missing_fields(_doc(operating_license=None, mtr_document=None))
    assert "company.operating_license" in missing
    assert "company.mtr_document" in missing


def test_company_missing_fields_requires_approved_compliance_documents() -> None:
    missing = company_missing_fields(
        _doc(
            operating_license=CompanyComplianceFile(
                storage_key="econmesh/company-docs/x/lo.pdf",
                public_url="https://example.com/lo.pdf",
                filename="lo.pdf",
                content_type="application/pdf",
                status=ComplianceDocumentStatus.PENDING,
            )
        )
    )
    assert "company.operating_license" in missing
