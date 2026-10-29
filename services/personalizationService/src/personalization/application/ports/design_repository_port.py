"""Persist owner-scoped choices and local audit in one transaction."""

from typing import Protocol
from uuid import UUID

from personalization.application.designs.draft_record import (
    DesignCondition,
    DraftContent,
    DraftRecord,
)


class DesignRepositoryPort(Protocol):
    def create(self, owner_id: UUID, content: DraftContent) -> DraftRecord: ...

    def get(self, owner_id: UUID, design_id: UUID) -> DraftRecord: ...

    def update(
        self,
        owner_id: UUID,
        design_id: UUID,
        content: DraftContent,
        condition: DesignCondition,
    ) -> DraftRecord: ...

    def copy(self, owner_id: UUID, design_id: UUID) -> DraftRecord: ...

    def list(
        self, owner_id: UUID, after: UUID | None, limit: int
    ) -> tuple[DraftRecord, ...]: ...
