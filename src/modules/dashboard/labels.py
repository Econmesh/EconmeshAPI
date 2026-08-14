"""Human-readable labels for dashboard chart keys."""

from __future__ import annotations

AGREEMENT_STATUS_LABELS: dict[str, str] = {
    "draft": "Rascunho",
    "awaiting_send": "Aguardando envio",
    "awaiting_signatures": "Aguardando assinaturas",
    "partially_signed": "Parcialmente assinado",
    "signed": "Assinado",
    "rejected": "Rejeitado",
    "cancelled": "Cancelado",
    "expired": "Expirado",
}

PROPOSAL_STATUS_LABELS: dict[str, str] = {
    "draft": "Rascunho",
    "pending_approval": "Aguardando aprovação",
    "changes_requested": "Alterações solicitadas",
    "approved": "Aprovada",
    "rejected": "Rejeitada",
    "sent_to_agreements": "Enviada para Acordos",
}

OPPORTUNITY_TYPE_LABELS: dict[str, str] = {
    "comercializacao": "Comercialização",
    "simbiose_industrial": "Simbiose industrial",
    "compartilhamento": "Compartilhamento",
}

OFFER_DEMAND_LABELS: dict[str, str] = {
    "gerador": "Oferta (gerador)",
    "receptor": "Demanda (receptor)",
}

SUPPORT_STATUS_LABELS: dict[str, str] = {
    "open": "Aberto",
    "in_progress": "Em andamento",
    "closed": "Fechado",
}

PENDING_AGREEMENT_STATUSES = (
    "awaiting_send",
    "awaiting_signatures",
    "partially_signed",
)

__all__ = [
    "AGREEMENT_STATUS_LABELS",
    "OFFER_DEMAND_LABELS",
    "OPPORTUNITY_TYPE_LABELS",
    "PENDING_AGREEMENT_STATUSES",
    "PROPOSAL_STATUS_LABELS",
    "SUPPORT_STATUS_LABELS",
]
