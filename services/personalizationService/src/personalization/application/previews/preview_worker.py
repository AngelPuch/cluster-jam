"""Recover two-sided previews without publishing stale draft renders."""

from collections.abc import Callable
from dataclasses import replace
from uuid import UUID

from personalization.application.designs.draft_record import DesignState
from personalization.application.errors.design_analysis_error import (
    DesignAnalysisError,
)
from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.errors.image_validation_error import (
    ImageValidationError,
)
from personalization.application.errors.template_error import TemplateError
from personalization.application.files.file_record import FileRecord, FileState
from personalization.application.ports.design_analysis_ports import (
    AnalysisSourcePort,
)
from personalization.application.ports.preview_ports import (
    PreviewRendererPort,
    PreviewRepositoryPort,
)
from personalization.application.ports.template_repository_port import (
    TemplateRepositoryPort,
)
from personalization.application.ports.thumbnail_ports import (
    ThumbnailStoragePort,
)
from personalization.application.previews.preview import (
    check_preview,
    preview_id,
)
from personalization.application.templates.template_record import Side
from personalization.application.thumbnails.thumbnail_worker import (
    ThumbnailBatch,
)


class PreviewWorker:
    def __init__(
        self,
        repository: PreviewRepositoryPort,
        templates: TemplateRepositoryPort,
        sources: AnalysisSourcePort,
        storage: ThumbnailStoragePort,
        renderer: PreviewRendererPort,
        bucket: str,
    ) -> None:
        self._repository = repository
        self._templates = templates
        self._sources = sources
        self._storage = storage
        self._renderer = renderer
        self._bucket = bucket

    def process(self, design_id: UUID) -> bool:
        with self._repository.lock(design_id) as acquired:
            if not acquired:
                return False
            draft = self._repository.get_draft(design_id)
            if draft is None or draft.state is not DesignState.DRAFT:
                return False
            self._storage.ensure_private()
            pending: dict[Side, FileRecord] = {}
            for side in Side:
                record = self._repository.get_file(preview_id(draft, side))
                if record is None:
                    continue
                if not check_preview(draft, side, record, self._bucket):
                    raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
                if record.state is FileState.PENDING:
                    if (
                        self._storage.read_verified(record, allow_missing=True)
                        is not None
                    ):
                        record = self._repository.publish(record)
                pending[side] = record
            if not all(
                side in pending and pending[side].state is FileState.AVAILABLE
                for side in Side
            ):
                template = self._templates.get(draft.template_id)
                sources = self._sources.resolve(draft.content.applications)
                rendered = self._renderer.render(
                    draft, template, sources, self._storage.read_verified
                )
                if tuple(item.side for item in rendered) != tuple(Side):
                    raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
                for item in rendered:
                    intended = item.record(draft, self._bucket)
                    old = pending.get(item.side)
                    if old is not None:
                        if replace(old, state=FileState.PENDING) != intended:
                            raise FileError(
                                FileFailure.FILE_INTEGRITY_MISMATCH
                            )
                        if old.state is FileState.AVAILABLE:
                            continue
                    reserved = self._repository.reserve(intended)
                    if reserved != intended:
                        raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
                    self._storage.upload(reserved, item.content)
                    self._repository.publish(reserved)
            return self._repository.attach(draft)

    def batch(
        self,
        after: UUID | None,
        limit: int,
        stop_requested: Callable[[], bool] = lambda: False,
    ) -> ThumbnailBatch:
        completed = busy = 0
        failures: list[str] = []
        last = None
        for design_id in self._repository.candidates(after, limit):
            if stop_requested():
                break
            last = design_id
            try:
                if self.process(design_id):
                    completed += 1
                else:
                    busy += 1
            except (
                FileError,
                ImageValidationError,
                DesignAnalysisError,
                TemplateError,
            ) as error:
                failures.append(error.failure.value)
        return ThumbnailBatch(completed, busy, tuple(failures), last)
