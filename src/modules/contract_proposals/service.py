"""Business rules for contract proposals (minutas)."""

from __future__ import annotations

import re
from uuid import UUID

from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from src.core.firebase import firebase
from src.infrastructure.realtime.conversation_pubsub import ConversationRealtimePublisher
from src.modules.agreements.service import AgreementsService
from src.modules.auth.repository import AuthRepository
from src.modules.companies.model import CompanyDocument
from src.modules.companies.repository import CompaniesRepository
from src.modules.contract_proposals.core_sections import (
    FORO_SECTION_DEFINITION,
    is_foro_title,
)
from src.modules.contract_proposals.model import (
    ContractProposalDocument,
    ContractProposalStatus,
    OpportunitySnapshot,
    PartySnapshot,
    ProposalPdfFile,
    ProposalSection,
)
from src.modules.contract_proposals.opportunity_contract import (
    contract_type_for,
    minuta_title_for,
)
from src.modules.contract_proposals.pdf_service import (
    build_core_sections_html,
    build_foro_html,
    pdf_page_count,
    render_proposal_pdf,
    sha256_bytes,
)
from src.modules.contract_proposals.repository import ContractProposalsRepository
from src.modules.contract_proposals.schema import (
    ApproveProposalResponse,
    ContractProposalCreate,
    ContractProposalListItem,
    ContractProposalListParams,
    ContractProposalListResponse,
    ContractProposalResponse,
    ContractProposalUpdate,
    OpportunitySnapshotResponse,
    PartySnapshotResponse,
    ProposalPdfFileResponse,
    ProposalSectionInput,
    ProposalSectionResponse,
    RejectProposalRequest,
    RequestChangesRequest,
)
from src.modules.contract_proposals.section_sync import (
    NEGOTIATING_STATUSES,
    add_missing_admin_sections,
    ensure_foro_section,
    proposal_opportunity_type,
    reorder_proposal_sections,
)
from src.modules.contract_sections.repository import ContractSectionsRepository
from src.modules.conversations.model import (
    ConversationAuthorRole,
    ConversationMessageType,
    ConversationSystemEventKind,
    OpportunityConversationMessageDocument,
)
from src.modules.conversations.repository import (
    ConversationMessagesRepository,
    ConversationsRepository,
)
from src.modules.conversations.service import (
    _message_event_payload,
    _message_to_response,
)
from src.modules.opportunities.model import OpportunityPeriodicity
from src.modules.opportunities.repository import OpportunitiesRepository
from src.modules.platform_settings.model import ForoFillMode
from src.modules.platform_settings.repository import PlatformSettingsRepository
from src.shared.constants.brazil_states import STATE_NEIGHBORS
from src.shared.utils.ids import new_uuid
from src.shared.utils.storage_keys import build_storage_key
from src.shared.utils.time import utcnow

_EDITABLE = {
    ContractProposalStatus.DRAFT,
    ContractProposalStatus.CHANGES_REQUESTED,
}

_PERIODICITY_LABELS = {
    OpportunityPeriodicity.CONTINUA: "Contínua",
    OpportunityPeriodicity.ESPORADICA: "Esporádica",
}


def to_agreement_title(minuta_title: str) -> str:
    """Drop the 'Minuta de' prefix when a proposal becomes an agreement."""
    cleaned = re.sub(r"(?i)^\s*minuta\s+de\s+", "", minuta_title).strip()
    return cleaned or minuta_title


def _format_address(company: CompanyDocument) -> str | None:
    addr = company.address
    if addr is None:
        return None
    parts = [
        p
        for p in [
            addr.street,
            addr.number,
            addr.complement,
            addr.neighborhood,
            addr.postal_code,
        ]
        if p
    ]
    return ", ".join(parts) if parts else None


def _party_from_company(company: CompanyDocument) -> PartySnapshot:
    addr = company.address
    return PartySnapshot(
        company_id=company.id,
        legal_name=company.legal_name,
        trade_name=company.trade_name,
        tax_id=company.tax_id,
        address_line=_format_address(company),
        city=addr.city if addr else None,
        state=addr.state if addr else None,
        email=company.email,
        phone=company.phone,
        legal_representative=company.legal_representative,
    )


def _party_block(party: PartySnapshot) -> str:
    name = party.legal_name
    city_state = ""
    if party.city or party.state:
        city_state = f", {party.city or ''}/{party.state or ''}"
    address = party.address_line or "endereço não informado"
    email = party.email or "não informado"
    phone = party.phone or "não informado"
    rep = party.legal_representative or "não informado"
    return (
        f"{name}, pessoa jurídica de direito privado, inscrita no CNPJ sob o nº {party.tax_id}, "
        f"com sede na {address}{city_state}, e-mail: {email}, telefone: {phone}, "
        f"neste ato representada por {rep}."
    )


def _format_price(price: float | None, negotiable: bool) -> str:
    if negotiable or price is None:
        return "A combinar"
    return f"R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class ContractProposalsService:
    def __init__(
        self,
        repository: ContractProposalsRepository,
        conversations_repo: ConversationsRepository,
        companies_repo: CompaniesRepository,
        opportunities_repo: OpportunitiesRepository,
        sections_repo: ContractSectionsRepository,
        auth_repo: AuthRepository,
        agreements_service: AgreementsService,
        messages_repo: ConversationMessagesRepository | None = None,
        realtime: ConversationRealtimePublisher | None = None,
        platform_settings_repository: PlatformSettingsRepository | None = None,
    ) -> None:
        self._repo = repository
        self._conversations = conversations_repo
        self._companies = companies_repo
        self._opportunities = opportunities_repo
        self._sections = sections_repo
        self._auth = auth_repo
        self._agreements = agreements_service
        self._messages = messages_repo
        self._realtime = realtime
        self._platform_settings = platform_settings_repository

    async def _resolve_user(self, firebase_uid: str):
        user = await self._auth.get_by_firebase_uid(firebase_uid)
        if user is None:
            raise NotFoundError("User not found.", code="user_not_found")
        return user

    def _role_for(self, doc: ContractProposalDocument, user_id: UUID) -> str | None:
        if user_id == doc.offerer_user_id:
            return "offerer"
        if user_id == doc.interested_user_id:
            return "interested"
        return None

    def _ensure_participant(self, doc: ContractProposalDocument, user_id: UUID) -> str:
        role = self._role_for(doc, user_id)
        if role is None:
            raise ForbiddenError("You do not have access to this contract proposal.")
        return role

    @staticmethod
    def _is_admin_foro_mode(mode: ForoFillMode | str | None) -> bool:
        return mode in (ForoFillMode.ADMIN, ForoFillMode.ADMIN.value, "admin")

    async def _resolve_foro_settings(
        self,
    ) -> tuple[ForoFillMode, str | None, str | None]:
        if self._platform_settings is None:
            return ForoFillMode.COMPANY, None, None
        settings = await self._platform_settings.get_or_create()
        mode = settings.foro_fill_mode
        if mode in (ForoFillMode.ADMIN, ForoFillMode.ADMIN.value, "admin"):
            mode = ForoFillMode.ADMIN
        else:
            mode = ForoFillMode.COMPANY
        return mode, settings.foro_city, settings.foro_state

    def _refresh_foro_html(
        self, doc: ContractProposalDocument, *, signed_at=None
    ) -> None:
        html = build_foro_html(
            city=doc.foro_city,
            state=doc.foro_state,
            contractor_legal_name=doc.contractor.legal_name,
            contracted_legal_name=doc.contracted.legal_name,
            signed_at=signed_at,
        )
        found = False
        for index, section in enumerate(doc.sections):
            if is_foro_title(section.title):
                doc.sections[index] = section.model_copy(
                    update={
                        "title": FORO_SECTION_DEFINITION["title"],
                        "content_html": html,
                        "is_core": True,
                        "is_editable": False,
                        "is_admin_managed": False,
                        "template_id": None,
                    }
                )
                found = True
        if not found:
            doc.sections.append(
                ProposalSection(
                    title=FORO_SECTION_DEFINITION["title"],
                    content_html=html,
                    sort_order=len(doc.sections),
                    is_core=True,
                    is_admin_managed=False,
                    is_editable=False,
                )
            )

    async def _apply_foro_settings(self, doc: ContractProposalDocument) -> bool:
        mode, city, state = await self._resolve_foro_settings()
        changed = False
        if doc.foro_fill_mode != mode:
            doc.foro_fill_mode = mode
            changed = True
        if self._is_admin_foro_mode(mode) and (
            doc.foro_city != city or doc.foro_state != state
        ):
            doc.foro_city = city
            doc.foro_state = state
            changed = True
        if changed:
            self._refresh_foro_html(doc)
        return changed

    async def _sync_missing_admin_sections(
        self, doc: ContractProposalDocument
    ) -> ContractProposalDocument:
        """Keep negotiating minutas aligned with active admin templates.

        - Adds newly created matching templates
        - Removes admin sections whose template is inactive or no longer applies
        - Does not overwrite content of sections already on the minuta (admin
          content updates are pushed when the template is edited)
        """
        if doc.status not in NEGOTIATING_STATUSES:
            return doc
        opp_type = proposal_opportunity_type(doc)
        if opp_type is not None:
            templates = await self._sections.list_active_by_opportunity_type(opp_type)
        else:
            templates = await self._sections.list_active_by_type(doc.contract_type)
        template_ids = {t.id for t in templates}
        changed = False
        filtered: list[ProposalSection] = []
        for section in doc.sections:
            if section.is_admin_managed and (
                is_foro_title(section.title)
                or (
                    section.template_id is not None
                    and section.template_id not in template_ids
                )
            ):
                changed = True
                continue
            filtered.append(section)
        doc.sections = filtered
        if add_missing_admin_sections(doc, templates):
            changed = True
        if await self._apply_foro_settings(doc):
            changed = True
        if ensure_foro_section(doc):
            changed = True
            if reorder_proposal_sections(doc, templates):
                changed = True
        if changed:
            return await self._repo.replace(doc)
        return doc

    def _to_response(
        self, doc: ContractProposalDocument, *, user_id: UUID | None = None
    ) -> ContractProposalResponse:
        my_role = self._role_for(doc, user_id) if user_id else None
        pdf = None
        if doc.pdf_file:
            pdf = ProposalPdfFileResponse.model_validate(doc.pdf_file.model_dump())
        foro_html = build_foro_html(
            city=doc.foro_city,
            state=doc.foro_state,
            contractor_legal_name=doc.contractor.legal_name,
            contracted_legal_name=doc.contracted.legal_name,
        )
        section_responses: list[ProposalSectionResponse] = []
        for section in sorted(doc.sections, key=lambda x: x.sort_order):
            payload = section.model_dump()
            if is_foro_title(section.title):
                payload["content_html"] = foro_html
                payload["title"] = FORO_SECTION_DEFINITION["title"]
                payload["is_core"] = True
                payload["is_editable"] = False
            section_responses.append(ProposalSectionResponse.model_validate(payload))
        return ContractProposalResponse(
            id=doc.id,
            conversation_id=doc.conversation_id,
            opportunity_id=doc.opportunity_id,
            offerer_company_id=doc.offerer_company_id,
            interested_company_id=doc.interested_company_id,
            offerer_user_id=doc.offerer_user_id,
            interested_user_id=doc.interested_user_id,
            created_by_user_id=doc.created_by_user_id,
            title=doc.title,
            contract_type=doc.contract_type,
            status=doc.status,
            contractor=PartySnapshotResponse.model_validate(doc.contractor.model_dump()),
            contracted=PartySnapshotResponse.model_validate(doc.contracted.model_dump()),
            opportunity=OpportunitySnapshotResponse.model_validate(
                doc.opportunity.model_dump()
            ),
            sections=section_responses,
            foro_city=doc.foro_city,
            foro_state=doc.foro_state,
            foro_fill_mode=doc.foro_fill_mode,
            pdf_file=pdf,
            agreement_id=doc.agreement_id,
            change_request_message=doc.change_request_message,
            rejection_reason=doc.rejection_reason,
            my_role=my_role,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    async def create(
        self, payload: ContractProposalCreate, *, firebase_uid: str
    ) -> ContractProposalResponse:
        user = await self._resolve_user(firebase_uid)
        conversation = await self._conversations.get_by_id(payload.conversation_id)
        if conversation is None:
            raise NotFoundError("Conversation not found.")
        if user.id != conversation.offerer_user_id:
            raise ForbiddenError("Apenas a empresa ofertante pode propor um acordo.")

        existing = await self._repo.find_active_for_conversation(conversation.id)
        if existing is not None:
            raise ConflictError(
                "Já existe uma minuta ativa para esta conversa.",
                details={"proposal_id": str(existing.id)},
            )

        offerer = await self._companies.get(conversation.offerer_company_id)
        interested = await self._companies.get(conversation.interested_company_id)
        if offerer is None or interested is None:
            raise NotFoundError("Empresa da conversa não encontrada.")

        opportunity = await self._opportunities.get(conversation.opportunity_id)
        if opportunity is None:
            raise NotFoundError("Opportunity not found.")

        periodicity_label = None
        if opportunity.periodicity:
            periodicity_label = _PERIODICITY_LABELS.get(
                opportunity.periodicity, str(opportunity.periodicity)
            )

        contractor = _party_from_company(interested)
        contracted = _party_from_company(offerer)
        opp_snap = OpportunitySnapshot(
            opportunity_id=opportunity.id,
            title=opportunity.title,
            description=opportunity.description,
            category=opportunity.category,
            price=opportunity.price,
            price_negotiable=opportunity.price_negotiable,
            periodicity=str(opportunity.periodicity) if opportunity.periodicity else None,
            prazo=periodicity_label,
            opportunity_type=str(opportunity.opportunity_type)
            if opportunity.opportunity_type
            else None,
        )

        valor = _format_price(opportunity.price, opportunity.price_negotiable)
        prazo = periodicity_label or "A combinar"
        core = build_core_sections_html(
            contractor_block=_party_block(contractor),
            contracted_block=_party_block(contracted),
            opportunity_title=opportunity.title,
            opportunity_description=opportunity.description,
            valor=valor,
            prazo=prazo,
            opportunity_type=opp_snap.opportunity_type,
        )
        sections: list[ProposalSection] = []
        for idx, (title, html) in enumerate(core):
            sections.append(
                ProposalSection(
                    title=title,
                    content_html=html,
                    sort_order=idx,
                    is_core=True,
                    is_admin_managed=False,
                    is_editable=False,
                )
            )

        if opp_snap.opportunity_type:
            templates = await self._sections.list_active_by_opportunity_type(
                opp_snap.opportunity_type
            )
        else:
            templates = await self._sections.list_active_by_type(
                payload.contract_type or contract_type_for(None)
            )
        base = len(sections)
        for offset, tmpl in enumerate(templates):
            if is_foro_title(tmpl.title):
                continue
            sections.append(
                ProposalSection(
                    title=tmpl.title,
                    content_html=tmpl.content_html,
                    sort_order=base + offset,
                    is_core=False,
                    is_admin_managed=True,
                    is_editable=bool(tmpl.is_company_editable),
                    template_id=tmpl.id,
                )
            )

        foro_mode, foro_city, foro_state = await self._resolve_foro_settings()
        if not self._is_admin_foro_mode(foro_mode):
            foro_city = contracted.city
            foro_state = contracted.state

        doc = ContractProposalDocument(
            conversation_id=conversation.id,
            opportunity_id=opportunity.id,
            offerer_company_id=conversation.offerer_company_id,
            interested_company_id=conversation.interested_company_id,
            offerer_user_id=conversation.offerer_user_id,
            interested_user_id=conversation.interested_user_id,
            created_by_user_id=user.id,
            title=minuta_title_for(opp_snap.opportunity_type),
            contract_type=contract_type_for(opp_snap.opportunity_type),
            status=ContractProposalStatus.DRAFT,
            contractor=contractor,
            contracted=contracted,
            opportunity=opp_snap,
            sections=sections,
            foro_city=foro_city,
            foro_state=foro_state,
            foro_fill_mode=foro_mode,
        )
        ensure_foro_section(doc)
        reorder_proposal_sections(doc, templates)
        self._refresh_foro_html(doc)
        await self._repo.create(doc)
        await self._log_negotiation_event(
            conversation_id=conversation.id,
            actor=user,
            kind=ConversationSystemEventKind.AGREEMENT_PROPOSED,
            offerer_user_id=conversation.offerer_user_id,
            interested_user_id=conversation.interested_user_id,
        )
        return self._to_response(doc, user_id=user.id)

    async def get(
        self, proposal_id: UUID, *, firebase_uid: str
    ) -> ContractProposalResponse:
        user = await self._resolve_user(firebase_uid)
        doc = await self._repo.get(proposal_id)
        if doc is None:
            raise NotFoundError("Contract proposal not found.")
        self._ensure_participant(doc, user.id)
        doc = await self._sync_missing_admin_sections(doc)
        return self._to_response(doc, user_id=user.id)

    async def list(
        self, params: ContractProposalListParams, *, firebase_uid: str
    ) -> ContractProposalListResponse:
        user = await self._resolve_user(firebase_uid)
        skip = (params.page - 1) * params.page_size
        items = await self._repo.list_for_user(
            user_id=user.id,
            conversation_id=params.conversation_id,
            skip=skip,
            limit=params.page_size,
        )
        total = await self._repo.count_for_user(
            user_id=user.id, conversation_id=params.conversation_id
        )
        return ContractProposalListResponse(
            items=[
                ContractProposalListItem(
                    id=d.id,
                    conversation_id=d.conversation_id,
                    opportunity_id=d.opportunity_id,
                    title=d.title,
                    status=d.status,
                    contract_type=d.contract_type,
                    opportunity_type=d.opportunity.opportunity_type,
                    agreement_id=d.agreement_id,
                    created_at=d.created_at,
                    updated_at=d.updated_at,
                )
                for d in items
            ],
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    def _apply_party_patch(self, party: PartySnapshot, data: dict) -> None:
        for key, value in data.items():
            if value is not None or key in data:
                setattr(party, key, value)

    async def update(
        self,
        proposal_id: UUID,
        payload: ContractProposalUpdate,
        *,
        firebase_uid: str,
    ) -> ContractProposalResponse:
        user = await self._resolve_user(firebase_uid)
        doc = await self._repo.get(proposal_id)
        if doc is None:
            raise NotFoundError("Contract proposal not found.")
        role = self._ensure_participant(doc, user.id)
        if role != "offerer":
            raise ForbiddenError("Apenas a empresa ofertante pode editar a minuta.")
        if doc.status not in _EDITABLE:
            raise ValidationAppError("A minuta não pode ser editada neste status.")

        doc = await self._sync_missing_admin_sections(doc)

        if payload.title is not None:
            doc.title = payload.title
        if payload.contract_type is not None:
            doc.contract_type = payload.contract_type
            doc = await self._sync_missing_admin_sections(doc)
        if payload.contractor is not None:
            self._apply_party_patch(
                doc.contractor, payload.contractor.model_dump(exclude_unset=True)
            )
        if payload.contracted is not None:
            self._apply_party_patch(
                doc.contracted, payload.contracted.model_dump(exclude_unset=True)
            )
        if payload.opportunity is not None:
            for key, value in payload.opportunity.model_dump(exclude_unset=True).items():
                setattr(doc.opportunity, key, value)

        foro_touched = (
            "foro_city" in payload.model_fields_set
            or "foro_state" in payload.model_fields_set
        )
        if foro_touched:
            live_mode, _, _ = await self._resolve_foro_settings()
            if self._is_admin_foro_mode(live_mode) or self._is_admin_foro_mode(
                doc.foro_fill_mode
            ):
                raise ValidationAppError(
                    "A comarca do foro é definida pelo administrador."
                )
            if "foro_city" in payload.model_fields_set:
                city = (payload.foro_city or "").strip()
                doc.foro_city = city or None
            if "foro_state" in payload.model_fields_set:
                state = (payload.foro_state or "").strip().upper()
                if state and state not in STATE_NEIGHBORS:
                    raise ValidationAppError("Informe um estado (UF) válido para o foro.")
                doc.foro_state = state or None

        if payload.sections is not None:
            doc.sections = self._normalize_sections(payload.sections, existing=doc.sections)

        await self._apply_foro_settings(doc)
        ensure_foro_section(doc)
        opp_type = proposal_opportunity_type(doc)
        if opp_type is not None:
            templates = await self._sections.list_active_by_opportunity_type(opp_type)
        else:
            templates = await self._sections.list_active_by_type(doc.contract_type)
        reorder_proposal_sections(doc, templates)
        self._refresh_foro_html(doc)

        if doc.status == ContractProposalStatus.CHANGES_REQUESTED:
            doc.status = ContractProposalStatus.DRAFT
            doc.change_request_message = None

        await self._repo.replace(doc)
        return self._to_response(doc, user_id=user.id)

    def _normalize_sections(
        self,
        sections: list[ProposalSectionInput],
        *,
        existing: list[ProposalSection],
    ) -> list[ProposalSection]:
        if not sections:
            raise ValidationAppError("A minuta precisa de ao menos uma seção.")

        existing_by_id = {s.id: s for s in existing}
        locked_ids = {
            s.id
            for s in existing
            if s.is_core or (s.is_admin_managed and not s.is_editable)
        }
        incoming_ids = {item.id for item in sections if item.id is not None}
        missing_locked = locked_ids - incoming_ids
        if missing_locked:
            raise ValidationAppError(
                "Seções automáticas ou administrativas bloqueadas não podem ser removidas."
            )

        normalized: list[ProposalSection] = []
        for idx, item in enumerate(sections):
            prev = existing_by_id.get(item.id) if item.id else None
            if prev and prev.is_core:
                normalized.append(
                    ProposalSection(
                        id=prev.id,
                        title=prev.title,
                        content_html=prev.content_html,
                        sort_order=prev.sort_order,
                        is_core=True,
                        is_admin_managed=False,
                        is_editable=False,
                        template_id=None,
                    )
                )
                continue
            if prev and prev.is_admin_managed and not prev.is_editable:
                normalized.append(
                    ProposalSection(
                        id=prev.id,
                        title=prev.title,
                        content_html=prev.content_html,
                        sort_order=item.sort_order if item.sort_order else idx,
                        is_core=prev.is_core,
                        is_admin_managed=True,
                        is_editable=False,
                        template_id=prev.template_id,
                    )
                )
                continue
            is_admin = bool(item.is_admin_managed or (prev and prev.is_admin_managed))
            is_editable = (
                prev.is_editable
                if prev and prev.is_admin_managed
                else (True if not is_admin else item.is_editable)
            )
            if prev and prev.is_admin_managed:
                is_editable = prev.is_editable
            normalized.append(
                ProposalSection(
                    id=item.id or new_uuid(),
                    title=item.title,
                    content_html=item.content_html,
                    sort_order=item.sort_order if item.sort_order else idx,
                    is_core=item.is_core if prev is None else prev.is_core,
                    is_admin_managed=is_admin,
                    is_editable=is_editable if is_admin else True,
                    template_id=(
                        prev.template_id if prev else item.template_id
                    ),
                )
            )
        return normalized

    async def _log_negotiation_event(
        self,
        *,
        conversation_id: UUID,
        actor,
        kind: ConversationSystemEventKind,
        offerer_user_id: UUID,
        interested_user_id: UUID,
        reason: str | None = None,
    ) -> None:
        if self._messages is None:
            return
        actor_name = actor.name or actor.email or "Usuário"
        if actor.id == offerer_user_id:
            author_role = ConversationAuthorRole.OFFERER
        elif actor.id == interested_user_id:
            author_role = ConversationAuthorRole.INTERESTED
        else:
            author_role = ConversationAuthorRole.SYSTEM
        now = utcnow()
        clock = now.strftime("%H:%M")
        try:
            from zoneinfo import ZoneInfo

            clock = now.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M")
        except Exception:  # noqa: BLE001
            pass
        reason_suffix = f" por: {reason}" if reason and reason.strip() else ""
        bodies = {
            ConversationSystemEventKind.AGREEMENT_PROPOSED: (
                f"{actor_name} propôs um acordo às {clock}."
            ),
            ConversationSystemEventKind.AGREEMENT_SUBMITTED: (
                f"{actor_name} enviou a minuta para aprovação às {clock}."
            ),
            ConversationSystemEventKind.AGREEMENT_CHANGES_REQUESTED: (
                f"{actor_name} solicitou alterações na minuta às {clock}{reason_suffix}."
            ),
            ConversationSystemEventKind.AGREEMENT_REJECTED: (
                f"{actor_name} rejeitou a minuta às {clock}{reason_suffix}."
            ),
            ConversationSystemEventKind.AGREEMENT_APPROVED: (
                f"{actor_name} aprovou a minuta às {clock}."
            ),
        }
        body = bodies.get(kind, f"{actor_name} atualizou a minuta às {clock}.")
        message = OpportunityConversationMessageDocument(
            conversation_id=conversation_id,
            author_id=actor.id,
            author_company_id=None,
            author_role=author_role,
            message_type=ConversationMessageType.SYSTEM_EVENT,
            body=body,
            event_kind=kind,
            event_actor_user_id=actor.id,
            event_actor_name=actor_name,
            event_reason=reason.strip() if reason and reason.strip() else None,
        )
        await self._messages.create(message)
        await self._conversations.update(conversation_id, {"last_message_at": now})
        if self._realtime is not None:
            conversation = await self._conversations.get_by_id(conversation_id)
            msg_response = _message_to_response(message, author_name=actor_name)
            event_data: dict[str, object] = {
                "conversation_id": str(conversation_id),
                "message_id": str(message.id),
                "message_type": message.message_type.value,
                "message": _message_event_payload(msg_response),
            }
            if conversation is not None:
                event_data["opportunity_id"] = str(conversation.opportunity_id)
                event_data["opportunity_title"] = conversation.opportunity_title
                event_data["status"] = str(conversation.status)
                participant_ids = [
                    conversation.offerer_user_id,
                    conversation.interested_user_id,
                ]
            else:
                participant_ids = [offerer_user_id, interested_user_id]
            for user_id in participant_ids:
                await self._realtime.publish_to_user(
                    user_id, "message_created", event_data
                )
            await self._realtime.publish_to_admins("message_created", event_data)
            await self._realtime.publish_to_thread(
                conversation_id, "message_created", event_data
            )

    def _validate_for_pdf(self, doc: ContractProposalDocument) -> None:
        missing: list[str] = []
        for label, party in (("Contratante", doc.contractor), ("Contratada", doc.contracted)):
            if not party.legal_name:
                missing.append(f"{label}: razão social")
            if not party.tax_id:
                missing.append(f"{label}: CNPJ")
            if not party.address_line:
                missing.append(f"{label}: endereço")
            if not party.legal_representative:
                missing.append(f"{label}: representante legal")
        if not doc.sections:
            missing.append("seções")
        if not (doc.foro_city or "").strip():
            missing.append("Foro: cidade")
        if not (doc.foro_state or "").strip():
            missing.append("Foro: estado")
        if missing:
            raise ValidationAppError(
                "Campos obrigatórios ausentes para gerar o PDF.",
                details={"missing": missing},
            )

    async def generate_pdf(
        self, proposal_id: UUID, *, firebase_uid: str
    ) -> ContractProposalResponse:
        user = await self._resolve_user(firebase_uid)
        doc = await self._repo.get(proposal_id)
        if doc is None:
            raise NotFoundError("Contract proposal not found.")
        role = self._ensure_participant(doc, user.id)
        if role != "offerer":
            raise ForbiddenError("Apenas a empresa ofertante pode gerar o PDF.")
        if doc.status not in _EDITABLE:
            raise ValidationAppError("PDF só pode ser gerado em rascunho.")

        doc = await self._sync_missing_admin_sections(doc)
        await self._apply_foro_settings(doc)
        self._refresh_foro_html(doc)

        self._validate_for_pdf(doc)
        pdf_bytes = render_proposal_pdf(doc)
        if not pdf_bytes:
            raise ValidationAppError("Falha ao gerar o PDF.")

        key = build_storage_key("contract_proposals", user.id, "pdf")
        url = await firebase.upload_storage_bytes(
            key, pdf_bytes, content_type="application/pdf"
        )
        doc.pdf_file = ProposalPdfFile(
            storage_key=key,
            url=url,
            sha256=sha256_bytes(pdf_bytes),
            filename=f"minuta-{doc.id}.pdf",
            page_count=pdf_page_count(pdf_bytes),
            size_bytes=len(pdf_bytes),
        )
        doc.status = ContractProposalStatus.PENDING_APPROVAL
        await self._repo.replace(doc)
        await self._log_negotiation_event(
            conversation_id=doc.conversation_id,
            actor=user,
            kind=ConversationSystemEventKind.AGREEMENT_SUBMITTED,
            offerer_user_id=doc.offerer_user_id,
            interested_user_id=doc.interested_user_id,
        )
        return self._to_response(doc, user_id=user.id)

    async def approve(
        self, proposal_id: UUID, *, firebase_uid: str
    ) -> ApproveProposalResponse:
        user = await self._resolve_user(firebase_uid)
        doc = await self._repo.get(proposal_id)
        if doc is None:
            raise NotFoundError("Contract proposal not found.")
        role = self._ensure_participant(doc, user.id)
        if role != "interested":
            raise ForbiddenError("Apenas a empresa interessada pode aprovar a minuta.")
        if doc.status != ContractProposalStatus.PENDING_APPROVAL:
            raise ValidationAppError("A minuta não está aguardando aprovação.")
        if doc.pdf_file is None:
            raise ValidationAppError("PDF da minuta não encontrado.")

        agreement_title = to_agreement_title(doc.title)
        self._refresh_foro_html(doc)
        # Regenerate PDF with agreement title (without "Minuta de").
        pdf_source = doc.model_copy(update={"title": agreement_title})
        pdf_bytes = render_proposal_pdf(pdf_source)
        if not pdf_bytes:
            raise ValidationAppError("Falha ao gerar o PDF do contrato.")
        key = build_storage_key("agreements", doc.offerer_user_id, "pdf")
        url = await firebase.upload_storage_bytes(
            key, pdf_bytes, content_type="application/pdf"
        )
        agreement_pdf = ProposalPdfFile(
            storage_key=key,
            url=url,
            sha256=sha256_bytes(pdf_bytes),
            filename=f"contrato-{doc.id}.pdf",
            page_count=pdf_page_count(pdf_bytes),
            size_bytes=len(pdf_bytes),
        )

        agreement = await self._agreements.create_from_contract_proposal(
            title=agreement_title,
            description=doc.opportunity.description,
            owner_user_id=doc.offerer_user_id,
            offerer_company_id=doc.offerer_company_id,
            interested_company_id=doc.interested_company_id,
            offerer_user_id=doc.offerer_user_id,
            interested_user_id=doc.interested_user_id,
            pdf_file=agreement_pdf,
            opportunity_id=doc.opportunity_id,
            conversation_id=doc.conversation_id,
            contract_proposal_id=doc.id,
        )

        doc.status = ContractProposalStatus.SENT_TO_AGREEMENTS
        doc.agreement_id = agreement.id
        await self._repo.replace(doc)
        await self._log_negotiation_event(
            conversation_id=doc.conversation_id,
            actor=user,
            kind=ConversationSystemEventKind.AGREEMENT_APPROVED,
            offerer_user_id=doc.offerer_user_id,
            interested_user_id=doc.interested_user_id,
        )
        return ApproveProposalResponse(
            proposal=self._to_response(doc, user_id=user.id),
            agreement_id=agreement.id,
        )

    async def request_changes(
        self,
        proposal_id: UUID,
        payload: RequestChangesRequest,
        *,
        firebase_uid: str,
    ) -> ContractProposalResponse:
        user = await self._resolve_user(firebase_uid)
        doc = await self._repo.get(proposal_id)
        if doc is None:
            raise NotFoundError("Contract proposal not found.")
        role = self._ensure_participant(doc, user.id)
        if role != "interested":
            raise ForbiddenError("Apenas a empresa interessada pode solicitar alterações.")
        if doc.status != ContractProposalStatus.PENDING_APPROVAL:
            raise ValidationAppError("A minuta não está aguardando aprovação.")
        doc.status = ContractProposalStatus.CHANGES_REQUESTED
        doc.change_request_message = payload.message
        await self._repo.replace(doc)
        await self._log_negotiation_event(
            conversation_id=doc.conversation_id,
            actor=user,
            kind=ConversationSystemEventKind.AGREEMENT_CHANGES_REQUESTED,
            offerer_user_id=doc.offerer_user_id,
            interested_user_id=doc.interested_user_id,
            reason=payload.message,
        )
        return self._to_response(doc, user_id=user.id)

    async def reject(
        self,
        proposal_id: UUID,
        payload: RejectProposalRequest,
        *,
        firebase_uid: str,
    ) -> ContractProposalResponse:
        user = await self._resolve_user(firebase_uid)
        doc = await self._repo.get(proposal_id)
        if doc is None:
            raise NotFoundError("Contract proposal not found.")
        role = self._ensure_participant(doc, user.id)
        if role != "interested":
            raise ForbiddenError("Apenas a empresa interessada pode rejeitar a minuta.")
        if doc.status != ContractProposalStatus.PENDING_APPROVAL:
            raise ValidationAppError("A minuta não está aguardando aprovação.")
        doc.status = ContractProposalStatus.REJECTED
        doc.rejection_reason = payload.reason
        await self._repo.replace(doc)
        await self._log_negotiation_event(
            conversation_id=doc.conversation_id,
            actor=user,
            kind=ConversationSystemEventKind.AGREEMENT_REJECTED,
            offerer_user_id=doc.offerer_user_id,
            interested_user_id=doc.interested_user_id,
            reason=payload.reason,
        )
        return self._to_response(doc, user_id=user.id)

    async def admin_list(
        self, *, page: int, page_size: int, conversation_id: UUID | None = None
    ) -> ContractProposalListResponse:
        skip = (page - 1) * page_size
        items = await self._repo.list_all(
            conversation_id=conversation_id, skip=skip, limit=page_size
        )
        total = await self._repo.count_all(conversation_id=conversation_id)
        return ContractProposalListResponse(
            items=[
                ContractProposalListItem(
                    id=d.id,
                    conversation_id=d.conversation_id,
                    opportunity_id=d.opportunity_id,
                    title=d.title,
                    status=d.status,
                    contract_type=d.contract_type,
                    opportunity_type=d.opportunity.opportunity_type,
                    agreement_id=d.agreement_id,
                    created_at=d.created_at,
                    updated_at=d.updated_at,
                )
                for d in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def admin_get(self, proposal_id: UUID) -> ContractProposalResponse:
        doc = await self._repo.get(proposal_id)
        if doc is None:
            raise NotFoundError("Contract proposal not found.")
        doc = await self._sync_missing_admin_sections(doc)
        return self._to_response(doc)


__all__ = ["ContractProposalsService"]
