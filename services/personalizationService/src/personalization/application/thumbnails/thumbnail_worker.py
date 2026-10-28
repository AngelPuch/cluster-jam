"""Recover image jobs from committed references and intentions."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.errors.image_validation_error import (
    ImageValidationError,
)
from personalization.application.files.file_record import FileRecord, FileState
from personalization.application.ports.thumbnail_ports import (
    ThumbnailRendererPort,
    ThumbnailRepositoryPort,
    ThumbnailStoragePort,
)
from personalization.application.thumbnails.thumbnail import (
    THUMBNAIL_SIDE_PX,
    THUMBNAIL_USAGE_PREFIX,
    thumbnail_id,
)


@dataclass(frozen=True)
class ThumbnailBatch:
    completed: int
    busy: int
    failures: tuple[str, ...]
    after: UUID | None


class ThumbnailWorker:
    def __init__(
        self,
        repository: ThumbnailRepositoryPort,
        storage: ThumbnailStoragePort,
        renderer: ThumbnailRendererPort,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._renderer = renderer

    def process(self, source: FileRecord) -> bool:
        """Serialize one source across worker replicas."""
        if (
            source.usage != "ORIGINAL"
            or source.state is not FileState.AVAILABLE
        ):
            raise FileError(FileFailure.FILE_NOT_READY)
        with self._repository.lock(source.id) as acquired:
            if not acquired:
                return False
            self._storage.ensure_private()
            pending = self._repository.get(source.id)
            if pending is not None:
                self._check_relation(source, pending)
                if pending.state is FileState.AVAILABLE:
                    return True
                # An earlier upload may have lost its acknowledgement.
                if (
                    self._storage.read_verified(pending, allow_missing=True)
                    is not None
                ):
                    self._repository.publish(pending)
                    return True
            content = self._storage.read_verified(source)
            if content is None:
                raise FileError(FileFailure.FILE_NOT_READY)
            rendered = self._renderer.render(source, content)
            intended = rendered.record(source)
            if pending is not None and pending != intended:
                raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
            record = self._repository.reserve(intended)
            self._check_relation(source, record)
            if record != intended:
                raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
            # The intention is committed before the remote write.
            self._storage.upload(record, rendered.content)
            self._repository.publish(record)
            return True

    def _check_relation(self, source: FileRecord, derived: FileRecord) -> None:
        if (
            derived.id != thumbnail_id(source.id)
            or derived.owner_id != source.owner_id
            or derived.bucket != source.bucket
            or derived.object_key != f"{derived.id}.png"
            or derived.mime_type != "image/png"
            or derived.usage != THUMBNAIL_USAGE_PREFIX + str(source.id)
            or not 1 <= derived.width_px <= THUMBNAIL_SIDE_PX
            or not 1 <= derived.height_px <= THUMBNAIL_SIDE_PX
        ):
            raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)

    def batch(
        self,
        after: UUID | None,
        limit: int,
        stop_requested: Callable[[], bool] = lambda: False,
    ) -> ThumbnailBatch:
        """Advance past failures to avoid starving other jobs."""
        sources = self._repository.candidates(after, limit)
        completed = busy = 0
        failures: list[str] = []
        last = None
        for source in sources:
            if stop_requested():
                break
            last = source.id
            try:
                if self.process(source):
                    completed += 1
                else:
                    busy += 1
            except (FileError, ImageValidationError) as error:
                failures.append(error.failure.value)
        return ThumbnailBatch(
            completed,
            busy,
            tuple(failures),
            last,
        )
