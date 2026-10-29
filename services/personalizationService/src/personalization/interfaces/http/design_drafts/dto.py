"""Separate editable selections from server-owned draft fields."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from personalization.application.designs.draft_record import (
    DesignState,
    DraftContent,
    DraftRecord,
)
from personalization.interfaces.http.design_analyses.dto import (
    SelectionRequest,
)
from personalization.interfaces.http.dto.rest_model import RestModel


class DraftRequest(RestModel):
    model_config = ConfigDict(
        populate_by_name=False, validate_by_name=False, validate_by_alias=True
    )
    variant_id: UUID
    template_id: UUID
    applications: Annotated[list[SelectionRequest], Field(max_length=20)]

    def content(self) -> DraftContent:
        return DraftContent(
            self.variant_id,
            self.template_id,
            tuple(item.selection() for item in self.applications),
        )


class SavedApplicationResponse(RestModel):
    id: UUID
    zone_id: UUID
    zone_size_id: UUID
    print_version_id: UUID | None
    file_id: UUID | None


class DraftSummaryResponse(RestModel):
    id: UUID
    owner_id: UUID
    variant_id: UUID
    template_id: UUID
    state: DesignState
    version: int
    front_preview_id: UUID | None
    back_preview_id: UUID | None
    catalog_compatibility_verified: Literal[False] = False
    checkout_ready: Literal[False] = False

    @classmethod
    def from_record(cls, row: DraftRecord) -> DraftSummaryResponse:
        return cls(
            id=row.id,
            owner_id=row.owner_id,
            variant_id=row.variant_id,
            template_id=row.template_id,
            state=row.state,
            version=row.version,
            front_preview_id=row.front_preview_id,
            back_preview_id=row.back_preview_id,
        )


class DraftResponse(DraftSummaryResponse):
    applications: list[SavedApplicationResponse]

    @classmethod
    def from_record(cls, row: DraftRecord) -> DraftResponse:
        return cls(
            id=row.id,
            owner_id=row.owner_id,
            variant_id=row.variant_id,
            template_id=row.template_id,
            state=row.state,
            version=row.version,
            front_preview_id=row.front_preview_id,
            back_preview_id=row.back_preview_id,
            applications=[
                SavedApplicationResponse(
                    id=item.id,
                    zone_id=item.selection.zone_id,
                    zone_size_id=item.selection.zone_size_id,
                    print_version_id=item.selection.print_version_id,
                    file_id=item.selection.file_id,
                )
                for item in row.applications
            ],
        )


class DraftPageResponse(RestModel):
    items: list[DraftSummaryResponse]
    next_cursor: str | None
