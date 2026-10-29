"""Represent owned administrative drafts and immutable selections."""

import json
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from personalization.application.designs.analysis_record import (
    AnalysisSelection,
)


class DesignState(StrEnum):
    DRAFT = "BORRADOR"
    FROZEN = "CONGELADO"


@dataclass(frozen=True)
class DraftContent:
    variant_id: UUID
    template_id: UUID
    applications: tuple[AnalysisSelection, ...]

    def canonical(self) -> DraftContent:
        return DraftContent(
            self.variant_id,
            self.template_id,
            tuple(
                sorted(self.applications, key=lambda item: item.zone_id.int)
            ),
        )


@dataclass(frozen=True)
class SavedApplication:
    id: UUID
    selection: AnalysisSelection


@dataclass(frozen=True)
class DraftRecord:
    id: UUID
    owner_id: UUID
    variant_id: UUID
    template_id: UUID
    state: DesignState
    version: int
    front_preview_id: UUID | None
    back_preview_id: UUID | None
    applications: tuple[SavedApplication, ...]

    @property
    def content(self) -> DraftContent:
        return DraftContent(
            self.variant_id,
            self.template_id,
            tuple(item.selection for item in self.applications),
        ).canonical()


@dataclass(frozen=True)
class DesignCondition:
    revisions: frozenset[str] = frozenset()
    any_existing: bool = False

    def matches(self, revision: str) -> bool:
        return self.any_existing or revision in self.revisions


def draft_revision(record: DraftRecord) -> str:
    data = {
        "id": str(record.id),
        "ownerId": str(record.owner_id),
        "variantId": str(record.variant_id),
        "templateId": str(record.template_id),
        "state": record.state.value,
        "version": record.version,
        "frontPreviewId": str(record.front_preview_id)
        if record.front_preview_id
        else None,
        "backPreviewId": str(record.back_preview_id)
        if record.back_preview_id
        else None,
        "applications": [
            {
                "id": str(item.id),
                "zoneId": str(item.selection.zone_id),
                "zoneSizeId": str(item.selection.zone_size_id),
                "printVersionId": str(item.selection.print_version_id)
                if item.selection.print_version_id
                else None,
                "fileId": str(item.selection.file_id)
                if item.selection.file_id
                else None,
            }
            for item in sorted(
                record.applications,
                key=lambda item: item.selection.zone_id.int,
            )
        ],
    }
    return sha256(
        json.dumps(
            data, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
    ).hexdigest()


@dataclass(frozen=True)
class DraftPage:
    items: tuple[DraftRecord, ...]
    next_cursor: str | None
