"""Keep rendering, persistence and image I/O behind separate ports."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Protocol
from uuid import UUID

from personalization.application.designs.analysis_record import ResolvedSource
from personalization.application.designs.draft_record import DraftRecord
from personalization.application.files.file_record import FileRecord
from personalization.application.previews.preview import RenderedPreview
from personalization.application.templates.template_record import (
    TemplateRecord,
)


class PreviewRepositoryPort(Protocol):
    def candidates(self, after: UUID | None, limit: int) -> list[UUID]: ...
    def lock(self, design_id: UUID) -> AbstractContextManager[bool]: ...
    def get_draft(self, design_id: UUID) -> DraftRecord | None: ...
    def get_file(self, file_id: UUID) -> FileRecord | None: ...
    def reserve(self, record: FileRecord) -> FileRecord: ...
    def publish(self, record: FileRecord) -> FileRecord: ...
    def attach(self, draft: DraftRecord) -> bool: ...


class PreviewRendererPort(Protocol):
    def render(
        self,
        draft: DraftRecord,
        template: TemplateRecord,
        sources: tuple[ResolvedSource, ...],
        read: Callable[[FileRecord], bytes | None],
    ) -> tuple[RenderedPreview, RenderedPreview]: ...
