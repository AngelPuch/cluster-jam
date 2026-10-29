"""Exercise preview orchestration without a production bypass."""

from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

from personalization.application.designs.draft_record import (
    DesignState,
    DraftContent,
    DraftRecord,
)
from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileRecord
from personalization.application.images.image_policy import (
    ImageValidationPolicy,
)
from personalization.application.images.validate_image_service import (
    ValidateImageService,
)
from personalization.application.previews.preview import (
    preview_id,
    preview_revision,
)
from personalization.application.templates.template_record import Side
from personalization.infrastructure.images.pillow_image_inspector import (
    PillowImageInspector,
)
from personalization.infrastructure.images.pillow_preview_renderer import (
    PillowPreviewRenderer,
)
from test.designs.draft_fakes import MemoryDesignRepository
from test.designs.fakes import AnalysisData, analysis_data
from test.files.fakes import StorageServer
from test.image_samples import make_image
from test.thumbnails.fakes import MemoryThumbnailRepository


class MemoryPreviewRepository:
    def __init__(self, designs: MemoryDesignRepository) -> None:
        self._files = MemoryThumbnailRepository()
        self.records = self._files.records
        self.fail_publish = False
        self.designs = designs
        self.fail_attach = False
        self.attachments = 0

    def lock(self, design_id: UUID) -> AbstractContextManager[bool]:
        return self._files.lock(design_id)

    def reserve(self, record: FileRecord) -> FileRecord:
        return self._files.reserve(record)

    def publish(self, record: FileRecord) -> FileRecord:
        if self.fail_publish:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE)
        return self._files.publish(record)

    def get_file(self, file_id: UUID) -> FileRecord | None:
        return self.records.get(file_id)

    def get_draft(self, design_id: UUID) -> DraftRecord | None:
        return self.designs.records.get(design_id)

    def candidates(self, after: UUID | None, limit: int) -> list[UUID]:
        return sorted(
            (
                row.id
                for row in self.designs.records.values()
                if row.state is DesignState.DRAFT
                and (after is None or row.id.int > after.int)
                and (
                    row.front_preview_id is None or row.back_preview_id is None
                )
            ),
            key=lambda value: value.int,
        )[:limit]

    def attach(self, draft: DraftRecord) -> bool:
        if self.fail_attach:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE)
        current = self.get_draft(draft.id)
        if (
            current is None
            or current.state is not DesignState.DRAFT
            or preview_revision(current) != preview_revision(draft)
        ):
            return False
        self.designs.records[draft.id] = replace(
            current,
            front_preview_id=preview_id(draft, Side.FRONT),
            back_preview_id=preview_id(draft, Side.BACK),
        )
        self.attachments += 1
        return True


def renderer() -> PillowPreviewRenderer:
    return PillowPreviewRenderer(
        ValidateImageService(PillowImageInspector(), ImageValidationPolicy())
    )


@dataclass
class PreviewData:
    analysis: AnalysisData
    designs: MemoryDesignRepository
    previews: MemoryPreviewRepository
    draft: DraftRecord
    server: StorageServer


def preview_data() -> PreviewData:
    data = analysis_data()
    designs = MemoryDesignRepository()
    draft = designs.create(
        uuid4(),
        DraftContent(uuid4(), data.template.header.id, data.selections),
    )
    server = StorageServer()
    source = data.sources.file
    server.objects[f"{source.bucket}/{source.object_key}"] = make_image(
        size=(200, 100)
    )
    return PreviewData(
        data, designs, MemoryPreviewRepository(designs), draft, server
    )
