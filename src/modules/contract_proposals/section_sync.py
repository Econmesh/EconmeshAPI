"""Sync admin contract section templates into negotiating minutas."""

from __future__ import annotations

from src.modules.contract_proposals.core_sections import (
    CORE_SECTION_COUNT,
    core_title_sort_order,
    normalize_core_title,
)
from src.modules.contract_proposals.model import (
    ContractProposalDocument,
    ContractProposalStatus,
    ProposalSection,
)
from src.modules.contract_sections.model import (
    ContractSectionTemplateDocument,
    ContractType,
    SectionAppliesTo,
)

NEGOTIATING_STATUSES: tuple[ContractProposalStatus, ...] = (
    ContractProposalStatus.DRAFT,
    ContractProposalStatus.PENDING_APPROVAL,
    ContractProposalStatus.CHANGES_REQUESTED,
)


def proposal_matches_applies_to(
    proposal_type: ContractType, applies_to: SectionAppliesTo
) -> bool:
    if applies_to in (SectionAppliesTo.TODOS, SectionAppliesTo.OPORTUNIDADES):
        return True
    return proposal_type.value == applies_to.value


def contract_types_for_applies_to(
    applies_to: SectionAppliesTo,
) -> list[ContractType] | None:
    """Return specific contract types to filter, or None for all types."""
    if applies_to in (SectionAppliesTo.TODOS, SectionAppliesTo.OPORTUNIDADES):
        return None
    return [ContractType(applies_to.value)]


def section_from_template(
    tmpl: ContractSectionTemplateDocument, *, sort_order: int
) -> ProposalSection:
    return ProposalSection(
        title=tmpl.title,
        content_html=tmpl.content_html,
        sort_order=sort_order,
        is_core=False,
        is_admin_managed=True,
        is_editable=bool(tmpl.is_company_editable),
        template_id=tmpl.id,
    )


def apply_template_to_section(
    section: ProposalSection, tmpl: ContractSectionTemplateDocument
) -> ProposalSection:
    return section.model_copy(
        update={
            "title": tmpl.title,
            "content_html": tmpl.content_html,
            "is_editable": bool(tmpl.is_company_editable),
            "is_admin_managed": True,
            "template_id": tmpl.id,
        }
    )


def reorder_proposal_sections(
    doc: ContractProposalDocument,
    templates: list[ContractSectionTemplateDocument],
) -> bool:
    """Enforce core → admin(sort_order) → custom ordering on a negotiating minuta."""
    if doc.status not in NEGOTIATING_STATUSES:
        return False

    core: list[ProposalSection] = []
    admin: list[ProposalSection] = []
    custom: list[ProposalSection] = []
    for section in doc.sections:
        canonical = normalize_core_title(section.title)
        if section.is_core or canonical is not None:
            updates: dict = {"is_core": True}
            if canonical and canonical != section.title:
                updates["title"] = canonical
            core.append(section.model_copy(update=updates))
        elif section.is_admin_managed and section.template_id is not None:
            admin.append(section)
        else:
            custom.append(section)

    core.sort(
        key=lambda s: (
            core_title_sort_order(s.title)
            if core_title_sort_order(s.title) is not None
            else 999 + s.sort_order
        )
    )

    admin_by_id = {s.template_id: s for s in admin if s.template_id is not None}
    admin_ordered: list[ProposalSection] = []
    for tmpl in templates:
        section = admin_by_id.pop(tmpl.id, None)
        if section is not None:
            admin_ordered.append(section)
    admin_ordered.extend(sorted(admin_by_id.values(), key=lambda s: s.sort_order))
    custom_ordered = sorted(custom, key=lambda s: s.sort_order)

    ordered = core[:CORE_SECTION_COUNT] + admin_ordered + custom_ordered
    if len(core) > CORE_SECTION_COUNT:
        ordered = ordered + core[CORE_SECTION_COUNT:]

    new_sections: list[ProposalSection] = []
    for index, section in enumerate(ordered):
        if section.sort_order != index:
            new_sections.append(section.model_copy(update={"sort_order": index}))
        else:
            new_sections.append(section)

    changed = False
    if len(new_sections) != len(doc.sections):
        changed = True
    else:
        for before, after in zip(doc.sections, new_sections, strict=True):
            if (
                before.id != after.id
                or before.sort_order != after.sort_order
                or before.title != after.title
                or before.is_core != after.is_core
                or before.content_html != after.content_html
                or before.is_editable != after.is_editable
            ):
                changed = True
                break

    if changed:
        doc.sections = new_sections
    return changed


def add_missing_admin_sections(
    doc: ContractProposalDocument,
    templates: list[ContractSectionTemplateDocument],
) -> bool:
    """Append active admin templates not yet present, then enforce order."""
    if doc.status not in NEGOTIATING_STATUSES:
        return False

    present = {
        s.template_id
        for s in doc.sections
        if s.template_id is not None and s.is_admin_managed
    }
    missing = [t for t in templates if t.id not in present and t.is_active]
    changed = False
    if missing:
        next_order = max((s.sort_order for s in doc.sections), default=-1) + 1
        for tmpl in missing:
            doc.sections.append(section_from_template(tmpl, sort_order=next_order))
            next_order += 1
        changed = True

    if reorder_proposal_sections(doc, templates):
        changed = True
    return changed


def upsert_template_section(
    doc: ContractProposalDocument,
    tmpl: ContractSectionTemplateDocument,
    *,
    all_templates: list[ContractSectionTemplateDocument] | None = None,
) -> bool:
    """Add or update an admin template section on a negotiating minuta."""
    if doc.status not in NEGOTIATING_STATUSES:
        return False
    if not tmpl.is_active or not proposal_matches_applies_to(
        doc.contract_type, tmpl.contract_type
    ):
        removed = remove_template_section(doc, tmpl.id)
        if removed and all_templates is not None:
            reorder_proposal_sections(doc, all_templates)
        return removed

    changed = False
    found = False
    for idx, section in enumerate(doc.sections):
        if section.is_admin_managed and section.template_id == tmpl.id:
            found = True
            updated = apply_template_to_section(section, tmpl)
            if updated != section:
                doc.sections[idx] = updated
                changed = True
            break

    if not found:
        next_order = max((s.sort_order for s in doc.sections), default=-1) + 1
        doc.sections.append(section_from_template(tmpl, sort_order=next_order))
        changed = True

    templates_for_order = all_templates
    if templates_for_order is None:
        templates_for_order = [tmpl]
    if reorder_proposal_sections(doc, templates_for_order):
        changed = True
    return changed


def remove_template_section(
    doc: ContractProposalDocument, template_id
) -> bool:
    if doc.status not in NEGOTIATING_STATUSES:
        return False
    before = len(doc.sections)
    doc.sections = [
        s
        for s in doc.sections
        if not (s.is_admin_managed and s.template_id == template_id)
    ]
    return len(doc.sections) != before


__all__ = [
    "NEGOTIATING_STATUSES",
    "add_missing_admin_sections",
    "contract_types_for_applies_to",
    "proposal_matches_applies_to",
    "remove_template_section",
    "reorder_proposal_sections",
    "upsert_template_section",
]
