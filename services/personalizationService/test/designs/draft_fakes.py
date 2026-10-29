"""Keep draft persistence doubles outside the installed package."""

from dataclasses import replace
from uuid import UUID, uuid4

from personalization.application.designs.draft_record import (
    DesignCondition,
    DesignState,
    DraftContent,
    DraftRecord,
    SavedApplication,
    draft_revision,
)
from personalization.application.errors.design_error import (
    DesignError,
    DesignFailure,
)
from personalization.application.errors.security_error import (
    SecurityError,
    SecurityFailure,
)


class MemoryDesignRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, DraftRecord] = {}
        self.audit: list[UUID] = []
        self.calls = 0
        self.failure: DesignFailure | None = None

    def _check(self) -> None:
        self.calls += 1
        if self.failure is not None:
            raise DesignError(self.failure)

    def create(self, owner_id: UUID, content: DraftContent) -> DraftRecord:
        self._check()
        record = DraftRecord(
            uuid4(),
            owner_id,
            content.variant_id,
            content.template_id,
            DesignState.DRAFT,
            1,
            None,
            None,
            tuple(
                SavedApplication(uuid4(), item)
                for item in content.canonical().applications
            ),
        )
        self.records[record.id] = record
        self.audit.append(owner_id)
        return record

    def get(self, owner_id: UUID, design_id: UUID) -> DraftRecord:
        self._check()
        if design_id not in self.records:
            raise DesignError(DesignFailure.DESIGN_NOT_FOUND)
        record = self.records[design_id]
        if record.owner_id != owner_id:
            raise SecurityError(SecurityFailure.FORBIDDEN)
        return record

    def update(
        self,
        owner_id: UUID,
        design_id: UUID,
        content: DraftContent,
        condition: DesignCondition,
    ) -> DraftRecord:
        original = self.get(owner_id, design_id)
        if original.state is not DesignState.DRAFT:
            raise DesignError(DesignFailure.DESIGN_NOT_EDITABLE)
        if not condition.matches(draft_revision(original)):
            raise DesignError(DesignFailure.DESIGN_PRECONDITION_FAILED)
        if original.content == content.canonical():
            return original
        result = replace(
            original,
            variant_id=content.variant_id,
            template_id=content.template_id,
            version=original.version + 1,
            front_preview_id=None,
            back_preview_id=None,
            applications=tuple(
                SavedApplication(uuid4(), item)
                for item in content.canonical().applications
            ),
        )
        self.records[design_id] = result
        self.audit.append(owner_id)
        return result

    def copy(self, owner_id: UUID, design_id: UUID) -> DraftRecord:
        return self.create(owner_id, self.get(owner_id, design_id).content)

    def list(
        self, owner_id: UUID, after: UUID | None, limit: int
    ) -> tuple[DraftRecord, ...]:
        self._check()
        return tuple(
            sorted(
                (
                    record
                    for record in self.records.values()
                    if record.owner_id == owner_id
                    and (after is None or record.id.int > after.int)
                ),
                key=lambda row: row.id.int,
            )[:limit]
        )
