"""Separate image jobs from storage and database implementations."""

from contextlib import AbstractContextManager
from typing import Protocol
from uuid import UUID

from personalization.application.files.file_record import FileRecord
from personalization.application.thumbnails.thumbnail import RenderedThumbnail


class ThumbnailRepositoryPort(Protocol):
    def candidates(
        self, after: UUID | None, limit: int
    ) -> list[FileRecord]: ...

    def lock(self, source_id: UUID) -> AbstractContextManager[bool]: ...

    def get(self, source_id: UUID) -> FileRecord | None: ...

    def reserve(self, record: FileRecord) -> FileRecord: ...

    def publish(self, record: FileRecord) -> FileRecord: ...


class ThumbnailStoragePort(Protocol):
    def ensure_private(self) -> None: ...

    def upload(self, record: FileRecord, content: bytes) -> None: ...

    def read_verified(
        self, record: FileRecord, *, allow_missing: bool = False
    ) -> bytes | None: ...


class ThumbnailRendererPort(Protocol):
    def render(
        self, source: FileRecord, content: bytes
    ) -> RenderedThumbnail: ...
