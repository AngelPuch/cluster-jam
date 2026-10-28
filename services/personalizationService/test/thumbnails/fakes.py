"""Model durable intentions and exclusive source claims in memory."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
from uuid import UUID, uuid4

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileRecord, FileState
from personalization.application.thumbnails.thumbnail import thumbnail_id
from test.files.fakes import BUCKET
from test.image_samples import make_image


def source_record(
    content: bytes | None = None,
    *,
    width_px: int = 12,
    height_px: int = 8,
    mime_type: str = "image/png",
    state: FileState = FileState.AVAILABLE,
    usage: str = "ORIGINAL",
) -> FileRecord:
    content = make_image() if content is None else content
    file_id = uuid4()
    return FileRecord(
        id=file_id,
        owner_id=uuid4(),
        bucket=BUCKET,
        object_key=f"{file_id}.png",
        mime_type=mime_type,
        size_bytes=len(content),
        width_px=width_px,
        height_px=height_px,
        sha256=sha256(content).hexdigest(),
        state=state,
        usage=usage,
    )


class MemoryThumbnailRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, FileRecord] = {}
        self.sources: list[FileRecord] = []
        self.claimed: set[UUID] = set()
        self.fail_reserve = False
        self.fail_publish = False
        self.publications = 0

    def candidates(self, after: UUID | None, limit: int) -> list[FileRecord]:
        return sorted(
            (
                source
                for source in self.sources
                if (after is None or source.id.int > after.int)
                and (
                    (derived := self.get(source.id)) is None
                    or derived.state is FileState.PENDING
                )
            ),
            key=lambda row: row.id.int,
        )[:limit]

    @contextmanager
    def lock(self, source_id: UUID) -> Iterator[bool]:
        if source_id in self.claimed:
            yield False
            return
        self.claimed.add(source_id)
        try:
            yield True
        finally:
            self.claimed.remove(source_id)

    def get(self, source_id: UUID) -> FileRecord | None:
        return self.records.get(thumbnail_id(source_id))

    def reserve(self, record: FileRecord) -> FileRecord:
        if self.fail_reserve:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE)
        return self.records.setdefault(record.id, record)

    def publish(self, record: FileRecord) -> FileRecord:
        if self.fail_publish:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE)
        self.publications += 1
        result = replace(record, state=FileState.AVAILABLE)
        self.records[record.id] = result
        return result
