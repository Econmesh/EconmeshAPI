"""Acesso a dados de ``maturity_diagnostics``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.core.exceptions import ConflictError
from src.modules.maturity_diagnostics.model import (
    DiagnosticResponse,
    DiagnosticStatus,
    MaturityDiagnosticDocument,
)
from src.shared.utils.time import utcnow

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class MaturityDiagnosticsRepository:
    COLLECTION: str = MaturityDiagnosticDocument.collection_name

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection: AsyncCollection = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index(
            [("agent_user_id", ASCENDING), ("updated_at", DESCENDING)],
            name="ix_diag_agent_updated",
        )
        await self._collection.create_index(
            [("company_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_diag_company_created",
        )
        # No máximo um diagnóstico aberto por empresa.
        await self._collection.create_index(
            [("company_id", ASCENDING)],
            unique=True,
            name="uniq_diag_open_company",
            partialFilterExpression={"is_open": True},
        )

    async def create(self, doc: MaturityDiagnosticDocument) -> MaturityDiagnosticDocument:
        try:
            await self._collection.insert_one(doc.to_mongo())
        except DuplicateKeyError as exc:
            raise ConflictError(
                "There is already an open diagnostic for this company.",
                code="diagnostic_already_open",
            ) from exc
        return doc

    async def get(self, diagnostic_id: UUID) -> MaturityDiagnosticDocument | None:
        raw = await self._collection.find_one({"_id": diagnostic_id})
        return MaturityDiagnosticDocument.model_validate(raw) if raw else None

    async def get_open_for_company(self, company_id: UUID) -> MaturityDiagnosticDocument | None:
        raw = await self._collection.find_one({"company_id": company_id, "is_open": True})
        return MaturityDiagnosticDocument.model_validate(raw) if raw else None

    async def list_for_agent(
        self,
        agent_user_id: UUID,
        *,
        company_ids: list[UUID],
        company_id: UUID | None = None,
        status: DiagnosticStatus | None = None,
        limit: int = 200,
    ) -> list[MaturityDiagnosticDocument]:
        query: dict[str, Any] = {"agent_user_id": agent_user_id}
        if company_id is not None:
            query["company_id"] = company_id
        else:
            query["company_id"] = {"$in": company_ids}
        if status is not None:
            query["status"] = status.value
        cursor = self._collection.find(query).sort("updated_at", DESCENDING).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [MaturityDiagnosticDocument.model_validate(doc) for doc in docs]

    async def list_for_companies(
        self, company_ids: list[UUID]
    ) -> list[MaturityDiagnosticDocument]:
        if not company_ids:
            return []
        cursor = self._collection.find(
            {"company_id": {"$in": company_ids}},
            # O resumo da lista não precisa das respostas.
            projection={"responses": 0, "result": 0},
        ).sort("updated_at", DESCENDING)
        docs = await cursor.to_list(length=None)
        return [
            MaturityDiagnosticDocument.model_validate({**doc, "responses": {}}) for doc in docs
        ]

    async def save_responses(
        self,
        diagnostic_id: UUID,
        responses: dict[str, DiagnosticResponse],
        *,
        current_step: str | None = None,
    ) -> MaturityDiagnosticDocument | None:
        """Grava cada resposta em ``responses.<id>`` (sem sobrescrever as demais)."""
        now = utcnow()
        set_fields: dict[str, Any] = {
            f"responses.{qid}": resp.model_dump(mode="python")
            for qid, resp in responses.items()
        }
        set_fields["updated_at"] = now
        if current_step is not None:
            set_fields["current_step"] = current_step
        raw = await self._collection.find_one_and_update(
            {"_id": diagnostic_id, "is_open": True},
            {"$set": set_fields},
            return_document=ReturnDocument.AFTER,
        )
        return MaturityDiagnosticDocument.model_validate(raw) if raw else None

    async def update(
        self,
        diagnostic_id: UUID,
        patch: dict[str, Any],
        *,
        only_open: bool = True,
    ) -> MaturityDiagnosticDocument | None:
        query: dict[str, Any] = {"_id": diagnostic_id}
        if only_open:
            query["is_open"] = True
        patch = {**patch, "updated_at": utcnow()}
        raw = await self._collection.find_one_and_update(
            query, {"$set": patch}, return_document=ReturnDocument.AFTER
        )
        return MaturityDiagnosticDocument.model_validate(raw) if raw else None

    async def count_for_agent(
        self, agent_user_id: UUID, *, open_only: bool | None = None
    ) -> int:
        query: dict[str, Any] = {"agent_user_id": agent_user_id}
        if open_only is True:
            query["is_open"] = True
        elif open_only is False:
            query["status"] = DiagnosticStatus.COMPLETED.value
        return await self._collection.count_documents(query)


__all__ = ["MaturityDiagnosticsRepository"]
