"""Persist upload intentions before calling external storage."""

from typing import Protocol
from uuid import UUID

from personalization.application.files.file_record import FileRecord


class FileRepositoryPort(Protocol):
    """Commit each durable transition within its own transaction."""

    def create_pending(self, record: FileRecord) -> None:
        """Commit metadata before any object can be created."""
        ...

    def get(self, file_id: UUID) -> FileRecord | None:
        """Retrieve local metadata without consulting
        another service.
        """
        ...

    def make_available(self, file_id: UUID) -> FileRecord:
        """Publish a pending original, or return its published state."""
        ...

    def list_pending(self, limit: int) -> list[FileRecord]:
        """Return a bounded operator reconciliation batch."""
        ...
