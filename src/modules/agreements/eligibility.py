"""Profile and company completeness gate for agreements."""

from __future__ import annotations

from src.core.exceptions import ValidationAppError
from src.modules.auth.model import UserDocument
from src.modules.companies.model import CompanyDocument, ComplianceDocumentStatus
from src.modules.users.model import UserProfileDocument


def personal_missing_fields(
    user: UserDocument, profile: UserProfileDocument | None
) -> list[str]:
    missing: list[str] = []
    if not user.name:
        missing.append("name")
    if not user.email:
        missing.append("email")
    if not user.phone:
        missing.append("phone")
    if not (user.is_verified or user.email_verified):
        missing.append("email_verified")
    if profile is None:
        missing.extend(["cpf", "address"])
        return missing
    if not profile.cpf:
        missing.append("cpf")
    address = profile.address
    if address is None:
        missing.append("address")
    else:
        for field, key in (
            (address.postal_code, "address.postal_code"),
            (address.street, "address.street"),
            (address.number, "address.number"),
            (address.city, "address.city"),
            (address.state, "address.state"),
        ):
            if not field:
                missing.append(key)
    return missing


def company_missing_fields(company: CompanyDocument) -> list[str]:
    missing: list[str] = []
    if not company.legal_name:
        missing.append("company.legal_name")
    if not company.trade_name:
        missing.append("company.trade_name")
    if not company.tax_id:
        missing.append("company.tax_id")
    if not company.email:
        missing.append("company.email")
    if not company.phone:
        missing.append("company.phone")
    if not company.legal_representative:
        missing.append("company.legal_representative")
    address = company.address
    if address is None:
        missing.append("company.address")
    else:
        for field, key in (
            (address.postal_code, "company.address.postal_code"),
            (address.street, "company.address.street"),
            (address.number, "company.address.number"),
            (address.city, "company.address.city"),
            (address.state, "company.address.state"),
        ):
            if not field:
                missing.append(key)
    if not company.operating_license or not company.operating_license.storage_key:
        missing.append("company.operating_license")
    elif company.operating_license.status != ComplianceDocumentStatus.APPROVED:
        missing.append("company.operating_license")
    if not company.mtr_document or not company.mtr_document.storage_key:
        missing.append("company.mtr_document")
    elif company.mtr_document.status != ComplianceDocumentStatus.APPROVED:
        missing.append("company.mtr_document")
    return missing


def raise_if_incomplete(missing: list[str], *, message: str | None = None) -> None:
    if not missing:
        return
    raise ValidationAppError(
        message
        or "Complete seu perfil e os dados da empresa antes de continuar com acordos.",
        code="profile_incomplete",
        details={"missing": missing},
    )


__all__ = [
    "company_missing_fields",
    "personal_missing_fields",
    "raise_if_incomplete",
]
